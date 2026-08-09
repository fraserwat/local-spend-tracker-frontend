from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model, wired via AUTH_USER_MODEL from commit #1.

    Deliberately empty for now — no login flow exists yet (MVP is public,
    read-only, no auth). Exists so magic-link fields can be added later as
    an additive migration, since swapping AUTH_USER_MODEL after other
    migrations reference it is a costly retrofit in Django.
    """
