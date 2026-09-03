from .base import *  # noqa: F403
from .base import BASE_DIR, env

DEBUG = True

# `or` (not just `default=`) so a DJANGO_SECRET_KEY present but blank in
# .env -- e.g. .env.example copied verbatim, its "fill in" line left as-is
# -- still falls back here. django-environ's default= only fires when the
# var is unset, not when it's set to "", so without this a blank key
# reaches Django as "" and every request 500s on ImproperlyConfigured.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="") or "dev-insecure-secret-key-not-for-prod"

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Sibling data repo's curated parquet output, for local dev convenience only.
# No equivalent default in prod.py — a forgotten --source-dir/env var there
# must fail loudly, not silently resolve to a path that won't exist.
SPEND_SOURCE_DIR = env(
    "SPEND_SOURCE_DIR",
    default=str(BASE_DIR.parent / "local-big-con-nationwide" / "data" / "curated"),
)
