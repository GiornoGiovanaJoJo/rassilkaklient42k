"""Канцелярия: регистрация писем, привязка ответов, сроки — поверх БД.

Связывает чистую доменную логику (:mod:`cbmail.domain.correspondence`) с
хранилищем (таблицы ``cbmail_correspondence*``) и отправкой. Работает только при
включённом флаге ``correspondence_enabled`` — вызывающий код проверяет флаг и не
трогает письма обычной рассылки, если канцелярия выключена.

Все функции принимают синхронную ``Session`` (как сервис отправки): канцелярия
вызывается из того же блокирующего контура, что и SMTP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cbmail.core.config import get_settings
from cbmail.db.models import ContactCard, Correspondence, CorrespondenceEvent
from cbmail.domain.correspondence import contacts, deadlines, numbering, reply_link
from cbmail.domain.correspondence.events import EventType
from cbmail.domain.emails import email_domain, normalize_email


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Справочник контрагентов поверх таблицы cbmail_contact -------------------


@dataclass
class DbContactDirectory:
    """Реализация :class:`contacts.ContactDirectory` поверх ``cbmail_contact``."""

    session: Session

    def by_email(self, email: str) -> contacts.ContactCard | None:
        row = self.session.execute(
            select(ContactCard).where(ContactCard.email == normalize_email(email)).limit(1)
        ).scalar_one_or_none()
        return contacts.ContactCard(row.card_id, row.title) if row else None

    def by_domain(self, domain: str) -> contacts.ContactCard | None:
        row = self.session.execute(
            select(ContactCard).where(ContactCard.domain == (domain or "").lower()).limit(1)
        ).scalar_one_or_none()
        return contacts.ContactCard(row.card_id, row.title) if row else None


# --- Журнал событий ----------------------------------------------------------


def log_event(
    session: Session,
    *,
    tracking_id: str,
    type: EventType,
    correspondence_id: int | None = None,
    actor: str | None = None,
    at: datetime | None = None,
    **payload: object,
) -> CorrespondenceEvent:
    event = CorrespondenceEvent(
        correspondence_id=correspondence_id,
        tracking_id=tracking_id,
        type=type.value,
        actor=actor,
        payload=json.dumps(payload, ensure_ascii=False) if payload else "",
        at=at or _utcnow(),
    )
    session.add(event)
    return event


# --- Нумерация ---------------------------------------------------------------


def _next_sequence(session: Session, direction: numbering.Direction, year: int) -> int:
    """Следующий порядковый номер в пределах направления и года.

    ``max+1`` вместо ``count+1``: после удаления записи номера не должны
    переиспользоваться. Гонку двух параллельных регистраций ловит уникальное
    ограничение ``cbmail_correspondence_regnum_uniq`` — вызывающий повторит.
    """
    current = session.execute(
        select(func.coalesce(func.max(Correspondence.sequence), 0)).where(
            Correspondence.direction == direction.value, Correspondence.year == year
        )
    ).scalar_one()
    return int(current) + 1


# --- Регистрация исходящего письма ------------------------------------------


@dataclass(frozen=True, slots=True)
class OutgoingRegistration:
    correspondence: Correspondence
    headers: dict[str, str]
    tagged_subject: str


def register_outgoing(
    session: Session,
    *,
    from_email: str,
    to_email: str,
    subject: str,
    campaign_id: int | None = None,
    message_type: str | None = None,
    deadline_rules: list[deadlines.DeadlineRule] | None = None,
    actor: str | None = None,
    now: datetime | None = None,
) -> OutgoingRegistration:
    """Зарегистрировать исходящее письмо: номер, tracking, заголовки, журнал.

    Возвращает запись, служебные заголовки (их добавляют к письму перед
    отправкой) и тему со скрытой меткой. Контрагент и срок ответа проставляются
    автоматически, если найдены/настроены.
    """
    settings = get_settings()
    now = now or _utcnow()
    year = now.year

    sequence = _next_sequence(session, numbering.Direction.OUTGOING, year)
    reg = numbering.make_registration_number(numbering.Direction.OUTGOING, sequence, year=year)
    tracking_id = numbering.new_tracking_id(settings.correspondence_prefix, now)

    # Привязка к контрагенту по адресу получателя.
    match = contacts.match_contact(DbContactDirectory(session), to_email)

    # Срок ответа по правилам (если заданы).
    deadline_at = (
        deadlines.assign_deadline(
            deadline_rules,
            sent_at=now,
            message_type=message_type,
            recipient=to_email,
            subject=subject,
        )
        if deadline_rules
        else None
    )
    status = (
        deadlines.compute_status(deadline_at=deadline_at, replied_at=None, now=now).value
        if deadline_at
        else None
    )

    record = Correspondence(
        direction=numbering.Direction.OUTGOING.value,
        reg_number=reg.format(),
        tracking_id=tracking_id,
        year=year,
        sequence=sequence,
        subject=subject[:255],
        from_email=from_email,
        to_email=to_email,
        message_type=message_type,
        contact_card_id=match.card.card_id if match.found else None,
        campaign_id=campaign_id,
        deadline_at=deadline_at,
        deadline_status=status,
    )
    session.add(record)
    session.flush()  # нужен record.id для журнала

    log_event(
        session,
        tracking_id=tracking_id,
        type=EventType.REGISTERED,
        correspondence_id=record.id,
        actor=actor,
        at=now,
        reg_number=reg.format(),
    )
    if match.found:
        log_event(
            session,
            tracking_id=tracking_id,
            type=EventType.CONTACT_MATCHED,
            correspondence_id=record.id,
            at=now,
            card_id=match.card.card_id,
            matched_by=match.matched_by,
        )
    if deadline_at:
        log_event(
            session,
            tracking_id=tracking_id,
            type=EventType.DEADLINE_SET,
            correspondence_id=record.id,
            at=now,
            deadline_at=deadline_at.isoformat(),
        )

    domain = email_domain(from_email) or "localhost"
    headers = reply_link.outgoing_headers(tracking_id, reg.format(), domain)
    tagged = reply_link.tag_subject(subject, tracking_id)
    return OutgoingRegistration(correspondence=record, headers=headers, tagged_subject=tagged)


# --- Привязка входящего ответа ----------------------------------------------


def match_incoming_reply(
    session: Session,
    *,
    headers: dict[str, str],
    subject: str | None,
    from_email: str | None = None,
    actor: str | None = None,
    now: datetime | None = None,
) -> Correspondence | None:
    """Найти исходное письмо по входящему ответу и зафиксировать ответ.

    Возвращает ИСХОДЯЩУЮ запись, к которой привязан ответ, либо ``None``, если
    письмо не является ответом на нашу корреспонденцию. Повторная привязка того
    же ответа не перезаписывает время первого ответа.
    """
    now = now or _utcnow()
    tracking_id = reply_link.extract_tracking_id(headers, subject)
    if not tracking_id:
        return None

    original = session.execute(
        select(Correspondence).where(Correspondence.tracking_id == tracking_id).limit(1)
    ).scalar_one_or_none()
    if original is None:
        return None

    if original.replied_at is None:
        original.replied_at = now
        original.deadline_status = deadlines.compute_status(
            deadline_at=original.deadline_at, replied_at=now, now=now
        ).value

    log_event(
        session,
        tracking_id=tracking_id,
        type=EventType.REPLY_LINKED,
        correspondence_id=original.id,
        actor=actor,
        at=now,
        from_email=from_email or "",
        late=deadlines.answered_late(original.deadline_at, now),
    )
    return original


# --- Пересчёт статусов сроков (для планировщика напоминаний) ------------------


def refresh_deadline_statuses(session: Session, *, now: datetime | None = None) -> int:
    """Перевести просроченные ожидающие письма в статус «просрочен».

    Возвращает число писем, у которых статус сменился. Запускается периодически;
    на каждое нарушение пишет событие ``deadline_breached`` — на нём строятся
    уведомления.
    """
    now = now or _utcnow()
    rows = session.execute(
        select(Correspondence).where(
            Correspondence.replied_at.is_(None),
            Correspondence.deadline_at.is_not(None),
            Correspondence.deadline_at < now,
            Correspondence.deadline_status != deadlines.DeadlineStatus.OVERDUE.value,
        )
    ).scalars().all()
    for row in rows:
        row.deadline_status = deadlines.DeadlineStatus.OVERDUE.value
        log_event(
            session,
            tracking_id=row.tracking_id,
            type=EventType.DEADLINE_BREACHED,
            correspondence_id=row.id,
            at=now,
            deadline_at=row.deadline_at.isoformat() if row.deadline_at else "",
        )
    return len(rows)


def within_hours(hours: int) -> timedelta:
    """Утилита для правил напоминаний: срок «скоро» = в пределах N часов."""
    return timedelta(hours=hours)
