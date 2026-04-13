from django.contrib import admin, messages
from django.core.management import call_command
from django.shortcuts import render

from .models import Aula, FotoRFID, LecturaHuerfana, Producto, Ubicacion, Prestamo, Persona


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


@admin.register(FotoRFID)
class FotoRFIDAdmin(admin.ModelAdmin):
    list_display = ("id", "epc", "aula", "timestamp_captura", "subida_en", "tamano_bytes")
    list_filter = ("aula",)
    search_fields = ("epc",)
    readonly_fields = ("subida_en", "tamano_bytes")
    date_hierarchy = "timestamp_captura"
    actions = ["recuperar_fotos_action", "limpiar_fotos_action"]

    def _single_aula_or_error(self, request, queryset):
        aulas = set(queryset.values_list("aula_id", flat=True))
        aulas.discard(None)
        if len(aulas) == 0:
            self.message_user(request, "Selecciona al menos una foto de un aula concreta.", level=messages.ERROR)
            return None
        if len(aulas) > 1:
            self.message_user(request, f"Seleccion cubre {len(aulas)} aulas. Selecciona una sola.", level=messages.ERROR)
            return None
        return str(aulas.pop())

    @admin.action(description="Recuperar fotos del Tab5 (publicar upload_fotos)")
    def recuperar_fotos_action(self, request, queryset):
        aula_id = self._single_aula_or_error(request, queryset)
        if aula_id is None:
            return
        try:
            call_command("recuperar_fotos", aula=aula_id, action="upload")
        except Exception as exc:
            self.message_user(request, f"Fallo al publicar upload_fotos para aula {aula_id}: {exc}", level=messages.ERROR)
            return
        self.message_user(request, f"Publicado upload_fotos para aula {aula_id}.", level=messages.SUCCESS)

    @admin.action(description="Limpiar fotos del Tab5 (BORRA TODA la SD /fotos/)")
    def limpiar_fotos_action(self, request, queryset):
        aula_id = self._single_aula_or_error(request, queryset)
        if aula_id is None:
            return
        if request.POST.get("confirm") != "yes":
            return render(request, "admin/almacen/fotorfid/limpiar_confirm.html", {
                "title": "Confirmar limpieza destructiva",
                "aula_id": aula_id,
                "foto_count": queryset.count(),
                "selected_ids": queryset.values_list("pk", flat=True),
                "action_name": "limpiar_fotos_action",
            })
        try:
            call_command("recuperar_fotos", aula=aula_id, action="limpiar")
        except Exception as exc:
            self.message_user(request, f"Fallo al publicar limpiar_fotos para aula {aula_id}: {exc}", level=messages.ERROR)
            return
        self.message_user(request, f"Publicado limpiar_fotos para aula {aula_id}. /fotos/ sera borrado.", level=messages.WARNING)


@admin.register(LecturaHuerfana)
class LecturaHuerfanaAdmin(admin.ModelAdmin):
    list_display = ("epc", "aula_id", "timestamp", "created_at")
    list_filter = ("aula_id", "timestamp")
    search_fields = ("epc",)
    readonly_fields = ("epc", "timestamp", "aula_id", "created_at")
    ordering = ("-timestamp",)
