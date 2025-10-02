from django.contrib import admin
from .models import Aula, Producto, Ubicacion


@admin.register(Aula)
class AulaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo")
    search_fields = ("nombre", "codigo")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "epc", "aula", "estanteria", "posicion", "cantidad", "holder")
    search_fields = ("nombre", "epc", "n_serie", "descripcion")
    list_filter = ("aula",)


@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ("producto", "tipo", "aula", "estanteria", "posicion", "persona", "fecha")
    list_filter = ("tipo", "aula")
    search_fields = ("producto__nombre", "producto__epc", "persona__username")
