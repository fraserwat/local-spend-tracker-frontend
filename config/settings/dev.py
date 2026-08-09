from .base import *  # noqa: F403
from .base import env

DEBUG = True

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-secret-key-not-for-prod")

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
