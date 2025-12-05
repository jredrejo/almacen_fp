from django.contrib import admin
from .models import Aula, Producto, Ubicacion, Prestamo, Persona


@admin.register(Aula)
class AulaAdmin(admin.ModelAdmin):
    list_display = ("id","nombre")
    search_fields = ("nombre",)


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("user", "get_user_email", "get_user_staff", "last_aula")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("aulas_access", "user__is_staff")
    filter_horizontal = ("aulas_access",)

    def get_user_email(self, obj):
        return obj.user.email

    get_user_email.short_description = "Email"  # type: ignore[attr-defined]

    def get_user_staff(self, obj):
        return obj.user.is_staff

    get_user_staff.short_description = "Staff?"  # type: ignore[attr-defined]
    get_user_staff.boolean = True  # type: ignore[attr-defined]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


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
