"""Состояние лицензии одной строкой — для вывода в журнал деплоя.

Отдельным файлом, а не однострочником внутри workflow: там он живёт в двух
вложенных heredoc'ах, и любая кавычка или перенос строки в нём превращаются в
нерабочую команду, которую замечаешь только на боевом сервере.

Запускается так:
    docker exec rassilka-web python /app/../_config/license-status.py
либо копией внутри образа. Код возврата всегда 0: это сообщение, а не проверка,
и валить из-за него деплой нельзя.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from cbmail.core.licensing import license_status
    except Exception as exc:  # noqa: BLE001 — сообщение важнее разбора причины
        print(f"Состояние лицензии получить не удалось: {exc}")
        return 0

    status = license_status()
    if not status.get("enforced", True):
        print("Лицензия: проверка отключена — сервис работает без ключа.")
        return 0
    if status["ok"]:
        print("Лицензия: действительна")
        return 0

    print("ЛИЦЕНЗИЯ НЕ АКТИВИРОВАНА — сервис закрыт, кроме страницы активации.")
    print(f"  причина: {status['reason']}")
    print(f"  host_id: {status['host_id']}")
    print("  Выпустите ключ на этот host_id и введите его на странице /license")
    return 0


if __name__ == "__main__":
    sys.exit(main())
