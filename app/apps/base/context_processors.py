from apps.base.models import Settings


def site_settings(request):
    """Add site settings to template context."""
    try:
        settings_obj = Settings.objects.first()
        if settings_obj:
            return {"settings": settings_obj}
    except Exception:
        pass
    return {"settings": None}
