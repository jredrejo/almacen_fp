from .models import Aula, Persona
from .views import get_current_aula


def aula_context(request):
    current = get_current_aula(request)

    # Filter aulas based on user permissions
    if request.user.is_authenticated:
        try:
            persona = request.user.persona
            aulas = persona.get_aulas_access().order_by("nombre")
        except Persona.DoesNotExist:
            # If no Persona exists, show all aulas (fallback)
            aulas = Aula.objects.order_by("nombre")
    else:
        # Anonymous users see all aulas (though they shouldn't have access)
        aulas = Aula.objects.order_by("nombre")

    return {"ctx_current_aula": current, "ctx_all_aulas": aulas}
