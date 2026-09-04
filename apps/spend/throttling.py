from rest_framework.throttling import AnonRateThrottle


class ExportRateThrottle(AnonRateThrottle):
    """IP-based rate limit on CSV export -- no auth to key a limit on
    otherwise. Shared by the HTML view and the API's export APIView, so
    both get the same cache key/429 behavior.
    """

    scope = "export"
