"""Привязка письма к карточке контрагента по адресу.

Идентификация контрагента по email: сначала точное совпадение адреса, затем по
домену (новый сотрудник уже известной организации). Нормализация адреса —
общая с остальной системой (:mod:`cbmail.domain.emails`), чтобы ``Ivan@X.RU`` и
``ivan@x.ru`` считались одним адресом везде одинаково.

Справочник контрагентов — протокол :class:`ContactDirectory`; реальная
реализация (БД, см. services) ищет в таблице ``cbmail_contact``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cbmail.domain.emails import email_domain, normalize_email


@dataclass(frozen=True, slots=True)
class ContactCard:
    card_id: str
    title: str


class ContactDirectory(Protocol):
    def by_email(self, email: str) -> ContactCard | None: ...

    def by_domain(self, domain: str) -> ContactCard | None: ...


@dataclass(frozen=True, slots=True)
class MatchResult:
    card: ContactCard | None
    matched_by: str  # "email" | "domain" | "none"

    @property
    def found(self) -> bool:
        return self.card is not None


def match_contact(directory: ContactDirectory, email: str) -> MatchResult:
    """Найти карточку контрагента: сначала по адресу, затем по домену."""
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return MatchResult(card=None, matched_by="none")

    exact = directory.by_email(normalized)
    if exact is not None:
        return MatchResult(card=exact, matched_by="email")

    by_domain = directory.by_domain(email_domain(normalized))
    if by_domain is not None:
        return MatchResult(card=by_domain, matched_by="domain")

    return MatchResult(card=None, matched_by="none")
