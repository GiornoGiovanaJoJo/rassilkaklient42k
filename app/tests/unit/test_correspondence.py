"""Тесты канцелярии: нумерация, тред, сроки, контрагенты, журнал + сервис."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from cbmail.db.models import ContactCard, CorrespondenceEvent
from cbmail.domain.correspondence import deadlines, numbering, reply_link
from cbmail.domain.correspondence.events import EventType
from cbmail.services import correspondence as svc

# --- Доменная логика ---------------------------------------------------------

class TestNumbering:
    def test_format_and_roundtrip(self) -> None:
        n = numbering.make_registration_number(numbering.Direction.OUTGOING, 123, year=2026)
        assert str(n) == "ИСХ-2026-000123"
        assert numbering.parse_registration_number(str(n)) == n

    def test_tracking_id_prefix(self) -> None:
        tid = numbering.new_tracking_id("NIIPP", datetime(2026, 10, 21))
        assert tid.startswith("NIIPP-20261021-")


class TestReplyLink:
    def test_roundtrip_in_reply_to(self) -> None:
        headers = reply_link.outgoing_headers("COR-20261021-abcd", "ИСХ-2026-000001", "niipp.ru")
        incoming = {"In-Reply-To": headers["Message-ID"]}
        assert reply_link.extract_tracking_id(incoming) == "COR-20261021-abcd"

    def test_subject_fallback(self) -> None:
        subj = reply_link.tag_subject("Запрос", "COR-20261021-dead")
        assert reply_link.extract_tracking_id({}, "Re: " + subj) == "COR-20261021-dead"

    def test_foreign_reply_ignored(self) -> None:
        assert reply_link.extract_tracking_id({"In-Reply-To": "<x@gmail.com>"}, "Re: hi") is None


class TestDeadlines:
    NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    def test_statuses(self) -> None:
        past = self.NOW - timedelta(hours=1)
        future = self.NOW + timedelta(hours=1)
        S = deadlines.DeadlineStatus
        assert deadlines.compute_status(deadline_at=future, replied_at=None, now=self.NOW) is S.WAITING
        assert deadlines.compute_status(deadline_at=past, replied_at=None, now=self.NOW) is S.OVERDUE
        assert deadlines.compute_status(deadline_at=past, replied_at=self.NOW, now=self.NOW) is S.ANSWERED

    def test_rule_assignment(self) -> None:
        rules = [
            deadlines.DeadlineRule(hours=4, recipient_domain="eis.gov.ru"),
            deadlines.DeadlineRule(hours=48),
        ]
        specific = deadlines.assign_deadline(rules, sent_at=self.NOW, recipient="a@eis.gov.ru")
        general = deadlines.assign_deadline(rules, sent_at=self.NOW, recipient="a@mail.ru")
        assert specific == self.NOW + timedelta(hours=4)
        assert general == self.NOW + timedelta(hours=48)


# --- Сервис (поверх БД) ------------------------------------------------------

class TestCorrespondenceService:
    NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    def test_register_outgoing_assigns_number_tracking_headers(self, db: Session) -> None:
        reg = svc.register_outgoing(
            db,
            from_email="info@niipp.ru",
            to_email="partner@x.ru",
            subject="Запрос цен",
            now=self.NOW,
            actor="ivan",
        )
        assert reg.correspondence.reg_number == "ИСХ-2026-000001"
        assert reg.headers[reply_link.HEADER_TRACKING_ID] == reg.correspondence.tracking_id
        assert reg.headers["Message-ID"].endswith("@niipp.ru>")
        assert "[#" in reg.tagged_subject
        # Зафиксировано событие регистрации (flush — фикстура с autoflush=False).
        db.flush()
        events = db.query(CorrespondenceEvent).filter_by(tracking_id=reg.correspondence.tracking_id).all()
        assert any(e.type == EventType.REGISTERED.value for e in events)

    def test_sequence_increments_per_direction_year(self, db: Session) -> None:
        a = svc.register_outgoing(db, from_email="i@n.ru", to_email="a@x.ru", subject="1", now=self.NOW)
        b = svc.register_outgoing(db, from_email="i@n.ru", to_email="b@x.ru", subject="2", now=self.NOW)
        assert a.correspondence.reg_number == "ИСХ-2026-000001"
        assert b.correspondence.reg_number == "ИСХ-2026-000002"

    def test_contact_matched_by_email(self, db: Session) -> None:
        db.add(ContactCard(card_id="K-1", title="ООО Ромашка", email="partner@x.ru", domain="x.ru"))
        db.flush()
        reg = svc.register_outgoing(db, from_email="i@n.ru", to_email="Partner@X.ru", subject="s", now=self.NOW)
        assert reg.correspondence.contact_card_id == "K-1"

    def test_deadline_assigned_and_status(self, db: Session) -> None:
        rules = [deadlines.DeadlineRule(hours=24)]
        reg = svc.register_outgoing(
            db, from_email="i@n.ru", to_email="a@x.ru", subject="s",
            deadline_rules=rules, now=self.NOW,
        )
        assert reg.correspondence.deadline_at == self.NOW + timedelta(hours=24)
        assert reg.correspondence.deadline_status == deadlines.DeadlineStatus.WAITING.value

    def test_incoming_reply_links_and_closes(self, db: Session) -> None:
        reg = svc.register_outgoing(
            db, from_email="info@niipp.ru", to_email="a@x.ru", subject="Запрос",
            deadline_rules=[deadlines.DeadlineRule(hours=24)], now=self.NOW,
        )
        # Ответ приходит с нашим Message-ID в In-Reply-To.
        reply_time = self.NOW + timedelta(hours=2)
        original = svc.match_incoming_reply(
            db,
            headers={"In-Reply-To": reg.headers["Message-ID"]},
            subject="Re: Запрос",
            from_email="a@x.ru",
            now=reply_time,
        )
        assert original is not None
        assert original.id == reg.correspondence.id
        assert original.replied_at == reply_time
        assert original.deadline_status == deadlines.DeadlineStatus.ANSWERED.value

    def test_foreign_reply_returns_none(self, db: Session) -> None:
        assert svc.match_incoming_reply(db, headers={"In-Reply-To": "<x@gmail.com>"}, subject="hi") is None

    def test_refresh_deadline_marks_overdue(self, db: Session) -> None:
        reg = svc.register_outgoing(
            db, from_email="i@n.ru", to_email="a@x.ru", subject="s",
            deadline_rules=[deadlines.DeadlineRule(hours=1)], now=self.NOW,
        )
        later = self.NOW + timedelta(hours=2)
        changed = svc.refresh_deadline_statuses(db, now=later)
        assert changed == 1
        # Тот же объект в identity map уже обновлён; событие — после flush.
        assert reg.correspondence.deadline_status == deadlines.DeadlineStatus.OVERDUE.value
        db.flush()
        breached = db.query(CorrespondenceEvent).filter_by(type=EventType.DEADLINE_BREACHED.value).count()
        assert breached == 1
