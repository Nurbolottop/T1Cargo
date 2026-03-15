from apps.base.models import Settings, Filial
from apps.base.payment_models import PaymentDetails
import logging

logger = logging.getLogger(__name__)


def site_settings(request):
    """Add site settings and payment details to template context."""
    context = {"settings": None, "payment_details": None, "all_payment_details": []}
    
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
            filial = None
            is_director = False
            
            if hasattr(user, 'staff') and user.staff and user.staff.filial:
                # Для staff берем филиал из профиля
                filial = user.staff.filial
            elif user.is_superuser:
                # Для суперпользователя берем первый активный филиал
                filial = Filial.objects.filter(is_active=True).first()
            elif hasattr(user, 'userssh') and user.userssh:
                # Для пользователей с userssh (включая директоров)
                try:
                    from apps.telegram_bot import models as tg_models
                    role = user.userssh.role
                    logger.info(f"User {user.username} has role: {role}")
                    if role == tg_models.UsersSH.Role.DIRECTOR:
                        is_director = True
                        # Для директора показываем все филиалы
                        all_filials = Filial.objects.filter(is_active=True)
                        all_payments = []
                        for f in all_filials:
                            payment = PaymentDetails.objects.filter(
                                filial=f, is_active=True
                            ).order_by('-is_primary', '-created_at').first()
                            if payment:
                                all_payments.append(payment)
                        context["all_payment_details"] = all_payments
                        # Берем первый для совместимости
                        filial = all_filials.first()
                        logger.info(f"Director all filials: {all_filials.count()}, payments: {len(all_payments)}")
                except Exception as e:
                    logger.error(f"Error checking director role: {e}")
                    filial = None
            
            if filial and not is_director:
                # Ищем основные реквизиты или первые активные
                payment = PaymentDetails.objects.filter(
                    filial=filial, is_active=True
                ).order_by('-is_primary', '-created_at').first()
                context["payment_details"] = payment
                logger.info(f"Payment details for {user.username}: {payment}")
            elif filial and is_director:
                # Для директора берем первые реквизиты для совместимости
                payment = PaymentDetails.objects.filter(
                    filial=filial, is_active=True
                ).order_by('-is_primary', '-created_at').first()
                context["payment_details"] = payment
    except Exception as e:
        logger.error(f"Error in site_settings: {e}")
    
    return context
