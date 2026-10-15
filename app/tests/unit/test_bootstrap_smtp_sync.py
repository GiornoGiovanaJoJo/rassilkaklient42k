"""Пароль ящика из окружения: когда выкатка его обновляет, а когда нет.

Два простых правила, каждое из которых по отдельности плохо кончается.

«Никогда не перезаписывать» выглядит безопасным, но делает неверный пароль
неисправимым оттуда, где вообще живут настройки: поправили ``.env``, выкатили —
ничего не изменилось, а почему, нигде не сказано.

«Всегда перезаписывать» откатывает пароль, который человек исправил в
интерфейсе, при каждой выкатке. Почта работает до первого деплоя и ломается
снова — причём деплой мог быть совсем про другое.

Поэтому запоминается отпечаток того пароля, который записало окружение, и по
нему видно, трогали ли пароль руками.
"""

from __future__ import annotations

from cbmail.db.bootstrap_smtp import _fingerprint, _sync_existing
from cbmail.db.models import SmtpProfile


def _profile(password: str, env_hash: str | None) -> SmtpProfile:
    """Профиль в памяти: здесь проверяется решение, а не запись в базу."""
    return SmtpProfile(
        title="Ящик",
        email_host="smtp.example.com",
        email_port="465",
        email_host_user="box@example.com",
        email_host_password=password,
        env_password_hash=env_hash,
        default_from_email="box@example.com",
        email_use_tls=False,
        email_use_ssl=True,
    )


def _item(password: str) -> dict[str, str]:
    return {
        "host": "smtp.example.com",
        "user": "box@example.com",
        "password": password,
        "title": "Ящик",
        "port": "465",
        "security": "ssl",
        "from": "box@example.com",
        "project": "",
    }


def test_пароль_из_окружения_обновляет_нетронутый_профиль() -> None:
    """Главный случай: в .env положили рабочий пароль вместо нерабочего."""
    profile = _profile("старый", _fingerprint("старый"))
    _sync_existing(profile, _item("новый"), _fingerprint("новый"))
    assert profile.email_host_password == "новый"
    assert profile.env_password_hash == _fingerprint("новый")


def test_правка_в_интерфейсе_не_откатывается() -> None:
    """Человек исправил пароль сам — выкатка его не отменяет."""
    profile = _profile("исправленный-руками", _fingerprint("старый-из-env"))
    _sync_existing(profile, _item("другой-из-env"), _fingerprint("другой-из-env"))
    assert profile.email_host_password == "исправленный-руками"
    # Отметку тоже не трогаем: иначе следующая выкатка решит, что профиль снова
    # её, и затрёт правку.
    assert profile.env_password_hash == _fingerprint("старый-из-env")


def test_старый_профиль_без_отметки_считается_окруженческим() -> None:
    """До появления отметки профили заводились здесь же — владелец тот же."""
    profile = _profile("старый", None)
    _sync_existing(profile, _item("новый"), _fingerprint("новый"))
    assert profile.email_host_password == "новый"
    assert profile.env_password_hash == _fingerprint("новый")


def test_совпадающий_пароль_получает_отметку() -> None:
    """Ничего не меняем, но помечаем — чтобы следующая правка различалась."""
    profile = _profile("тот-же", None)
    _sync_existing(profile, _item("тот-же"), _fingerprint("тот-же"))
    assert profile.email_host_password == "тот-же"
    assert profile.env_password_hash == _fingerprint("тот-же")


def test_пустой_пароль_в_окружении_ничего_не_стирает() -> None:
    """Пароль не задали — это не повод обнулить рабочий."""
    profile = _profile("рабочий", _fingerprint("рабочий"))
    _sync_existing(profile, _item(""), None)
    assert profile.email_host_password == "рабочий"
    assert profile.env_password_hash == _fingerprint("рабочий")


def test_отпечаток_не_раскрывает_пароль() -> None:
    value = _fingerprint("секрет")
    assert "секрет" not in value
    assert len(value) == 64
    assert _fingerprint("секрет") == value, "одинаковый пароль — одинаковый отпечаток"
    assert _fingerprint("секрет ") != value, "разный пароль — разный отпечаток"
