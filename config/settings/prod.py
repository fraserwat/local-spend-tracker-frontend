from django.core.exceptions import ImproperlyConfigured
from whitenoise.storage import CompressedManifestStaticFilesStorage

from .base import *  # noqa: F403
from .base import REST_FRAMEWORK, env

DEBUG = False

# No default: a missing secret key must fail startup, not silently run insecure.
SECRET_KEY = env("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Fly terminates TLS at its edge and forwards plain HTTP internally with
# X-Forwarded-Proto set -- without this, is_secure() never returns True and
# SECURE_SSL_REDIRECT redirect-loops every request.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Fly's health check hits /healthz directly over the internal network,
# bypassing the edge entirely (no X-Forwarded-Proto) -- redirect it to
# https would just make the checker see a 301 instead of the 200 it wants.
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = "DENY"


class StaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Manifest storage, minus the "*.js" sourceMappingURL rewrite.

    Vendored leaflet.js references a .map file we don't ship; the default
    rewrite hard-fails collectstatic over that missing target otherwise.
    """

    patterns = (
        (
            "*.css",
            (
                r"""(?P<matched>url\(['"]{0,1}\s*(?P<url>.*?)["']{0,1}\))""",
                (
                    r"""(?P<matched>@import\s*["']\s*(?P<url>.*?)["'])""",
                    """@import url("%(url)s")""",
                ),
                (
                    (
                        r"(?m)^(?P<matched>/\*#[ \t]"
                        r"(?-i:sourceMappingURL)=(?P<url>.*)[ \t]*\*/)$"
                    ),
                    "/*# sourceMappingURL=%(url)s */",
                ),
            ),
        ),
    )


# Content-hashed filenames (safe far-future Cache-Control: immutable) plus
# gzip/brotli variants pre-built at collectstatic time.
STORAGES = {
    "staticfiles": {
        "BACKEND": "config.settings.prod.StaticFilesStorage",
    },
}

# Public data API: disable the browsable API's HTML form UI in prod, JSON only.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
