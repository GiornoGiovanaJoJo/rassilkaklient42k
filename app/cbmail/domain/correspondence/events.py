"""Типы событий журнала корреспонденции.

Запись журнала хранится в таблице ``cbmail_correspondence_event`` (см. models),
а здесь — только перечень типов, общий для домена и сервиса, чтобы строковые
значения не расходились по коду.
"""

from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    REGISTERED = "registered"            # присвоен регистрационный номер
    SENT = "sent"                        # письмо отправлено
    DELIVERY_FAILED = "delivery_failed"  # ошибка доставки
    DELIVERED = "delivered"              # подтверждена доставка
    REPLY_LINKED = "reply_linked"        # входящий ответ привязан к исходному
    DEADLINE_SET = "deadline_set"        # установлен срок ответа
    DEADLINE_BREACHED = "deadline_breached"  # срок нарушен
    CONTACT_MATCHED = "contact_matched"  # привязка к карточке контрагента
