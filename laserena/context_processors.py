from django.conf import settings


def administracion(request):
    return {"phpmyadmin_url": settings.PHPMYADMIN_URL}
