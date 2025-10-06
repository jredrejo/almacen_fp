from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import ProductoForm, UbicacionInlineForm
from .models import Producto, Ubicacion, Prestamo
from .tables import filter_inventory


def is_teacher(user):
    return user.is_authenticated and user.groups.filter(name="ProfesoresFP").exists()


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
    """HTMX fragment to update a single row after edits/deletes."""
    producto = get_object_or_404(
        Producto.objects.select_related(
            "ubicacion",
        ),
        pk=pk,
    )
    return render(request, "almacen/_product_row.partial.html", {"p": producto})


@login_required
@user_passes_test(is_teacher)
def producto_create(request):
    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            p = form.save()
            # create initial Ubicacion
            Ubicacion.objects.create(
                producto=p,
                estado="ESTANTE",
                aula=p.aula,
                estanteria=p.estanteria,
                posicion=p.posicion,
            )
            messages.success(request, "Producto creado.")
            return redirect("almacen:inventory")
    else:
        form = ProductoForm()
    return render(request, "almacen/producto_create.html", {"form": form})


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
                return inventory_row(request, p.pk)
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
    """
    If product is on shelf -> mark as taken by current user.
    If product is in person's hands -> if it's you, return to shelf (using product's aula/estanteria/posicion).
    Teachers can toggle for anyone.
    """
    producto = get_object_or_404(
        Producto.objects.select_related(
            "ubicacion",
        ),
        pk=pk,
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
            u.estanteria = producto.estanteria
            u.posicion = producto.posicion
            u.aula = producto.aula
            u.save()
            # close latest loan
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
