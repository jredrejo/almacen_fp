"""URL configuration for the API REST."""
from django.urls import path
from almacen import api

urlpatterns = [
    path("epc/<str:epc>/", api.epc_lookup, name="api_epc_lookup"),
    path("epc/", api.epc_bulk_lookup, name="api_epc_bulk_lookup"),
]
