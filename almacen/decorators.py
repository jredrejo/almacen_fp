# almacen/decorators.py
from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse


def user_in_group_profesores(user) -> bool:
    return user.is_authenticated and user.groups.filter(name="ProfesoresFP").exists()


def profesores_required(view_func):
    """
    Requiere:
      - usuario autenticado
      - que pertenezca al grupo 'ProfesoresFP'.

    No da acceso al admin ni toca is_staff; solo controla estas vistas.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Redirige al login si no está autenticado
            login_url = reverse("account_login")  # o el que uses
            return redirect(f"{login_url}?next={request.path}")

        if not user_in_group_profesores(request.user):
            # Usuario logado pero sin permisos -> 403
            return HttpResponseForbidden(
                "No tienes permisos para acceder a esta página."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view
