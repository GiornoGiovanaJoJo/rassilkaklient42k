"""Проверка почтовых профилей после выкатки — для вывода в журнал деплоя.

«Профиль создан» и «через профиль можно отправить письмо» — разные вещи.
Авторизация отваливается по причинам, которых не видно в базе: почтовый
провайдер требует отдельный пароль для внешних приложений, хостинг закрыл
исходящие порты, пароль изменили. Молчать об этом нельзя — деплой «успешен», а
первая же рассылка не уходит.

Отдельным файлом, а не однострочником внутри workflow: там он живёт в двух
вложенных heredoc'ах, и любая кавычка в нём превращается в нерабочую команду,
которую замечаешь только на боевом сервере.

Код возврата всегда 0: это сообщение, а не проверка. Непрошедший ящик чинится
в интерфейсе за минуту и не повод откатывать выкатку.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from cbmail.db.models import SmtpProfile
        from cbmail.db.session import get_sync_engine
        from cbmail.smtp.sender import SmtpCredentials, verify_credentials
        from sqlalchemy import select
        from sqlalchemy.orm import Session as OrmSession
    except Exception as exc:  # noqa: BLE001 — сообщение важнее разбора причины
        print(f"Проверить почтовые профили не удалось: {exc}")
        return 0

    with OrmSession(get_sync_engine()) as session:
        profiles = session.execute(select(SmtpProfile).order_by(SmtpProfile.id)).scalars().all()

        if not profiles:
            print("Почтовых профилей нет — рассылать не из чего.")
            print("  Опишите ящики в .env (CBMAIL_SMTP_1_*) либо заведите их в разделе «Почты».")
            return 0

        print(f"Почтовые профили ({len(profiles)}):")
        for profile in profiles:
            where = f"{profile.email_host}:{profile.email_port}"
            try:
                ok, message = verify_credentials(SmtpCredentials.from_profile(profile))
            except Exception as exc:  # noqa: BLE001
                ok, message = False, str(exc)
            mark = "OK " if ok else "НЕТ"
            print(f"  [{mark}] {profile.email_host_user} ({where}) — {message}")
            if not ok:
                print("        Исправить: «Почты» → профиль → проверить логин, пароль и порт.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
