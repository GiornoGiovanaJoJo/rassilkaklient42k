"""Список получателей с обращениями: адрес + имя для подстановки ``{{name}}``.

Отдельно от :mod:`cbmail.domain.emails`, который отвечает ТОЛЬКО за адреса.
Здесь появляется понятие «получатель с именем»: в файле или в поле человек
указывает не просто адрес, а ещё и как к адресату обращаться в письме.

Главное решение — **хранить имена в том же текстовом поле** ``recipient_emails``,
не меняя схему БД. Одна строка на получателя, формат ``email, Имя`` (имя
необязательно). Это важно по двум причинам:

* весь остальной конвейер (``emails.split_emails``/``parse_emails``, план
  рассылки, предпросмотр, счётчики) продолжает извлекать из этого поля ровно
  адреса — имена для него невалидные токены и просто отбрасываются;
* имя нужно только в одном месте — при подстановке ``{{name}}`` в момент
  отправки, и достаётся оно отдельной картой «адрес → имя».

Разбор строки устроен так, чтобы не ломать привычный ввод:

* ``ivan@mail.ru`` — адрес без имени;
* ``Иван Иванов <ivan@mail.ru>`` или ``ivan@mail.ru, Иван`` — адрес с именем;
* ``a@x.ru, b@y.ru`` — несколько адресов в строке: это старый формат «через
  запятую», имена в такой строке не распознаются (их там и нет).
"""

from __future__ import annotations

import re

from cbmail.domain.emails import is_valid_email, normalize_email

# Те же разделители, что и в разборе адресов: запятая, точка с запятой, любые
# пробелы. Имя из нескольких слов собирается обратно через пробел.
_SPLIT_RE = re.compile(r"[,;\s]+")


def _parse_line(line: str) -> tuple[list[str], str]:
    """Разобрать одну строку в (адреса, имя).

    Токен считается адресом, если он валиден после снятия обрамляющих ``<>`` и
    хвостовых знаков препинания. Остальные непустые токены складываются в имя.
    """
    emails: list[str] = []
    name_parts: list[str] = []
    for raw_token in _SPLIT_RE.split(line):
        token = raw_token.strip().strip("<>")
        if not token:
            continue
        candidate = token.strip(",;.")
        if is_valid_email(candidate):
            emails.append(candidate)
        else:
            name_parts.append(token)
    return emails, " ".join(name_parts).strip()


def split_named(raw: str | None) -> tuple[list[tuple[str, str]], list[str]]:
    """Разобрать ввод в список пар ``(адрес, имя)`` и список непринятых строк.

    Порядок первого появления сохраняется, дубликаты адресов убираются по
    нормализованной форме (первое вхождение выигрывает вместе со своим именем).
    Строка, в которой не нашлось ни одного адреса, попадает в «непринятые» —
    чтобы форма могла показать это человеку, а не молча уменьшить список.
    """
    pairs: list[tuple[str, str]] = []
    invalid: list[str] = []
    if not raw:
        return pairs, invalid

    seen: set[str] = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        emails, name = _parse_line(line)
        if not emails:
            invalid.append(line.strip())
            continue
        if len(emails) == 1:
            key = normalize_email(emails[0])
            if key in seen:
                continue
            seen.add(key)
            pairs.append((emails[0], name))
        else:
            # Несколько адресов в одной строке — это список «через запятую».
            # Имя к ним не привязываем: кому из них оно относилось бы, неясно.
            for email in emails:
                key = normalize_email(email)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append((email, ""))
    return pairs, invalid


def name_map(raw: str | None) -> dict[str, str]:
    """Карта «нормализованный адрес → имя» для подстановки при отправке.

    Адреса без имени в карту не попадают — на их месте подставится запасное
    обращение (см. :data:`cbmail.domain.composer.DEFAULT_NAME`).
    """
    pairs, _ = split_named(raw)
    return {normalize_email(email): name for email, name in pairs if name}


def emails_only(pairs: list[tuple[str, str]]) -> list[str]:
    """Только адреса из пар — для валидации и подсчёта получателей."""
    return [email for email, _ in pairs]


def format_lines(pairs: list[tuple[str, str]]) -> str:
    """Собрать пары обратно в текст для хранения: одна строка на получателя.

    Формат ``email, Имя`` (без имени — просто ``email``). Именно его потом снова
    разбирает :func:`split_named`, а адреса из него извлекает ``emails``-модуль.
    """
    lines: list[str] = []
    for email, name in pairs:
        name = (name or "").strip()
        lines.append(f"{email}, {name}" if name else email)
    return "\n".join(lines)


def merge_pairs(
    primary: list[tuple[str, str]], extra: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Объединить два списка пар, убирая повторы адресов (первый список главнее).

    Нужно, когда к адресам, вписанным руками, дописываются адреса из файла:
    если адрес есть в обоих, остаётся имя из первого списка.
    """
    seen = {normalize_email(email) for email, _ in primary}
    result = list(primary)
    for email, name in extra:
        key = normalize_email(email)
        if key in seen:
            continue
        seen.add(key)
        result.append((email, name))
    return result
