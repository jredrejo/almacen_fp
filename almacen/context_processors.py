from .models import Aula
from .views import get_current_aula


def aula_context(request):
    current = get_current_aula(request)
    aulas = Aula.objects.order_by("nombre")
    return {"ctx_current_aula": current, "ctx_all_aulas": aulas}
