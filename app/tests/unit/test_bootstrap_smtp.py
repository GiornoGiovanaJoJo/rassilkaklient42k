"""Разбор описания ящика из окружения и выключатель лицензирования.

База здесь не нужна: проверяется чистая функция, переводящая способ шифрования
в пару флагов и порт. Ошибка в ней не падает, а зависает — связка «порт 465 +
STARTTLS» ждёт рукопожатия до таймаута, и выглядит это как «сервис тормозит».
"""

from __future__ import annotations

from cbmail.core import licensing
from cbmail.db.bootstrap_smtp import resolve_security


def test_ssl_implies_port_465():
    assert resolve_security("ssl", "") == (False, True, "465")


def test_tls_implies_port_587():
    assert resolve_security("tls", "") == (True, False, "587")


def test_empty_security_defaults_to_tls():
    assert resolve_security("", "") == (True, False, "587")


def test_explicit_port_wins_over_default():
    assert resolve_security("ssl", "2465") == (False, True, "2465")
    assert resolve_security("tls", "2587") == (True, False, "2587")


def test_security_is_case_and_space_tolerant():
    # Значение приходит из .env, где легко оставить пробел или заглавные буквы.
    assert resolve_security("  SSL ", "") == (False, True, "465")


def test_ssl_and_tls_are_mutually_exclusive():
    # Оба флага разом — ошибка: клиент начал бы STARTTLS поверх уже
    # зашифрованного канала.
    for mode in ("ssl", "tls", "none", ""):
        use_tls, use_ssl, _ = resolve_security(mode, "")
        assert not (use_tls and use_ssl)


def test_plain_keeps_requested_port():
    assert resolve_security("none", "25") == (False, False, "25")


def test_license_disabled_by_default(monkeypatch):
    monkeypatch.delenv(licensing.LICENSE_REQUIRED_ENV, raising=False)
    assert licensing.license_enforced() is False
    ok, reason = licensing.verify_license(force=True)
    assert ok
    assert "отключ" in reason
    assert licensing.license_status()["enforced"] is False


def test_license_can_be_switched_back_on(monkeypatch, tmp_path):
    # Код проверки не вырезан — включается переменной. Ключа нет, значит
    # обратно включённая проверка обязана закрыть сервис, а не пропустить.
    monkeypatch.setenv(licensing.LICENSE_REQUIRED_ENV, "1")
    monkeypatch.setenv("LICENSE_FILE", str(tmp_path / "нет-такого.key"))
    assert licensing.license_enforced() is True
    ok, reason = licensing.verify_license(force=True)
    assert not ok
    assert "not found" in reason
