"""Сроки ответа на письма и их статусы.

Для исходящего письма можно задать срок ожидания ответа (deadline). Модуль
считает статус (ожидается / просрочен / получен) и умеет назначать срок по
правилам — по типу, тематике или получателю. Логика чистая: времена и правила
на входе, статус/срок на выходе.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class DeadlineStatus(str, Enum):
    WAITING = "ожидается"
    OVERDUE = "просрочен"
    ANSWERED = "получен"

    @property
    def is_closed(self) -> bool:
        return self is DeadlineStatus.ANSWERED


def compute_status(
    *, deadline_at: datetime | None, replied_at: datetime | None, now: datetime
) -> DeadlineStatus:
    """Статус срока: ответ важнее просрочки; без срока — всегда «ожидается»."""
    if replied_at is not None:
        return DeadlineStatus.ANSWERED
    if deadline_at is not None and now > deadline_at:
        return DeadlineStatus.OVERDUE
    return DeadlineStatus.WAITING


def answered_late(deadline_at: datetime | None, replied_at: datetime | None) -> bool:
    if deadline_at is None or replied_at is None:
        return False
    return replied_at > deadline_at


def is_breaching_soon(
    *, deadline_at: datetime | None, replied_at: datetime | None, now: datetime, within: timedelta
) -> bool:
    """Срок скоро истечёт, ответа нет — повод напомнить заранее."""
    if deadline_at is None or replied_at is not None:
        return False
    return now <= deadline_at <= now + within


@dataclass(frozen=True, slots=True)
class DeadlineRule:
    """Правило автоназначения срока. Условия соединяются по И; ``None`` — не важно."""

    hours: int
    message_type: str | None = None
    recipient_domain: str | None = None
    subject_contains: str | None = None

    def matches(
        self, *, message_type: str | None, recipient: str | None, subject: str | None
    ) -> bool:
        if self.message_type is not None and (message_type or "") != self.message_type:
            return False
        if self.recipient_domain is not None:
            domain = (recipient or "").rsplit("@", 1)[-1].lower()
            if domain != self.recipient_domain.lower():
                return False
        return not (
            self.subject_contains is not None
            and self.subject_contains.lower() not in (subject or "").lower()
        )


def assign_deadline(
    rules: list[DeadlineRule],
    *,
    sent_at: datetime,
    message_type: str | None = None,
    recipient: str | None = None,
    subject: str | None = None,
) -> datetime | None:
    """Назначить срок по первому подошедшему правилу; иначе ``None``."""
    for rule in rules:
        if rule.matches(message_type=message_type, recipient=recipient, subject=subject):
            return sent_at + timedelta(hours=rule.hours)
    return None
