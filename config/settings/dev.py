from .base import *  # noqa: F403
from .base import BASE_DIR, env

DEBUG = True

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-secret-key-not-for-prod")

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Local dev convenience only -- prod.py has no default, so a forgotten
# env var there fails loudly instead of resolving to a bogus path.
SPEND_SOURCE_DIR = env(
    "SPEND_SOURCE_DIR",
    default=str(BASE_DIR.parent / "local-big-con-nationwide" / "data" / "curated"),
)
