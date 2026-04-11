"""Vistas de la API REST para resolucion EPC-a-nombre."""
import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from almacen.api_auth import require_api_key
from almacen.models import Aula, FotoRFID, Persona, Producto

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


# --- Phase 06.1: Tab5 photo upload endpoint (D-01, D-03, D-09, D-10) ---

# Filename format: <EPC>_YYYY-MM-DD_HH-MM-SS[_N].jpg
# EPC: hex, 8-24 chars (matches docs/CONTRACT.md MQTT regex, case-insensitive
# because the Tab5 filename isn't forced-uppercase on the firmware side).
FOTO_FILENAME_RE = re.compile(
    r"^(?P<epc>[0-9A-Fa-f]{8,24})"
    r"_(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})"
    r"(?:_\d+)?\.jpg$"
)

# Europe/Madrid local wall-clock is the origin tz of the filename timestamp.
# See docs/CONTRACT.md "Photo Upload" section and 06.1-RESEARCH.md Pitfall 5.
FOTO_FILENAME_TZ = ZoneInfo("Europe/Madrid")

# Upload size cap enforced in the view (DATA_UPLOAD_MAX_MEMORY_SIZE in settings
# is the Django-level backstop at 10 MB; view cap is identical).
FOTO_MAX_BYTES = 10 * 1024 * 1024

# JPEG magic bytes: every JFIF/Exif JPEG starts with FF D8 FF.
JPEG_MAGIC = b"\xff\xd8\xff"


@csrf_exempt
@require_api_key
@require_http_methods(["POST"])
def upload_foto(request) -> JsonResponse:
    """
    POST /api/fotos/
    Headers:
      Authorization: ApiKey <key>
      X-Filename:    <EPC>_YYYY-MM-DD_HH-MM-SS[_N].jpg
      X-Aula-Id:     <int>
      Content-Type:  image/jpeg
    Body: raw JPEG bytes.
    """
    filename = request.META.get("HTTP_X_FILENAME", "")
    aula_raw = request.META.get("HTTP_X_AULA_ID", "")

    match = FOTO_FILENAME_RE.match(filename)
    if not match:
        return JsonResponse(
            {"error": "Invalid filename format", "filename": filename},
            status=400,
        )

    epc = match.group("epc").upper()
    ts_str = match.group("ts")
    try:
        naive = datetime.strptime(ts_str, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return JsonResponse(
            {"error": "Invalid timestamp in filename", "ts": ts_str},
            status=400,
        )
    timestamp_captura = naive.replace(tzinfo=FOTO_FILENAME_TZ)

    body = request.body
    size = len(body)
    if size == 0:
        return JsonResponse({"error": "Empty body"}, status=400)
    if size > FOTO_MAX_BYTES:
        return JsonResponse(
            {"error": "Oversized body", "size": size, "max": FOTO_MAX_BYTES},
            status=413,
        )
    if not body.startswith(JPEG_MAGIC):
        return JsonResponse({"error": "Not a JPEG (magic bytes mismatch)"}, status=400)

    # Aula lookup (nullable -- invalid id -> null, do not 400)
    aula_obj = None
    if aula_raw:
        try:
            aula_obj = Aula.objects.get(pk=int(aula_raw))
        except (Aula.DoesNotExist, ValueError):
            aula_obj = None

    # Idempotency: (epc, timestamp_captura) is the natural key. Retry = no-op.
    existing = FotoRFID.objects.filter(
        epc=epc, timestamp_captura=timestamp_captura
    ).first()
    if existing is not None:
        return JsonResponse(
            {"ok": True, "id": existing.id, "duplicate": True},
            status=200,
        )

    try:
        foto = FotoRFID(
            epc=epc,
            aula=aula_obj,
            timestamp_captura=timestamp_captura,
            tamano_bytes=size,
        )
        foto.imagen.save(filename, ContentFile(body), save=True)
    except IntegrityError:
        # Race: two concurrent uploads. Re-fetch and return idempotent.
        existing = FotoRFID.objects.filter(
            epc=epc, timestamp_captura=timestamp_captura
        ).first()
        if existing:
            return JsonResponse(
                {"ok": True, "id": existing.id, "duplicate": True},
                status=200,
            )
        return JsonResponse({"error": "DB integrity error"}, status=500)

    return JsonResponse({"ok": True, "id": foto.id}, status=201)
