"""Канцелярия: список корреспонденции и карточка письма с журналом событий.

Раздел доступен только при включённом флаге ``correspondence_enabled`` — иначе
маршруты уводят на рассылки, а пункт меню не показывается. Это даёт «одинаковый
по функционалу» продукт: установка с канцелярией видит нумерацию и трекинг,
установка обычной рассылки — нет, из одного кода.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cbmail.core.config import get_settings
from cbmail.db.models import Correspondence, CorrespondenceEvent
from cbmail.domain.correspondence.deadlines import DeadlineStatus
from cbmail.web.deps import get_db, redirect, require_user
from cbmail.web.pagination import Page, offset, parse_page

router = APIRouter(prefix="/correspondence")

_PER_PAGE = 30


def _enabled() -> bool:
    return get_settings().correspondence_enabled


@router.get("/")
async def list_correspondence(
    request: Request,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if not _enabled():
        return redirect("/campaigns/", err="Раздел «Корреспонденция» выключен.")

    page_no = parse_page(request.query_params.get("page"))
    status = (request.query_params.get("status") or "").strip()

    where = []
    if status in {s.value for s in DeadlineStatus}:
        where.append(Correspondence.deadline_status == status)

    total = (
        await db.execute(select(func.count()).select_from(Correspondence).where(*where))
    ).scalar() or 0
    rows = await db.execute(
        select(Correspondence)
        .where(*where)
        .order_by(Correspondence.created_at.desc())
        .offset(offset(page_no, _PER_PAGE))
        .limit(_PER_PAGE)
    )
    page = Page(items=list(rows.scalars()), page=page_no, per_page=_PER_PAGE, total=total)

    # Счётчики по статусам сроков — для плашек-фильтров.
    counts = dict(
        (
            await db.execute(
                select(Correspondence.deadline_status, func.count()).group_by(
                    Correspondence.deadline_status
                )
            )
        ).all()
    )
    return render_correspondence(request, page, counts, status)


@router.get("/{corr_id}")
async def correspondence_detail(
    corr_id: int,
    request: Request,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if not _enabled():
        return redirect("/campaigns/", err="Раздел «Корреспонденция» выключен.")

    record = (
        await db.execute(select(Correspondence).where(Correspondence.id == corr_id))
    ).scalar_one_or_none()
    if record is None:
        return redirect("/correspondence/", err="Письмо не найдено.")

    events = (
        await db.execute(
            select(CorrespondenceEvent)
            .where(CorrespondenceEvent.tracking_id == record.tracking_id)
            .order_by(CorrespondenceEvent.at.asc())
        )
    ).scalars().all()

    # Разворачиваем JSON payload для показа в журнале.
    rows = []
    for e in events:
        try:
            payload = json.loads(e.payload) if e.payload else {}
        except ValueError:
            payload = {}
        rows.append((e, payload))

    from cbmail.web.templating import render

    return render(
        request,
        "correspondence/detail.html",
        {"corr": record, "events": rows},
    )


def render_correspondence(request: Request, page: Page, counts: dict, status: str):
    from cbmail.web.templating import render

    return render(
        request,
        "correspondence/list.html",
        {"page": page, "counts": counts, "active_status": status},
    )
