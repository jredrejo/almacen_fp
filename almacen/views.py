from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Producto, Ubicacion, Prestamo, Aula, Persona
from .forms import ProductoForm, UbicacionInlineForm, AulaForm

from .tables import filter_inventory


def is_teacher(user):
    return user.is_authenticated and user.groups.filter(name="ProfesoresFP").exists()


def get_current_aula(request):
    """Priority: GET ?aula -> session -> user's Persona.last_aula."""
    aula_id = request.GET.get("aula")
    if aula_id:
        try:
            return Aula.objects.get(pk=aula_id)
        except Aula.DoesNotExist:
            return None
    # session
    sid = request.session.get("current_aula_id")
    if sid:
        try:
            return Aula.objects.get(pk=sid)
        except Aula.DoesNotExist:
            pass
    # user preference
    if request.user.is_authenticated:
        try:
            persona = request.user.persona
            return persona.last_aula  # may be None
        except Persona.DoesNotExist:
            pass
    return None


@login_required
def dashboard(request):
    total = Producto.objects.count()
    en_manos = Ubicacion.objects.filter(estado="PERSONA").count()
    en_estante = total - en_manos
    recientes = Producto.objects.order_by("-creado")[:8]
    ctx = {
        "total": total,
        "en_manos": en_manos,
        "en_estante": en_estante,
        "recientes": recientes,
    }
    return render(request, "almacen/dashboard.html", ctx)


@login_required
def inventory(request):
    qs = filter_inventory(Producto.objects.all(), request.GET.get("q"))
    ctx = {"productos": qs, "q": request.GET.get("q", "")}
    return render(request, "almacen/inventory.html", ctx)


@login_required
def inventory_row(request, pk: int):
    producto = get_object_or_404(
        Producto.objects.select_related("ubicacion", "aula"), pk=pk
    )
    return render(request, "almacen/_product_row.partial.html", {"p": producto})


from django.contrib import messages


# almacen/views.py
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse


@login_required
@user_passes_test(is_teacher)
def producto_create(request):
    current_aula = get_current_aula(request)
    if not current_aula:
        messages.error(request, "Selecciona primero un aula en el selector del menú.")
        return redirect("almacen:inventory")

    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES, fixed_aula=current_aula)
        if form.is_valid():
            p = form.save(commit=False)
            p.aula = current_aula
            p.save()
            Ubicacion.objects.create(
                producto=p,
                estado="ESTANTE",
                aula=p.aula,
                estanteria=p.estanteria,
                posicion=p.posicion,
            )
            messages.success(request, "Producto creado correctamente.")
            action = request.POST.get("action", "new")
            return redirect(
                "almacen:inventory" if action == "list" else "almacen:producto_create"
            )
    else:
        form = ProductoForm(fixed_aula=current_aula)

    return render(
        request,
        "almacen/producto_create.html",
        {"form": form, "current_aula": current_aula},
    )


@login_required
@user_passes_test(is_teacher)
def producto_edit(request, pk: int):
    p = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES, instance=p)
        if form.is_valid():
            p = form.save()
            # keep Ubicacion shelf info in sync if on ESTANTE
            try:
                u = p.ubicacion
                if u.estado == "ESTANTE":
                    u.aula = p.aula
                    u.estanteria = p.estanteria
                    u.posicion = p.posicion
                    u.save()
            except Ubicacion.DoesNotExist:
                pass
            messages.success(request, "Producto actualizado.")
            if request.htmx:
                resp = HttpResponse(status=204)
                resp["HX-Redirect"] = reverse("almacen:inventory")
                return resp
            return redirect("almacen:inventory")
    else:
        form = ProductoForm(instance=p)
    return render(request, "almacen/producto_create.html", {"form": form, "edit": True})


@login_required
@user_passes_test(is_teacher)
def producto_delete(request, pk: int):
    p = get_object_or_404(Producto, pk=pk)
    p.delete()
    messages.success(request, "Producto eliminado.")
    if request.htmx:
        # HX-Trigger to remove row on client side can be handled by id target
        return HttpResponse("")  # row removed by client via swap:oob or hx-delete
    return redirect("almacen:inventory")


@login_required
def prestamos_overview(request):
    # Who currently has products (Ubicacion.estado=PERSONA)
    ubicaciones = Ubicacion.objects.select_related("producto", "persona").filter(
        estado="PERSONA"
    )
    return render(
        request, "almacen/prestamos_overview.html", {"ubicaciones": ubicaciones}
    )


@login_required
def toggle_prestamo(request, pk: int):
    producto = get_object_or_404(
        Producto.objects.select_related("ubicacion", "aula"), pk=pk
    )
    try:
        u = producto.ubicacion
    except Ubicacion.DoesNotExist:
        u = Ubicacion.objects.create(
            producto=producto, estado="ESTANTE", aula=producto.aula
        )

    if u.estado == "ESTANTE":
        u.estado = "PERSONA"
        u.persona = request.user
        u.tomado_en = timezone.now()
        u.save()
        Prestamo.objects.create(producto=producto, usuario=request.user)
        messages.success(request, "Has tomado el producto.")
    else:
        if u.persona == request.user or is_teacher(request.user):
            u.estado = "ESTANTE"
            u.persona = None
            u.aula = producto.aula
            u.estanteria = producto.estanteria
            u.posicion = producto.posicion
            u.save()
            prestamo = (
                Prestamo.objects.filter(producto=producto, devuelto_en__isnull=True)
                .order_by("-tomado_en")
                .first()
            )
            if prestamo:
                prestamo.devuelto_en = timezone.now()
                prestamo.save()
            messages.success(request, "Producto devuelto al estante.")
        else:
            return HttpResponseBadRequest(
                "No puedes devolver un producto que no tienes."
            )
    if request.htmx:
        return inventory_row(request, producto.pk)
    return HttpResponseRedirect(reverse("almacen:inventory"))


@login_required
@require_POST
def set_current_aula(request):
    aula_id = request.POST.get("aula_id")
    try:
        aula = Aula.objects.all().get(pk=aula_id)
    except Aula.DoesNotExist:
        messages.error(request, "Aula no encontrada.")
        return redirect(request.META.get("HTTP_REFERER", "almacen:inventory"))
    # session
    request.session["current_aula_id"] = aula.id
    # persist on Persona
    persona, _ = Persona.objects.get_or_create(user=request.user)
    persona.last_aula = aula
    persona.save()
    messages.success(request, f"Aula seleccionada: {aula}")
    # HX: if HTMX, just refresh navbar/inventory; otherwise redirect back
    if request.htmx:
        return redirect("almacen:inventory")
    return redirect(request.META.get("HTTP_REFERER", "almacen:inventory"))


@login_required
def inventory(request):
    current_aula = get_current_aula(request)
    qs = Producto.objects.all()
    if current_aula:
        qs = qs.filter(aula=current_aula)
    qs = filter_inventory(qs, request.GET.get("q"))
    ctx = {
        "productos": qs,
        "q": request.GET.get("q", ""),
        "current_aula": current_aula,
    }
    return render(request, "almacen/inventory.html", ctx)


@login_required
@user_passes_test(is_teacher)
def aulas_list_create(request):
    # Show list + form on same page
    if request.method == "POST":
        form = AulaForm(request.POST)
        if form.is_valid():
            aula = form.save()
            messages.success(request, f"Aula creada: {aula}")
            return redirect("almacen:aulas")
    else:
        form = AulaForm()
    aulas = Aula.objects.all().order_by("nombre")
    return render(request, "almacen/aulas.html", {"form": form, "aulas": aulas})
