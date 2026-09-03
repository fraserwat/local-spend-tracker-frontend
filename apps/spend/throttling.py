from rest_framework.throttling import AnonRateThrottle


class ExportRateThrottle(AnonRateThrottle):
    """IP-based rate limit on CSV export, since there's no auth to key a
    limit on otherwise (docs/ARCHITECTURE.md's security plan).

    One class, used by both the HTML view (via `.allow_request()` called
    directly) and the API's export APIView (via `throttle_classes`) --
    same cache key, same 429 behavior, regardless of entry point.
    """

    scope = "export"
