FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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
    uv run --no-dev python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["uv", "run", "--no-dev", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]
