"""Vistas de la API REST para resolucion EPC-a-nombre."""
import json
import re
from typing import Any

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from almacen.api_auth import require_api_key
from almacen.models import Persona, Producto

# Patrón para validar formato de EPC (solo caracteres hexadecimales)
EPC_PATTERN = re.compile(r"^[A-Fa-f0-9]+$")


def _resolve_epc(epc: str) -> dict[str, Any] | None:
    """
    Resuelve un codigo EPC a su informacion correspondiente.

    Busca primero en Producto, luego en Persona.

    Args:
        epc: Codigo EPC a resolver

    Returns:
        Diccionario con la informacion del EPC o None si no existe
    """
    try:
        # Buscar producto
        producto = Producto.objects.select_related("aula").get(epc=epc)
        prestamo = producto.current_prestamo

        return {
            "epc": epc,
            "type": "producto",
            "nombre": producto.nombre,
            "aula": producto.aula.nombre,
            "prestado": producto.is_taken,
            "prestado_a": (
                str(prestamo.usuario.get_full_name() or prestamo.usuario.username)
                if prestamo and prestamo.usuario
                else None
            ),
        }
    except Producto.DoesNotExist:
        pass

    try:
        # Buscar persona
        persona = Persona.objects.select_related("user").get(epc=epc)
        return {
            "epc": epc,
            "type": "persona",
            "nombre": persona.user.get_full_name() or persona.user.email,
        }
    except Persona.DoesNotExist:
        pass

    return None


@require_GET
@require_api_key
def epc_lookup(request, epc: str) -> JsonResponse:
    """
    Endpoint para resolucion individual de EPC.

    GET /api/epc/{epc}/

    Retorna informacion del producto o persona asociado al EPC.
    """
    # Validar formato de EPC
    if not EPC_PATTERN.match(epc):
        return JsonResponse(
            {"error": "Formato EPC invalido", "epc": epc}, status=400
        )

    # Resolver EPC
    result = _resolve_epc(epc)

    if result is None:
        return JsonResponse({"error": "EPC no encontrado", "epc": epc}, status=404)

    return JsonResponse(result)


@csrf_exempt
@require_api_key
@require_http_methods(["POST"])
def epc_bulk_lookup(request) -> JsonResponse:
    """
    Endpoint para resolucion masiva de EPCs.

    POST /api/epc/
    Body: {"epcs": ["EPC1", "EPC2", ...]}

    Retorna resultados para todos los EPCs, incluyendo errores.
    Maximo 50 EPCs por peticion.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalido"}, status=400)

    # Validar que epcs existe y es una lista
    epcs = body.get("epcs")
    if not isinstance(epcs, list):
        return JsonResponse(
            {"error": "El campo 'epcs' debe ser una lista"}, status=400
        )

    # Validar limite de 50 EPCs
    if len(epcs) > 50:
        return JsonResponse(
            {"error": "Maximo 50 EPCs por peticion", "enviados": len(epcs)},
            status=400,
        )

    results = []
    for epc in epcs:
        if not isinstance(epc, str):
            results.append({"epc": str(epc), "error": "EPC debe ser string"})
            continue

        # Validar formato
        if not EPC_PATTERN.match(epc):
            results.append({"epc": epc, "error": "Formato EPC invalido"})
            continue

        # Resolver EPC
        result = _resolve_epc(epc)
        if result is None:
            results.append({"epc": epc, "error": "EPC no encontrado"})
        else:
            results.append(result)

    return JsonResponse({"results": results})
