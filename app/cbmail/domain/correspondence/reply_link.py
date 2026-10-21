"""Мета-ссылка «Ответить» и связывание ответа с исходным письмом.

По входящему ответу нужно автоматически понять, на какое НАШЕ исходящее письмо
он пришёл, и привязать его к той же цепочке (треду). Делается только через
служебные заголовки, не меняя тело письма и совместимо с внешними клиентами:

* исходящему ставим ``Message-ID`` с нашим tracking-токеном и дублируем токен в
  ``X-Correspondence-Id`` (+ регистрационный номер в ``X-Correspondence-Reg``);
* клиент при ответе по RFC 5322 копирует наш ``Message-ID`` в ``In-Reply-To`` и
  ``References`` — оттуда достаём токен;
* на случай клиента, потерявшего заголовки, токен прячется в теме как ``[#...]``.

Три независимых источника (In-Reply-To, References, тема) дают устойчивость.
Токен имеет вид ``<PREFIX>-<8 цифр>-<hex/буквы>`` (см. numbering.new_tracking_id).
"""

from __future__ import annotations

import re

HEADER_TRACKING_ID = "X-Correspondence-Id"
HEADER_REG_NUMBER = "X-Correspondence-Reg"

# Токен: буквенный префикс, дата, произвольный хвост. Префикс берётся в скобки
# в регулярках как [A-Za-z0-9]+, чтобы работать с любым кодом организации.
_TOKEN_CORE = r"[A-Za-z][A-Za-z0-9]*-\d{8}-[0-9A-Za-z]+"
_MESSAGE_ID_RE = re.compile(rf"<\s*({_TOKEN_CORE})@")
_SUBJECT_TAG_RE = re.compile(rf"\[#({_TOKEN_CORE})\]")
_TOKEN_RE = re.compile(_TOKEN_CORE)


def build_message_id(tracking_id: str, domain: str) -> str:
    domain = (domain or "localhost").strip().lstrip("@")
    return f"<{tracking_id}@{domain}>"


def outgoing_headers(tracking_id: str, reg_number: str, domain: str) -> dict[str, str]:
    """Служебные заголовки для исходящего письма (добавляются перед отправкой)."""
    return {
        "Message-ID": build_message_id(tracking_id, domain),
        HEADER_TRACKING_ID: tracking_id,
        HEADER_REG_NUMBER: reg_number,
    }


def tag_subject(subject: str, tracking_id: str) -> str:
    """Дописать к теме скрытую метку ``[#token]`` (запасной канал). Идемпотентно."""
    subject = subject or ""
    if f"[#{tracking_id}]" in subject:
        return subject
    return f"{subject} [#{tracking_id}]"


def extract_tracking_id(headers: dict[str, str] | None, subject: str | None = None) -> str | None:
    """Найти наш токен во входящем письме: заголовки, затем тема. ``None`` — не наш."""
    lookup = {str(k).lower(): v for k, v in (headers or {}).items()}

    own = lookup.get(HEADER_TRACKING_ID.lower())
    if own and _TOKEN_RE.fullmatch(own.strip()):
        return own.strip()

    for name in ("in-reply-to", "references"):
        value = lookup.get(name)
        if not value:
            continue
        match = _MESSAGE_ID_RE.search(value) or _TOKEN_RE.search(value)
        if match:
            return match.group(1) if match.re is _MESSAGE_ID_RE else match.group(0)

    if subject:
        match = _SUBJECT_TAG_RE.search(subject)
        if match:
            return match.group(1)

    return None
