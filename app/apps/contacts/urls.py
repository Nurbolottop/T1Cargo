from django.urls import path

from . import views

urlpatterns = [
    path("manager/login/", views.manager_login, name="manager_login"),
    path("manager/logout/", views.manager_logout, name="manager_logout"),
    path("manager/", views.manager_dashboard, name="manager_dashboard"),
    path("manager/clients/", views.manager_clients, name="manager_clients"),
    path("manager/clients/<int:user_id>/", views.manager_client_detail, name="manager_client_detail"),
    path("manager/shipments/", views.manager_shipments, name="manager_shipments"),
    path("manager/shipments/import/", views.manager_shipments_import, name="manager_shipments_import"),
    path("manager/shipments/new/", views.manager_shipment_new, name="manager_shipment_new"),
    path("manager/shipments/<int:shipment_id>/", views.manager_shipment_detail, name="manager_shipment_detail"),
]
