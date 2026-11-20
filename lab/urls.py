from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("choose-center/", views.choose_center, name="choose_center"),
    path("patients/", views.patient_list, name="patient_list"),
    path("patients/new/", views.patient_create, name="patient_create"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/new/", views.order_create, name="order_create"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("orders/<int:order_id>/report/", views.order_report, name="order_report"),
]
