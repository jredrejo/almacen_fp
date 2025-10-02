from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inventario/", views.inventory, name="inventory"),
    path("inventario/row/<int:pk>/", views.product_row, name="product_row"),  # HTMX partial
    path("producto/nuevo/", views.product_create, name="product_create"),
    path("producto/<int:pk>/editar/", views.product_edit, name="product_edit"),
    path("producto/<int:pk>/eliminar/", views.product_delete, name="product_delete"),
    path("prestamos/", views.checkouts, name="checkouts"),
    path("ubicaciones/", views.locations, name="locations"),
    path("prestamo/<int:pk>/tomar/", views.checkout_take, name="checkout_take"),
    path("prestamo/<int:pk>/devolver/", views.checkout_return, name="checkout_return"),
]
