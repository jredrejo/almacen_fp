from django.contrib import admin
from .models import Aula, Producto, Ubicacion, Prestamo


@admin.register(Aula)
class AulaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


class UbicacionInline(admin.StackedInline):
    model = Ubicacion
    extra = 0


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "epc", "aula", "estanteria", "posicion", "cantidad")
    search_fields = ("nombre", "epc", "n_serie")
    list_filter = ("aula",)
    inlines = [UbicacionInline]


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ("producto", "usuario", "tomado_en", "devuelto_en")
    list_filter = ("usuario", "producto")
