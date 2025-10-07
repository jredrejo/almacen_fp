from django.urls import path
from . import views

app_name = "almacen"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inventario/", views.inventory, name="inventory"),
    path("inventario/row/<int:pk>/", views.inventory_row, name="inventory_row"),  # HTMX
    path("producto/nuevo/", views.producto_create, name="producto_create"),
    path("producto/<int:pk>/editar/", views.producto_edit, name="producto_edit"),
    path("producto/<int:pk>/eliminar/", views.producto_delete, name="producto_delete"),
    path("prestamos/", views.prestamos_overview, name="prestamos_overview"),
    path("toggle-prestamo/<int:pk>/", views.toggle_prestamo, name="toggle_prestamo"),
    path("aulas/", views.aulas_list_create, name="aulas"),
    path("set-aula/", views.set_current_aula, name="set_current_aula"),
    path("producto/nuevo/", views.producto_create, name="producto_create"),
    path("get-latest-epc/", views.get_latest_epc, name="get_latest_epc"),
]
