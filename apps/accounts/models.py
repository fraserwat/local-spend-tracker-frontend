from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Deliberately empty -- no auth yet. Exists now so AUTH_USER_MODEL is
    already set before other migrations reference it; swapping it later
    is a costly Django retrofit."""
