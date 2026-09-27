"""Shared Django bootstrap for standalone scripts run outside manage.py.

Each script needs its own repo-root sys.path entry and settings module set
before any apps.*/django.* import -- collapsed here so scripts/*.py don't
each hand-copy the same four lines.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def setup_django() -> None:
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    import django

    django.setup()
