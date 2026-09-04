FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/code/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /usr/local/bin/

WORKDIR /code

COPY pyproject.toml uv.lock /code/
RUN uv sync --locked --no-dev --no-install-project

COPY . /code

RUN uv sync --locked --no-dev

# collectstatic needs settings to import cleanly (SECRET_KEY has no
# default in prod.py) but never touches the database -- a placeholder
# value here is fine, it's discarded once the image is built.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=collectstatic-build-only-not-used-at-runtime \
    DJANGO_ALLOWED_HOSTS=collectstatic.invalid \
    python manage.py collectstatic --noinput

EXPOSE 8000

# --timeout: gunicorn's sync worker only checks in with the arbiter between
# requests, not mid-response -- a single request (the streaming CSV export,
# up to CSV_EXPORT_ROW_CAP=500,000 rows) that runs longer than this gets
# its worker killed mid-stream, truncating the response with a *silent*
# HTTP 200 instead of an error. Measured live against Croydon's real
# 1,048,125-row dataset on a shared-cpu-1x machine: the full 500K-row
# export takes just over 300s end to end (~1,600 rows/sec, Neon is an
# external network hop, not localhost) -- 600s is real headroom above the
# measured worst case, not a guess.
# --workers: 3, not 2 -- a multi-minute export legitimately holds one
# worker for the duration; 2 workers means a single concurrent export
# request could leave only one worker for every other visitor on the site.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "600"]
