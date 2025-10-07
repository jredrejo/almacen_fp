from django.db.models import Q
from .models import Producto


def filter_inventory(qs, q: str | None):
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q)
            | Q(epc__icontains=q)
            | Q(n_serie__icontains=q)
            | Q(descripcion__icontains=q)
        )
    return qs.select_related("aula", "ubicacion")  # removed aula__taller
