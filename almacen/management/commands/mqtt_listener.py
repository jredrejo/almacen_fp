import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone
from logging.handlers import RotatingFileHandler

import paho.mqtt.client as mqtt
from django.core.cache import caches
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from almacen.models import Aula, Persona, Prestamo, Producto

# --- Configuración del Broker ---
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC_LECTURA = "rfid/lectura/+"
MQTT_TOPIC_SISTEMA = "rfid/sistema"

# --- Configuración de Batch ---
BATCH_TIME_SECONDS = int(os.getenv("BATCH_TIME_SECONDS", 5))

# --- Configuración de Redis/Caché ---
CACHE_TIMEOUT_SECONDS = int(os.getenv("CACHE_TIMEOUT_SECONDS", 35))
CACHE_KEY_FORMAT = "last_epc:{}"

try:
    epc_cache = caches["epc_cache"]
except KeyError:
    epc_cache = caches["default"]


# Configurar logging con rotación
def setup_logging():
    """Configura logging con rotación de archivos. Funciona en Linux y Windows."""

    # En Linux/Unix, intentar usar /var/log
    if os.path.exists("/var/log") and os.access("/var/log", os.W_OK):
        log_file = "/var/log/mqtt-listener.log"
    else:
        # Fallback: usar el directorio actual
        log_dir = os.path.join(os.getcwd(), "logs")
        log_file = os.path.join(log_dir, "mqtt-listener.log")

    if "log_dir" in locals():
        os.makedirs(log_dir, exist_ok=True)
    else:
        # Para /var/log, el directorio ya debería existir
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Configurar handler con rotación
    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB por archivo
        backupCount=5,  # Mantener 5 archivos de backup
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    # Configurar el logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # También configurar el logger raíz para capturar todo
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    # Mostrar información sobre dónde se están guardando los logs
    logger.info(f"Logging configured. Log file: {log_file}")

    return logger


logger = setup_logging()


class BatchProcessor:
    """Procesa EPCs en lotes por aula."""

    def __init__(self, batch_time_seconds):
        self.batch_time = timedelta(seconds=batch_time_seconds)
        self.batches = defaultdict(list)  # {aula_id: [(epc, timestamp), ...]}
        self.last_epc_time = {}  # {aula_id: datetime}

    def add_epc(self, aula_id, epc, timestamp):
        """Agrega un EPC al batch. NO procesa inmediatamente."""
        # Agregar el nuevo EPC al batch
        self.batches[aula_id].append((epc, timestamp))

        # Actualizar el timestamp de la última lectura para este aula
        # Esto "reinicia" el timer del batch cada vez que llega un nuevo EPC
        self.last_epc_time[aula_id] = timestamp

        logger.debug(
            f"EPC '{epc}' agregado al batch del Aula {aula_id}. Total en batch: {len(self.batches[aula_id])}"
        )

    def check_and_process_batches(self):
        """Verifica y procesa batches que han expirado."""
        now = timezone.now()
        aulas_to_process = []

        # Identificar aulas cuyos batches deben procesarse
        for aula_id, last_time in list(self.last_epc_time.items()):
            time_since_last = now - last_time
            if time_since_last >= self.batch_time and self.batches[aula_id]:
                aulas_to_process.append(aula_id)

        # Procesar los batches
        for aula_id in aulas_to_process:
            self._process_batch(aula_id)

    def _process_batch(self, aula_id):
        """Procesa un batch completo de EPCs para un aula."""
        batch = self.batches[aula_id]

        if not batch:
            return

        logger.info(f"Procesando batch para Aula {aula_id} con {len(batch)} lecturas")

        try:
            self._process_batch_logic(aula_id, batch)
        except Exception as e:
            logger.exception(f"Error procesando batch para Aula {aula_id}: {e}")
        finally:
            # Siempre limpiar el batch después de procesarlo
            if aula_id in self.batches:
                del self.batches[aula_id]
            if aula_id in self.last_epc_time:
                del self.last_epc_time[aula_id]

    def _process_batch_logic(self, aula_id, batch):
        """Lógica principal para procesar el batch."""
        # Extraer EPCs únicos y usar el timestamp más reciente para cada uno
        epc_dict = {}
        for epc, timestamp in batch:
            if epc not in epc_dict or timestamp > epc_dict[epc]:
                epc_dict[epc] = timestamp

        epcs = list(epc_dict.keys())
        logger.info(f"EPCs únicos en batch: {epcs}")

        # Buscar Persona en el batch
        persona = None
        persona_epc = None

        for epc in epcs:
            try:
                persona_obj = Persona.objects.select_related("user").get(epc=epc)
                persona = persona_obj.user
                persona_epc = epc
                logger.info(
                    f"Persona encontrada: {persona.get_full_name() or persona.email} (EPC: {epc})"
                )
                break
            except Persona.DoesNotExist:
                continue

        # Separar EPCs de productos
        producto_epcs = [epc for epc in epcs if epc != persona_epc]

        # Obtener el modo de operación del aula
        try:
            aula = Aula.objects.get(pk=aula_id)
            operation_mode = aula.operation_mode
        except Aula.DoesNotExist:
            logger.error(f"Aula con ID {aula_id} no encontrada en la BD")
            return

        # Validar que hay una persona si hay productos (solo en modo WITH_PERSONA)
        if producto_epcs and not persona and operation_mode == "WITH_PERSONA":
            logger.error(
                f"Batch en Aula {aula_id} ({aula.nombre}) contiene {len(producto_epcs)} productos "
                f"pero NO se detectó ninguna Persona. EPCs: {producto_epcs}"
            )
            return

        # En modo WITHOUT_PERSONA, advertir si hay productos sin persona pero continuar
        if producto_epcs and not persona and operation_mode == "WITHOUT_PERSONA":
            logger.warning(
                f"Batch en Aula {aula_id} ({aula.nombre}) contiene {len(producto_epcs)} productos "
                f"sin Persona detectada. Procesando en modo WITHOUT_PERSONA."
            )

        if not producto_epcs:
            logger.info("Batch solo contiene Persona, no hay productos para procesar.")
            return

        # Procesar cada producto
        for epc in producto_epcs:
            timestamp = epc_dict[epc]
            self._process_producto_epc(aula_id, epc, timestamp, persona)

    def _process_producto_epc(self, aula_id, epc, timestamp, persona):
        """Procesa un EPC de producto individual."""
        try:
            producto = Producto.objects.select_related("aula").get(epc=epc)
        except Producto.DoesNotExist:
            logger.warning(
                f"EPC '{epc}' no encontrado ni en Producto ni en Persona. "
                f"Aula ID: {aula_id}, Timestamp: {timestamp}"
            )
            return

        # Validar aula del producto
        if producto.aula_id != aula_id:  # type: ignore[attr-defined]
            logger.warning(
                f"Producto '{producto.nombre}' (EPC: {epc}) está registrado en "
                f"Aula '{producto.aula.nombre}' pero fue detectado en Aula ID {aula_id}. "
                f"Actualizando ubicación..."
            )
            try:
                nueva_aula = Aula.objects.get(pk=aula_id)
                producto.aula = nueva_aula
                producto.save(update_fields=["aula"])
                logger.info(
                    f"Producto '{producto.nombre}' movido a Aula '{nueva_aula.nombre}'"
                )
            except Aula.DoesNotExist:
                logger.error(f"Aula con ID {aula_id} no existe en la BD")
                return

        # Buscar préstamo activo (no devuelto)
        prestamo_activo = Prestamo.objects.filter(
            producto=producto, devuelto_en__isnull=True
        ).first()

        with transaction.atomic():
            # Obtener o crear la Ubicacion para este producto
            from almacen.models import Ubicacion

            ubicacion, created = Ubicacion.objects.get_or_create(producto=producto)

            if prestamo_activo:
                # DEVOLUCIÓN: El producto está prestado, marcar como devuelto
                prestamo_activo.devuelto_en = timestamp
                prestamo_activo.save(update_fields=["devuelto_en"])

                # Actualizar Ubicacion: producto vuelve al estante
                ubicacion.estado = "ESTANTE"
                ubicacion.aula = producto.aula
                ubicacion.estanteria = producto.estanteria
                ubicacion.posicion = producto.posicion
                ubicacion.persona = None
                ubicacion.tomado_en = None
                ubicacion.save(
                    update_fields=[
                        "estado",
                        "aula",
                        "estanteria",
                        "posicion",
                        "persona",
                        "tomado_en",
                    ]
                )

                usuario_nombre = (
                    prestamo_activo.usuario.get_full_name()
                    or prestamo_activo.usuario.email
                    if prestamo_activo.usuario
                    else "desconocido"
                )
                logger.info(
                    f"✓ DEVOLUCIÓN: '{producto.nombre}' devuelto por "
                    f"{usuario_nombre} a {timestamp.strftime('%H:%M:%S')}"
                )
            else:
                # PRÉSTAMO: El producto no está prestado, crear nuevo préstamo
                # En modo WITHOUT_PERSONA, persona puede ser None
                Prestamo.objects.create(
                    producto=producto, usuario=persona, tomado_en=timestamp
                )

                # Actualizar Ubicacion: producto tomado por persona
                ubicacion.estado = "PERSONA"
                ubicacion.persona = persona
                ubicacion.tomado_en = timestamp
                ubicacion.aula = None
                ubicacion.estanteria = ""
                ubicacion.posicion = ""
                ubicacion.save(
                    update_fields=[
                        "estado",
                        "persona",
                        "tomado_en",
                        "aula",
                        "estanteria",
                        "posicion",
                    ]
                )

                if persona:
                    usuario_nombre = persona.get_full_name() or persona.email
                    logger.info(
                        f"✓ PRÉSTAMO: '{producto.nombre}' tomado por "
                        f"{usuario_nombre} a {timestamp.strftime('%H:%M:%S')}"
                    )
                else:
                    logger.info(
                        f"✓ PRÉSTAMO: '{producto.nombre}' tomado (sin persona identificada) "
                        f"a {timestamp.strftime('%H:%M:%S')}"
                    )


# --- Payload Validation (pure functions, no Django, no side effects) ---

EPC_RE = re.compile(r"^[0-9A-F]{8,24}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def validate_epc(epc):
    """Returns (ok, reason). Reason is 'epc_format' or None."""
    if not isinstance(epc, str) or not EPC_RE.match(epc):
        return False, "epc_format"
    return True, None


def validate_timestamp(ts_str):
    """Returns (ok, value). Value is a tz-aware UTC datetime on success, 'ts_format' on failure."""
    if not isinstance(ts_str, str) or not TS_RE.match(ts_str):
        return False, "ts_format"
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt_timezone.utc)
    except ValueError:
        return False, "ts_format"
    return True, dt


def validate_payload(data, aula_id_from_topic):
    """
    Validate rfid/lectura/{aula_id} payload against docs/CONTRACT.md MQTT section.
    Returns (ok: bool, reason: str | None, parsed: dict | None).
    parsed = {"epc": str, "timestamp": datetime} on success.
    """
    if not isinstance(data, dict):
        return False, "schema", None
    if not all(k in data for k in ("aula_id", "epc", "timestamp")):
        return False, "schema", None
    if str(data["aula_id"]) != str(aula_id_from_topic):
        return False, "aula_mismatch", None
    ok, reason = validate_epc(data["epc"])
    if not ok:
        return False, reason, None
    ok, ts_or_reason = validate_timestamp(data["timestamp"])
    if not ok:
        return False, "ts_format", None
    return True, None, {"epc": data["epc"], "timestamp": ts_or_reason}


class Command(BaseCommand):
    help = "Escucha mensajes MQTT para EPC de RFID con proceso por lotes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-time",
            type=int,
            default=BATCH_TIME_SECONDS,
            help=f"Tiempo de espera en segundos para agrupar lecturas (default: {BATCH_TIME_SECONDS}s)",
        )
        parser.add_argument(
            "--check-interval",
            type=float,
            default=0.5,
            help="Intervalo en segundos para verificar batches expirados (default: 0.5s)",
        )

    def handle(self, *args, **options):
        batch_time = options["batch_time"]
        check_interval = options["check_interval"]

        logger.info(
            f"Iniciando el listener MQTT con batch time de {batch_time} segundos..."
        )

        self.batch_processor = BatchProcessor(batch_time)
        self.reject_counts = Counter()

        client = mqtt.Client()
        if MQTT_USER and MQTT_PASSWORD:
            client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        client.on_connect = self.on_connect
        client.on_message = self.on_message

        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            # Usar loop con timeout para poder verificar batches periódicamente
            while True:
                client.loop(timeout=check_interval)
                self.batch_processor.check_and_process_batches()
        except KeyboardInterrupt:
            logger.info("Listener detenido por el usuario")
        except Exception as e:
            logger.error(f"Error de conexión MQTT: {e}")
        finally:
            logger.info(
                "mqtt_reject_summary",
                extra={"counts": dict(self.reject_counts)},
            )

    def on_connect(self, client, userdata, flags, rc):
        """Callback al conectarse al broker."""
        if rc == 0:
            logger.info("Conectado al broker MQTT.")
            client.subscribe(MQTT_TOPIC_LECTURA)
            client.subscribe(MQTT_TOPIC_SISTEMA)
            logger.info(f"Suscrito a {MQTT_TOPIC_LECTURA} y {MQTT_TOPIC_SISTEMA}")
        else:
            logger.error(f"Conexión fallida con código {rc}")

    def on_message(self, client, userdata, msg):
        """Callback al recibir un mensaje. Routing por tipo de topic."""
        try:
            payload_str = msg.payload.decode("utf-8")
            topic_parts = msg.topic.split('/')

            # Routing por tipo de topic
            if len(topic_parts) == 3 and topic_parts[1] == 'lectura':
                aula_id_from_topic = topic_parts[2]
                self._process_lectura(aula_id_from_topic, payload_str, msg.topic)
            elif len(topic_parts) == 2 and topic_parts[1] == 'sistema':
                logger.info(f"Evento sistema MQTT: {payload_str}")
            else:
                logger.warning(f"Topic no reconocido: {msg.topic}")
        except Exception as e:
            logger.exception(f"Error inesperado procesando mensaje MQTT: {e}")

    def _process_lectura(self, aula_id_from_topic, payload_str, topic):
        """Procesa un mensaje del topic rfid/lectura/{aula_id}."""
        def _reject(reason):
            self.reject_counts[reason] += 1
            logger.warning(
                "mqtt_payload_rejected",
                extra={
                    "topic": topic,
                    "reason": reason,
                    "payload_preview": (payload_str or "")[:80],
                },
            )

        # 1. JSON decode
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            _reject("json_decode")
            return

        # 2. Schema + format validation (pure function from Task 1)
        ok, reason, parsed = validate_payload(data, aula_id_from_topic)
        if not ok:
            _reject(reason)
            return

        # 3. Topic aula_id -> int (operational, not a contract violation if topic is well-formed)
        try:
            aula_id_int = int(aula_id_from_topic)
        except (TypeError, ValueError):
            _reject("schema")  # malformed topic -- treat as schema violation
            return

        # 4. Aula existence -- operational error, not contract violation
        try:
            Aula.objects.get(pk=aula_id_int)
        except Aula.DoesNotExist:
            logger.error("Aula %s no existe", aula_id_int)
            return

        # 5. Almacenamiento en cache de Django
        cache_key = CACHE_KEY_FORMAT.format(aula_id_int)
        data_to_cache = {
            "epc": parsed["epc"],
            "leido_en": parsed["timestamp"],
        }
        epc_cache.set(cache_key, data_to_cache, timeout=CACHE_TIMEOUT_SECONDS)

        # 6. Happy path -- hand off to batch processor
        self.batch_processor.add_epc(aula_id_int, parsed["epc"], parsed["timestamp"])
