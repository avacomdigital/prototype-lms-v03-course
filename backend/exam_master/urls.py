from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"status": "ok", "service": "avacom-ops-master"})


urlpatterns = [
    path("health/", health),
    path("api/", include("exams.urls")),
]

