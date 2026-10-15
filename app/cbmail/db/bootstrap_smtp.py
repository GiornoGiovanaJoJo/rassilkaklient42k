"""Почтовые ящики как профили отправки — на чистой установке, из окружения.

Профиль SMTP заводится в интерфейсе, под своей учётной записью. На новом
сервере это означает: войти, открыть «Почты», вручную перепечатать хост, порт,
логин и пароль — и только потом можно отправить первое письмо. Ящиков обычно
несколько, а ошибка в одном символе пароля даёт отказ авторизации, который
выглядит как «сервис не работает».

Поэтому ящики описываются в ``.env`` и заводятся при установке — тем же
способом, что и первый администратор (см. :mod:`cbmail.db.bootstrap_admin`).

Формат — плоские переменные с номером, а не JSON одной строкой::

    CBMAIL_SMTP_1_TITLE=Zoom Logistic — info
    CBMAIL_SMTP_1_HOST=smtp.mail.ru
    CBMAIL_SMTP_1_PORT=465
    CBMAIL_SMTP_1_SECURITY=ssl
    CBMAIL_SMTP_1_USER=info@example.ru
    CBMAIL_SMTP_1_PASSWORD=...
    CBMAIL_SMTP_1_FROM=info@example.ru
    CBMAIL_SMTP_1_PROJECT=Zoom Logistic

JSON в ``.env`` ломается тихо: кавычки внутри значения, восклицательный знак в
пароле, перенос строки — и профиль не создаётся без внятной причины. Плоские
переменные читаются глазами и правятся без оглядки на экранирование.

Существующий профиль ищется по паре «владелец + логин ящика».

Пароль у него обновляется, **пока его не трогали руками**. Простое правило
«никогда не перезаписывать» выглядело безопаснее, но делало неверный пароль
неисправимым оттуда, где вообще живут настройки: поправить ``.env`` и выкатить
— ничего не менялось. Простое правило «всегда перезаписывать» откатывало бы
пароль, исправленный в интерфейсе, при каждой выкатке.

Поэтому запоминается отпечаток того пароля, который записало окружение
(``env_password_hash``). Совпадает с текущим — значит профилем по-прежнему
управляет ``.env``, и новое значение можно применить. Не совпадает — пароль
меняли в интерфейсе, и выкатка его не трогает.
"""

from __future__ import annotations

import hashlib
import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from cbmail.db.models import MailProject, Profile, SmtpProfile
from cbmail.db.session import get_sync_engine

logger = logging.getLogger(__name__)

PREFIX = "CBMAIL_SMTP"

# Больше двадцати ящиков на одной установке не встречалось; ограничение нужно,
# чтобы не перебирать окружение бесконечно.
MAX_PROFILES = 20


def _fingerprint(password: str) -> str:
    """Отпечаток пароля — чтобы отличить «поменяли руками» от «как было»."""
    return hashlib.sha256(password.encode()).hexdigest()


DEFAULT_SSL_PORT = 465
DEFAULT_TLS_PORT = 587


def resolve_security(value: str, port: str) -> tuple[bool, bool, str]:
    """Разобрать способ шифрования в пару флагов и порт.

    Возвращает ``(use_tls, use_ssl, port)``. Порт подставляется по способу
    шифрования, если не задан явно: 465 для SSL, 587 для STARTTLS. Ошибиться
    здесь легко — связка «порт 465 + STARTTLS» даёт зависание до таймаута, а не
    внятный отказ, потому что сервер ждёт TLS-рукопожатие с первого байта.
    """
    mode = (value or "").strip().lower()
    if mode in {"ssl", "smtps", "implicit"}:
        return False, True, (port or str(DEFAULT_SSL_PORT))
    if mode in {"none", "plain", ""} and port:
        # Явный порт без шифрования — оставляем как просили, но это открытый
        # канал: логин и пароль уйдут по сети в base64.
        return False, False, port
    if mode in {"none", "plain"}:
        return False, False, str(DEFAULT_TLS_PORT)
    return True, False, (port or str(DEFAULT_TLS_PORT))


def _env(index: int, name: str) -> str:
    return (os.environ.get(f"{PREFIX}_{index}_{name}") or "").strip()


def _describe(index: int) -> dict[str, str] | None:
    """Описание одного ящика из окружения; None — если переменных нет."""
    host = _env(index, "HOST")
    user = _env(index, "USER")
    if not host and not user:
        return None
    return {
        "host": host,
        "user": user,
        "password": os.environ.get(f"{PREFIX}_{index}_PASSWORD") or "",
        "title": _env(index, "TITLE"),
        "port": _env(index, "PORT"),
        "security": _env(index, "SECURITY"),
        "from": _env(index, "FROM"),
        "project": _env(index, "PROJECT"),
    }


def _owner(session: OrmSession) -> Profile | None:
    """Чей это будет ящик.

    Профили принадлежат пользователю, и бесхозных не бывает. Берём
    администратора из ``CBMAIL_ADMIN_LOGIN``, а если не задан — первого
    созданного суперпользователя: на чистой установке он единственный.
    """
    login = (os.environ.get("CBMAIL_ADMIN_LOGIN") or "").strip()
    if login:
        found = session.execute(
            select(Profile).where(Profile.username == login)
        ).scalar_one_or_none()
        if found is not None:
            return found
    return session.execute(
        select(Profile).where(Profile.is_superuser.is_(True)).order_by(Profile.date_joined)
    ).scalars().first()


def _project_id(session: OrmSession, owner: Profile, name: str) -> int | None:
    if not name:
        return None
    existing = session.execute(
        select(MailProject).where(
            MailProject.user_id == owner.id, MailProject.name == name
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    project = MailProject(name=name, user_id=owner.id)
    session.add(project)
    session.flush()
    return project.id


def _sync_existing(
    profile: SmtpProfile, item: dict[str, str], fingerprint: str | None
) -> None:
    """Обновить пароль у заведённого профиля, если им по-прежнему ведает .env.

    Признак — отпечаток: он совпадает с текущим паролем, значит после записи из
    окружения пароль никто не менял. Расхождение означает правку в интерфейсе,
    и выкатка её не отменяет.

    Пустой отпечаток у старой записи считаем «ведёт окружение»: до появления
    этой отметки профили заводились здесь же, и других владельцев у них не
    было. Созданный руками профиль с тем же логином один раз получит пароль из
    окружения — дальше отметка расставится и он будет учитываться как все.
    """
    if not item["password"]:
        return
    if profile.email_host_password == item["password"]:
        # Пароль уже тот самый — ставим отметку, если её ещё нет, и выходим.
        if profile.env_password_hash != fingerprint:
            profile.env_password_hash = fingerprint
        return

    managed_by_env = (
        profile.env_password_hash is None
        or profile.env_password_hash == _fingerprint(profile.email_host_password or "")
    )
    if not managed_by_env:
        logger.info(
            "Почтовый профиль %s: пароль меняли в интерфейсе — значение из окружения не применяем",
            item["user"],
        )
        return

    profile.email_host_password = item["password"]
    profile.env_password_hash = fingerprint
    # Пароль в журнал не пишем ни при каких условиях.
    logger.info("Почтовый профиль %s: пароль обновлён из окружения", item["user"])


def ensure_smtp_profiles() -> None:
    """Завести описанные в окружении ящики и обновить те, что ведёт окружение."""
    described = [item for item in (_describe(i) for i in range(1, MAX_PROFILES + 1)) if item]
    if not described:
        return

    engine = get_sync_engine()
    with OrmSession(engine) as session:
        owner = _owner(session)
        if owner is None:
            logger.error(
                "Почтовые профили описаны в окружении, но в системе нет ни одного "
                "пользователя — заводить ящик не на кого. Сначала создайте "
                "администратора (CBMAIL_ADMIN_LOGIN / CBMAIL_ADMIN_PASSWORD)."
            )
            return

        created = 0
        for item in described:
            if not item["host"] or not item["user"]:
                logger.error(
                    "Ящик %s описан не полностью: нужны и %s_HOST, и %s_USER — пропускаем.",
                    item["title"] or item["user"] or item["host"],
                    PREFIX,
                    PREFIX,
                )
                continue

            use_tls, use_ssl, port = resolve_security(item["security"], item["port"])
            fingerprint = _fingerprint(item["password"]) if item["password"] else None

            existing = session.execute(
                select(SmtpProfile).where(
                    SmtpProfile.user_id == owner.id,
                    SmtpProfile.email_host_user == item["user"],
                )
            ).scalar_one_or_none()

            if existing is not None:
                _sync_existing(existing, item, fingerprint)
                continue

            session.add(
                SmtpProfile(
                    title=item["title"] or item["user"],
                    email_host=item["host"],
                    email_port=port,
                    email_host_user=item["user"],
                    email_host_password=item["password"],
                    env_password_hash=fingerprint,
                    default_from_email=item["from"] or item["user"],
                    email_use_tls=use_tls,
                    email_use_ssl=use_ssl,
                    user_id=owner.id,
                    project_id=_project_id(session, owner, item["project"]),
                )
            )
            created += 1
            # Адрес ящика — не секрет, пароль в журнал не пишем.
            logger.info("Заведён почтовый профиль: %s (%s:%s)", item["user"], item["host"], port)

        session.commit()
