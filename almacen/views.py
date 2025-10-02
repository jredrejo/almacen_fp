from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ProductoForm, UbicacionShelfForm
from .models import Aula, Producto, Ubicacion
from .htmx import hx_redirect

TEACHERS_GROUP = "ProfesoresFP"


def is_teacher(user):
    return user.is_authenticated and user.groups.filter(name=TEACHERS_GROUP).exists()


@login_required
def dashboard(request):
    aulas = Aula.objects.all().order_by("nombre")
    productos = Producto.objects.select_related("aula").all()[:10]
    return render(request, "store/dashboard.html", {"aulas": aulas, "productos": productos})


teacher_required = user_passes_test(is_teacher, login_url="/accounts/login/")


@login_required
def inventory(request):
    q = request.GET.get("q", "").strip()
    aula_id = request.GET.get("aula", "")
    qs = Producto.objects.select_related("aula")
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(epc__icontains=q) | Q(n_serie__icontains=q))
    if aula_id:
        qs = qs.filter(aula_id=aula_id)
    qs = qs.order_by("nombre")
    aulas = Aula.objects.all()
    ctx = {"productos": qs, "aulas": aulas, "q": q, "aula_id": aula_id}
    return render(request, "store/inventory.html", ctx)


@login_required
def product_row(request, pk):
    prod = get_object_or_404(Producto.objects.select_related("aula"), pk=pk)
    return render(request, "store/_product_row.html", {"p": prod})


@teacher_required
def product_create(request):
    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            p = form.save()
            Ubicacion.objects.create(
                producto=p,
                tipo=Ubicacion.Tipo.ESTANTERIA,
                aula=p.aula,
                estanteria=p.estanteria,
                posicion=p.posicion,
            )
            messages.success(request, "Producto creado.")
            if request.htmx:
                return hx_redirect("/store/inventario/")
            return redirect("inventory")
    else:
        form = ProductoForm()
    return render(request, "store/product_form.html", {"form": form, "crear": True})


@teacher_required
def product_edit(request, pk):
    p = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES, instance=p)
        if form.is_valid():
            p = form.save()
            messages.success(request, "Producto actualizado.")
            if request.htmx:
                return render(request, "store/_product_row.html", {"p": p})
            return redirect("inventory")
    else:
        form = ProductoForm(instance=p)
    return render(request, "store/product_form.html", {"form": form, "crear": False, "p": p})


@teacher_required
def product_delete(request, pk):
    p = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        p.delete()
        messages.success(request, "Producto eliminado.")
        if request.htmx:
            return HttpResponse(status=204)  # HTMX will remove row
        return redirect("inventory")
    raise Http404()


@login_required
def checkouts(request):
    """Quick glance of people who have taken a product."""
    productos = (
        Producto.objects.select_related("aula", "holder")
        .filter(holder__isnull=False)
        .order_by("holder_desde")
    )
    return render(request, "store/checkouts.html", {"productos": productos})


@teacher_required
def locations(request):
    """Table of Ubicacion events (where the products are / have been)."""
    ubic = Ubicacion.objects.select_related("producto", "persona", "aula").all()[:500]
    form = UbicacionShelfForm()
    return render(request, "store/locations.html", {"ubicaciones": ubic, "form": form})


@login_required
def checkout_take(request, pk):
    """Mark product as taken by current user (e.g., swipe person RFID, then product EPC)."""
    p = get_object_or_404(Producto, pk=pk)
    if p.holder_id:
        messages.error(request, "El producto ya está en préstamo.")
        return redirect("inventory")
    p.holder = request.user
    p.holder_desde = timezone.now()
    p.save(update_fields=["holder", "holder_desde"])
    Ubicacion.objects.create(
        producto=p, tipo=Ubicacion.Tipo.PRESTAMO, aula=p.aula, persona=request.user
    )
    messages.success(request, "Prestamo registrado.")
    return redirect("checkouts")


@login_required
def checkout_return(request, pk):
    p = get_object_or_404(Producto, pk=pk)
    if not p.holder_id:
        messages.error(request, "Ese producto no estaba en préstamo.")
        return redirect("inventory")
    p.holder = None
    p.holder_desde = None
    p.save(update_fields=["holder", "holder_desde"])
    Ubicacion.objects.create(
        producto=p,
        tipo=Ubicacion.Tipo.ESTANTERIA,
        aula=p.aula,
        estanteria=p.estanteria,
        posicion=p.posicion,
    )
    messages.success(request, "Producto devuelto.")
    return redirect("inventory")
