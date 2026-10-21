"""Канцелярия: нумерация и трекинг корреспонденции поверх рассылки.

Чистая доменная логика (без БД и сети), общая для веб-приложения и возможного
локального коннектора:

* :mod:`numbering`   — автонумерация писем;
* :mod:`contacts`    — привязка к карточке контрагента по email;
* :mod:`deadlines`   — сроки ответа и их статусы;
* :mod:`reply_link`  — мета-ссылка и связывание ответа с исходным письмом;
* :mod:`events`      — типы событий журнала.

Включается флагом ``correspondence_enabled``. Хранение и интеграция с отправкой —
в :mod:`cbmail.services.correspondence`.
"""

from __future__ import annotations

__all__ = ["contacts", "deadlines", "events", "numbering", "reply_link"]
