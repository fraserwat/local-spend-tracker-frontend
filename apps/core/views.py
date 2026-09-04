from django.db import connection
from django.db.utils import OperationalError
from django.http import JsonResponse


def healthz(request):
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})
