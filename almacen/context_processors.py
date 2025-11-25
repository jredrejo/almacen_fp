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
            # If no Persona exists, show no aulas for non-staff users
            aulas = (
                Aula.objects.order_by("nombre")
                if request.user.is_staff
                else Aula.objects.none()
            )
    else:
        # Anonymous users see no aulas
        aulas = Aula.objects.none()

    return {"ctx_current_aula": current, "ctx_all_aulas": aulas}
