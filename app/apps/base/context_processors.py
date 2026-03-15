from apps.base.models import Settings, Filial
from apps.base.payment_models import PaymentDetails


def site_settings(request):
    """Add site settings and payment details to template context."""
    context = {"settings": None, "payment_details": None}
    
    try:
        settings_obj = Settings.objects.first()
        if settings_obj:
            context["settings"] = settings_obj
    except Exception:
        pass
    
    # Получаем реквизиты для филиала пользователя
    try:
        user = request.user
        if user.is_authenticated:
            if hasattr(user, 'staff') and user.staff and user.staff.filial:
                # Для staff берем филиал из профиля
                filial = user.staff.filial
            elif user.is_superuser:
                # Для суперпользователя берем первый активный филиал
                filial = Filial.objects.filter(is_active=True).first()
            else:
                filial = None
            
            if filial:
                # Ищем основные реквизиты или первые активные
                payment = PaymentDetails.objects.filter(
                    filial=filial, is_active=True
                ).order_by('-is_primary', '-created_at').first()
                context["payment_details"] = payment
    except Exception:
        pass
    
    return context
