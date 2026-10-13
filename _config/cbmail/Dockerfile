FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq5 нужен psycopg (синхронный движок Celery-воркера и init_session).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Зависимости — отдельным слоем, чтобы не переустанавливались при правке кода.
COPY app/pyproject.toml /app/pyproject.toml
COPY app/cbmail /app/cbmail
RUN pip install .

# Оформление интерфейса. Раньше его в образе не было вовсе: на старом сервере
# каталог со статикой остался от Django-версии и подключался томом. На новом
# сервере том пустой — страницы отдавались голой разметкой без единого стиля, и
# выглядело это как сломанный сервис, хотя приложение работало.
#
# Поэтому статика едет внутри образа: она меняется вместе с кодом и обязана
# обновляться вместе с ним, а не жить отдельной жизнью в томе.
COPY _static /app/_static

COPY _config/cbmail/entrypoint-web.sh /app/entrypoint-web.sh
COPY _config/cbmail/entrypoint-worker.sh /app/entrypoint-worker.sh
RUN chmod +x /app/entrypoint-web.sh /app/entrypoint-worker.sh

EXPOSE 8000
