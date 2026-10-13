"""Первый администратор на чистой установке.

Пользователи в системе заводятся только из-под уже существующего
администратора. На новом сервере таких нет, и получалась замкнутая ситуация:
сервис поднят, а войти в него некому.

Поэтому при установке с нуля создаётся первая учётная запись — из переменных
окружения ``CBMAIL_ADMIN_LOGIN`` и ``CBMAIL_ADMIN_PASSWORD``.

Пароль берётся из окружения, а не придумывается здесь: записать выдуманный в
журнал значит отдать доступ любому, кто этот журнал прочитает, а журналы
пересылают в поддержку не задумываясь. Если переменные не заданы, учётная
запись не создаётся — вместо этого в журнал идёт внятное указание, что
прописать. Сервис при этом стартует: падать из-за ненастроенного входа значит
прятать причину за «контейнер не поднялся».

Повторный запуск ничего не делает: учётная запись уже есть.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from cbmail.core.security import hash_password
from cbmail.db.models import Profile
from cbmail.db.session import get_sync_engine

logger = logging.getLogger(__name__)

LOGIN_ENV = "CBMAIL_ADMIN_LOGIN"
PASSWORD_ENV = "CBMAIL_ADMIN_PASSWORD"
EMAIL_ENV = "CBMAIL_ADMIN_EMAIL"

# Короткий пароль у учётной записи с полным доступом — приглашение к подбору.
MIN_PASSWORD_LENGTH = 10


def ensure_first_admin() -> None:
    """Создать первого администратора, если в системе нет ни одного."""
    engine = get_sync_engine()
    with OrmSession(engine) as session:
        existing = session.execute(select(Profile.id).limit(1)).first()
        if existing is not None:
            return

        login = (os.environ.get(LOGIN_ENV) or "").strip()
        password = os.environ.get(PASSWORD_ENV) or ""

        if not login or not password:
            logger.error(
                "В системе нет ни одного пользователя, и войти в неё некому. "
                "Пропишите в .env переменные %s и %s и перезапустите сервис.",
                LOGIN_ENV,
                PASSWORD_ENV,
            )
            return

        if len(password) < MIN_PASSWORD_LENGTH:
            logger.error(
                "%s короче %s символов — учётная запись не создана. "
                "У администратора полный доступ к рассылкам и адресам получателей.",
                PASSWORD_ENV,
                MIN_PASSWORD_LENGTH,
            )
            return

        session.add(
            Profile(
                username=login,
                email=(os.environ.get(EMAIL_ENV) or "").strip(),
                password=hash_password(password),
                is_superuser=True,
                is_staff=True,
                is_active=True,
            )
        )
        session.commit()
        # Логин — не секрет, пароль в журнал не пишем ни при каких условиях.
        logger.info("Создан первый администратор: %s", login)
