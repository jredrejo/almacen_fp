"""Decoradores de autenticacion para la API REST."""
import functools
import hmac
from typing import Callable

from django.conf import settings
from django.http import JsonResponse


def require_api_key(view_func: Callable) -> Callable:
    """
    Decorador que requiere API key valida en el header Authorization.

    Formato esperado: Authorization: ApiKey {clave}

    Usa hmac.compare_digest() para evitar timing attacks.

    Args:
        view_func: La vista a proteger

    Returns:
        La vista envuelta con verificacion de API key
    """

    @functools.wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Extraer header Authorization
        auth_header = request.headers.get("Authorization", "")

        # Verificar que empieza con "ApiKey "
        if not auth_header.startswith("ApiKey "):
            return JsonResponse({"error": "API key requerida"}, status=401)

        # Extraer la clave despues de "ApiKey " (7 caracteres)
        provided_key = auth_header[7:]

        # Si API_KEY esta vacio en settings, rechazar siempre
        if not settings.API_KEY:
            return JsonResponse({"error": "API key invalida"}, status=401)

        # Comparar con hmac.compare_digest para evitar timing attacks
        if not hmac.compare_digest(provided_key, settings.API_KEY):
            return JsonResponse({"error": "API key invalida"}, status=401)

        # API key valida, permitir acceso
        return view_func(request, *args, **kwargs)

    return _wrapped_view
