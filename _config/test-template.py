"""Диагностический шаблон письма — чтобы проверять вёрстку по одному письму.

Зачем. «Шаблон расползается» — жалоба, по которой невозможно понять, что
именно сломано: ширина, колонки, картинки или подстановки. Проверять это на
боевом письме долго и неудобно. Здесь собран один шаблон, где каждый блок
проверяет ровно одну вещь и сам подписан, что он проверяет. Отправили его
себе, открыли на телефоне и в Outlook — и сразу видно, что не так.

Что проверяет:

* ширину — письмо должно остаться колонкой 600 px, а не растянуться на весь
  экран (в Outlook это ломалось: движок Word не понимает max-width);
* колонки — меню из трёх пунктов должно остаться в строку, а не рассыпаться на
  три столбика букв по вертикали (так ломал отменённый «отзывчивый» режим);
* картинку — приходит ли она к получателю вообще;
* подстановки — {{email}} и {{unsubscribe_url}} должны замениться на адрес
  получателя и рабочую ссылку отписки;
* длинный текст — не должен рваться посреди слов.

Запуск на сервере (файл кладёт деплой, внутрь образа он не попадает):

    docker cp _config/test-template.py rassilka-web:/tmp/test-template.py
    docker exec rassilka-web python /tmp/test-template.py           # показать, что будет
    docker exec rassilka-web python /tmp/test-template.py --apply   # завести шаблон

Без --apply ничего не пишется: печатается JSON, который можно вставить в
редакторе кнопкой загрузки шаблона из файла.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import zlib
from pathlib import Path

TEMPLATE_NAME = "Проверка вёрстки (тестовый)"

#: Ширина колонки письма. Та же, что у конструктора, — на неё опирается рамка
#: для Outlook, без неё проверка ширины бессмысленна.
EMAIL_WIDTH = 600

MEDIA_SUBDIR = "test-template"
IMAGE_NAME = "proverka.png"

#: Подпись картинки. Она же — проверка: подпись видна ровно тогда, когда
#: картинка не загрузилась, и сразу объясняет, что именно произошло.
IMAGE_ALT = "Зелёная полоса с белым просветом — если вы читаете эту надпись, картинка не загрузилась"


# --- Картинка ----------------------------------------------------------------


def _png(width: int, height: int, rows: list[bytes]) -> bytes:
    """Собрать PNG из готовых строк пикселей (RGB, по три байта на точку).

    Рисуем сами, без Pillow: тащить ради одной проверочной картинки
    графическую библиотеку в образ незачем.
    """

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _test_image_bytes() -> bytes:
    """Полоса с рамкой и белым просветом — её ни с чем не спутаешь.

    Картинка должна отличаться от «ничего не загрузилось» с одного взгляда,
    поэтому не однотонная: видно и границы, и середину.
    """
    width, height = 560, 120
    border, dark, light, white = 6, (0x1F, 0x6F, 0x3C), (0xDC, 0xEF, 0xE2), (0xFF, 0xFF, 0xFF)

    rows: list[bytes] = []
    for y in range(height):
        if y < border or y >= height - border:
            rows.append(bytes(dark) * width)
            continue
        line = bytearray()
        for x in range(width):
            if x < border or x >= width - border:
                line += bytes(dark)
            elif height // 3 <= y < height * 2 // 3 and width // 6 <= x < width * 5 // 6:
                line += bytes(white)
            else:
                line += bytes(light)
        rows.append(bytes(line))
    return _png(width, height, rows)


def _ensure_image(base_url: str) -> str:
    """Положить картинку в media и вернуть её публичный адрес."""
    media_root = Path(os.environ.get("MEDIA_ROOT", "_media"))
    target_dir = media_root / MEDIA_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / IMAGE_NAME
    if not target.exists():
        target.write_bytes(_test_image_bytes())
    return f"{base_url}/media/{MEDIA_SUBDIR}/{IMAGE_NAME}"


# --- Документ конструктора ----------------------------------------------------


def _pad(top: int = 0, right: int = 24, bottom: int = 0, left: int = 24) -> dict:
    return {"top": top, "right": right, "bottom": bottom, "left": left}


def build_document(image_url: str, base_url: str) -> dict:
    """Документ редактора. По нему письмо открывается и правится как обычное."""
    order = [
        "t-head",
        "t-intro",
        "t-div1",
        "t-h-width",
        "t-width",
        "t-div2",
        "t-h-cols",
        "t-cols",
        "t-div3",
        "t-h-image",
        "t-image",
        "t-div4",
        "t-h-button",
        "t-button",
        "t-div5",
        "t-h-vars",
        "t-vars",
        "t-unsub",
    ]

    def text(key: str, body: str, **style) -> tuple[str, dict]:
        base_style = {"padding": _pad(8, 24, 8, 24), "fontWeight": "normal"}
        base_style.update(style)
        return key, {"type": "Text", "data": {"props": {"text": body, "markdown": False}, "style": base_style}}

    def divider(key: str) -> tuple[str, dict]:
        return key, {
            "type": "Divider",
            "data": {"props": {"lineColor": "#E0E0E0", "lineHeight": 1}, "style": {"padding": _pad(12, 24, 12, 24)}},
        }

    def subhead(key: str, body: str) -> tuple[str, dict]:
        return text(key, body, fontWeight="bold", color="#1F6F3C", padding=_pad(4, 24, 4, 24))

    blocks: dict[str, dict] = {}
    blocks.update(
        dict(
            [
                (
                    "t-head",
                    {
                        "type": "Heading",
                        "data": {
                            "props": {"text": "Проверка письма", "level": "h2"},
                            "style": {"padding": _pad(24, 24, 4, 24), "textAlign": "center"},
                        },
                    },
                ),
                text(
                    "t-intro",
                    "Это служебное письмо. Откройте его на компьютере, на телефоне "
                    "и на рабочей почте. Каждый блок ниже подписан, что он проверяет: "
                    "если блок выглядит как описано — эта часть работает.",
                    textAlign="center",
                    color="#616161",
                ),
                divider("t-div1"),
                subhead("t-h-width", "1. Ширина"),
                text(
                    "t-width",
                    "Письмо должно оставаться узкой колонкой по центру, даже если окно "
                    "почты раскрыто на весь экран. Если текст растянулся на всю ширину "
                    "и строки стали длинными — ширина не держится.",
                ),
                divider("t-div2"),
                subhead("t-h-cols", "2. Колонки"),
                (
                    "t-cols",
                    {
                        "type": "ColumnsContainer",
                        "data": {
                            "props": {
                                "columnsCount": 3,
                                "columnsGap": 12,
                                "contentAlignment": "middle",
                                "columns": [
                                    {"childrenIds": ["t-col1"]},
                                    {"childrenIds": ["t-col2"]},
                                    {"childrenIds": ["t-col3"]},
                                ],
                            },
                            "style": {"padding": _pad(8, 24, 8, 24)},
                        },
                    },
                ),
                text("t-col1", "о компании", textAlign="center", fontWeight="bold", padding=_pad()),
                text("t-col2", "каталог", textAlign="center", fontWeight="bold", padding=_pad()),
                text("t-col3", "новости", textAlign="center", fontWeight="bold", padding=_pad()),
                text(
                    "t-cols-note",
                    "Три слова выше должны стоять в строку. Если они встали столбиком "
                    "или рассыпались на буквы по вертикали — колонки ломаются.",
                    color="#616161",
                ),
                divider("t-div3"),
                subhead("t-h-image", "3. Картинка"),
                (
                    "t-image",
                    {
                        "type": "Image",
                        "data": {
                            "props": {
                                "url": image_url,
                                "alt": IMAGE_ALT,
                                "linkHref": None,
                                "contentAlignment": "middle",
                            },
                            "style": {"padding": _pad(8, 24, 8, 24), "textAlign": "center"},
                        },
                    },
                ),
                divider("t-div4"),
                subhead("t-h-button", "4. Кнопка и ссылка"),
                (
                    "t-button",
                    {
                        "type": "Button",
                        "data": {
                            "props": {
                                "text": "Проверить ссылку",
                                "url": base_url,
                                "size": "medium",
                                "buttonStyle": "rounded",
                                "buttonTextColor": "#FFFFFF",
                                "buttonBackgroundColor": "#1F6F3C",
                            },
                            "style": {"padding": _pad(8, 24, 8, 24), "textAlign": "center"},
                        },
                    },
                ),
                divider("t-div5"),
                subhead("t-h-vars", "5. Подстановки"),
                text(
                    "t-vars",
                    "Письмо отправлено на адрес {{email}} — здесь должен стоять ваш "
                    "адрес, а не фигурные скобки. Если видны скобки, подстановка не "
                    "сработала.",
                ),
                text(
                    "t-unsub",
                    "Ссылка отписки: {{unsubscribe_url}} — она должна открываться и "
                    "сообщать, что адрес отписан. Ссылка на 404 — повод для получателя "
                    "нажать «Спам».",
                    color="#616161",
                    padding=_pad(8, 24, 24, 24),
                ),
            ]
        )
    )

    # Пояснение под колонками идёт сразу за ними, а сами колонки держат
    # дочерние блоки по идентификаторам — в корень они не попадают.
    order.insert(order.index("t-cols") + 1, "t-cols-note")

    blocks["root"] = {
        "type": "EmailLayout",
        "data": {
            "backdropColor": "#F5F5F5",
            "canvasColor": "#FFFFFF",
            "textColor": "#262626",
            "borderColor": "#E0E0E0",
            "borderRadius": 0,
            "fontFamily": "MODERN_SANS",
            "childrenIds": order,
        },
    }
    return blocks


# --- HTML --------------------------------------------------------------------

_FONT = '"Helvetica Neue", "Arial Nova", "Nimbus Sans", Arial, sans-serif'


def build_html(image_url: str, base_url: str) -> str:
    """Готовое письмо.

    Форма повторяет то, что отдаёт конструктор: корневая таблица шириной 100%
    с ограничением max-width. Это важно — именно по объявленному max-width
    сборка письма добавляет рамку для Outlook.
    """

    def block(inner: str, padding: str = "8px 24px") -> str:
        return f'<div style="padding:{padding}">{inner}</div>'

    def note(body: str) -> str:
        return block(f'<div style="color:#616161">{body}</div>')

    def sub(body: str) -> str:
        return block(f'<div style="color:#1F6F3C;font-weight:bold">{body}</div>', "4px 24px")

    def line() -> str:
        return block('<hr style="border:none;border-top:1px solid #E0E0E0;margin:0">', "12px 24px")

    menu_cell = (
        '<td style="vertical-align:middle;text-align:center;font-weight:bold">{}</td>'
    )
    menu = (
        '<table align="center" width="100%" cellpadding="0" cellspacing="0" border="0"'
        ' style="table-layout:fixed;border-collapse:collapse"><tbody><tr>'
        + menu_cell.format("о компании")
        + menu_cell.format("каталог")
        + menu_cell.format("новости")
        + "</tr></tbody></table>"
    )

    body = "".join(
        [
            block(
                f'<h2 style="margin:0;font-family:{_FONT};text-align:center">Проверка письма</h2>',
                "24px 24px 4px 24px",
            ),
            note(
                "Это служебное письмо. Откройте его на компьютере, на телефоне и на "
                "рабочей почте. Каждый блок ниже подписан, что он проверяет: если блок "
                "выглядит как описано — эта часть работает."
            ),
            line(),
            sub("1. Ширина"),
            block(
                "Письмо должно оставаться узкой колонкой по центру, даже если окно почты "
                "раскрыто на весь экран. Если текст растянулся на всю ширину и строки "
                "стали длинными — ширина не держится."
            ),
            line(),
            sub("2. Колонки"),
            block(menu),
            note(
                "Три слова выше должны стоять в строку. Если они встали столбиком или "
                "рассыпались на буквы по вертикали — колонки ломаются."
            ),
            line(),
            sub("3. Картинка"),
            block(
                f'<img src="{image_url}" width="560" alt="{IMAGE_ALT}" '
                'style="display:inline-block;vertical-align:middle;border:none">',
                "8px 24px",
            ),
            line(),
            sub("4. Кнопка и ссылка"),
            block(
                f'<div style="text-align:center"><a href="{base_url}" target="_blank" '
                f'style="display:inline-block;padding:12px 20px;background-color:#1F6F3C;'
                f'color:#FFFFFF;font-family:{_FONT};font-weight:bold;border-radius:4px;'
                'text-decoration:none">Проверить ссылку</a></div>'
            ),
            line(),
            sub("5. Подстановки"),
            block(
                "Письмо отправлено на адрес {{email}} — здесь должен стоять ваш адрес, "
                "а не фигурные скобки. Если видны скобки, подстановка не сработала."
            ),
            note(
                'Ссылка отписки: <a href="{{unsubscribe_url}}" style="color:#616161">'
                "{{unsubscribe_url}}</a> — она должна открываться и сообщать, что адрес "
                "отписан. Ссылка на 404 — повод для получателя нажать «Спам»."
            ),
        ]
    )

    return (
        '<div style="background-color:#F5F5F5;color:#262626;font-family:' + _FONT + ";"
        'font-size:16px;line-height:1.5;margin:0;padding:32px 0;width:100%">'
        '<table align="center" width="100%" role="presentation" cellspacing="0" cellpadding="0"'
        f' border="0" style="margin:0 auto;max-width:{EMAIL_WIDTH}px;background-color:#ffffff;'
        'border:1px solid #E0E0E0">'
        '<tbody><tr style="width:100%"><td>' + body + "</td></tr></tbody></table></div>"
    )


# --- Запись ------------------------------------------------------------------


def main() -> int:
    apply = "--apply" in sys.argv
    configured_base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    base_url = configured_base or "http://localhost:8000"

    if not configured_base:
        # Молча подставить localhost нельзя: картинка и кнопка в письме будут
        # вести на адрес, которого у получателя нет, и проверка покажет
        # «картинка не дошла» там, где на самом деле не настроен адрес сервиса.
        print("ВНИМАНИЕ: PUBLIC_BASE_URL не задан в .env.")
        print("  Картинка и кнопка в письме будут вести на localhost и у получателя не откроются.")
        print("  Пропишите в .env адрес, по которому сервис доступен из интернета, и повторите.")
        print()

    image_url = _ensure_image(base_url)
    document = build_document(image_url, base_url)
    html = build_html(image_url, base_url)

    if not apply:
        print(f"Шаблон: {TEMPLATE_NAME}")
        print(f"Адрес сервиса: {base_url}")
        print(f"Картинка: {image_url}")
        print()
        print("JSON для загрузки в редакторе (кнопка загрузки шаблона из файла):")
        print(json.dumps(document, ensure_ascii=False, indent=2))
        print()
        print("Ничего не записано — запустите с --apply, чтобы завести шаблон в сервисе.")
        return 0

    try:
        from cbmail.db.models import MessageTemplate
        from cbmail.db.session import get_sync_engine
        from sqlalchemy import select
        from sqlalchemy.orm import Session as OrmSession
    except Exception as exc:  # noqa: BLE001 — сообщение важнее разбора причины
        print(f"Не удалось подключиться к базе: {exc}")
        return 1

    with OrmSession(get_sync_engine()) as session:
        existing = session.execute(
            select(MessageTemplate).where(MessageTemplate.name == TEMPLATE_NAME)
        ).scalars().first()
        # Обновляем, а не плодим копии: шаблон служебный, и десять одинаковых
        # «Проверок вёрстки» в списке мешают больше, чем помогают.
        if existing is None:
            existing = MessageTemplate(name=TEMPLATE_NAME)
            session.add(existing)
            action = "создан"
        else:
            action = "обновлён"
        existing.mask = html
        existing.mask_json = json.dumps(document, ensure_ascii=False)
        session.commit()
        print(f"Шаблон «{TEMPLATE_NAME}» {action}, id={existing.id}")

    print("Теперь: Кампании -> новая кампания -> выберите этот шаблон -> отправьте себе.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
