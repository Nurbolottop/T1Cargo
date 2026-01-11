from django.urls import path

from . import views

urlpatterns = [
    path('webapp/register/', views.webapp_register, name='webapp_register'),
    path('webapp/register/filials/', views.webapp_register_filials, name='webapp_register_filials'),
    path('webapp/register/submit/', views.webapp_register_submit, name='webapp_register_submit'),
    path('webapp/profile/', views.webapp_profile, name='webapp_profile'),
    path('webapp/profile/data/', views.webapp_profile_data, name='webapp_profile_data'),
    path('webapp/profile/parcels/', views.webapp_profile_parcels, name='webapp_profile_parcels'),
    path('webapp/profile/addresses/', views.webapp_profile_addresses, name='webapp_profile_addresses'),
    path('webapp/profile/support/', views.webapp_profile_support, name='webapp_profile_support'),
]
