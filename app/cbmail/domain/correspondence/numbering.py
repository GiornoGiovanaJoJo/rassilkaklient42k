"""Автоматическая нумерация корреспонденции.

Каждому письму (входящему и исходящему) присваивается уникальный
регистрационный номер и стабильный tracking-идентификатор. Регистрационный
номер — для канцелярии (направление, год, сквозной порядковый номер), tracking —
для связывания ответа и поиска в журнале (см. :mod:`.reply_link`).

Чистый модуль без ввода-вывода: выдачу порядкового значения делает вызывающий
код (счётчик в БД), здесь — только форматирование и разбор, чтобы правила
нумерации проверялись тестами без базы.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    """Направление письма. Значение — префикс в регистрационном номере."""

    INCOMING = "ВХ"
    OUTGOING = "ИСХ"


_REG_NUMBER_RE = re.compile(r"^(?P<dir>ВХ|ИСХ)-(?P<year>\d{4})-(?P<seq>\d{6})$")
_SEQ_WIDTH = 6


@dataclass(frozen=True, slots=True)
class RegistrationNumber:
    direction: Direction
    year: int
    sequence: int

    def format(self) -> str:
        return f"{self.direction.value}-{self.year:04d}-{self.sequence:0{_SEQ_WIDTH}d}"

    def __str__(self) -> str:
        return self.format()


def make_registration_number(
    direction: Direction, sequence: int, *, year: int | None = None, now: datetime | None = None
) -> RegistrationNumber:
    """Собрать регистрационный номер. ``sequence`` выдаёт счётчик (БД)."""
    if sequence < 1:
        raise ValueError("Порядковый номер должен быть положительным")
    if year is None:
        year = (now or datetime.now()).year
    return RegistrationNumber(direction=direction, year=year, sequence=sequence)


def parse_registration_number(value: str) -> RegistrationNumber:
    """Разобрать строку номера обратно в структуру. Бросает ``ValueError``."""
    match = _REG_NUMBER_RE.match((value or "").strip())
    if not match:
        raise ValueError(f"Не похоже на регистрационный номер: {value!r}")
    return RegistrationNumber(
        direction=Direction(match.group("dir")),
        year=int(match.group("year")),
        sequence=int(match.group("seq")),
    )


def new_tracking_id(prefix: str, now: datetime | None = None) -> str:
    """Уникальный tracking-идентификатор письма: ``<PREFIX>-<дата>-<hex>``.

    ``prefix`` — буквенный код организации (настройка ``correspondence_prefix``).
    Случайный хвост криптографический, чтобы токен нельзя было угадать и
    подделать привязку ответа.
    """
    stamp = (now or datetime.now()).strftime("%Y%m%d")
    code = (prefix or "COR").strip().upper()
    return f"{code}-{stamp}-{secrets.token_hex(8)}"
