import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta

import paho.mqtt.client as mqtt
from django.core.cache import caches
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from almacen.models import Aula, Persona, Prestamo, Producto

# Obtener un logger con el nombre del módulo/comando
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- Configuración del Broker ---
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC = "rfid/#"
MQTT_TOPIC_READINGS = "rfid/lectura"

# --- Configuración de Batch ---
BATCH_TIME_SECONDS = int(os.getenv("BATCH_TIME_SECONDS", 3))
OPERATION_MODE = os.getenv("OPERATION_MODE", "WITH_PERSONA")

# --- Configuración de Redis/Caché ---
CACHE_TIMEOUT_SECONDS = int(os.getenv("CACHE_TIMEOUT_SECONDS", 35))
CACHE_KEY_FORMAT = "last_epc:{}"

try:
    epc_cache = caches["epc_cache"]
except KeyError:
    epc_cache = caches["default"]


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

        # Validar que hay una persona si hay productos (solo en modo WITH_PERSONA)
        if producto_epcs and not persona and OPERATION_MODE == "WITH_PERSONA":
            logger.error(
                f"Batch en Aula {aula_id} contiene {len(producto_epcs)} productos "
                f"pero NO se detectó ninguna Persona. EPCs: {producto_epcs}"
            )
            return

        # En modo WITHOUT_PERSONA, advertir si hay productos sin persona pero continuar
        if producto_epcs and not persona and OPERATION_MODE != "WITH_PERSONA":
            logger.warning(
                f"Batch en Aula {aula_id} contiene {len(producto_epcs)} productos "
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

    def on_connect(self, client, userdata, flags, rc):
        """Callback al conectarse al broker."""
        if rc == 0:
            logger.info("Conectado al broker MQTT.")
            client.subscribe(MQTT_TOPIC)
            logger.info(f"Suscrito al tema: {MQTT_TOPIC}")
        else:
            logger.error(f"Conexión fallida con código {rc}")

    def on_message(self, client, userdata, msg):
        """Callback al recibir un mensaje. Espera un payload JSON."""
        try:
            payload_str = msg.payload.decode("utf-8")
            if MQTT_TOPIC_READINGS not in msg.topic:
                logger.warning(
                    f"Mensaje recibido: {payload_str} en topic no usado para EPC: {msg.topic}"
                )
                return

            try:
                data = json.loads(payload_str)
            except json.JSONDecodeError:
                logger.error(
                    f"Error decodificando JSON en el mensaje del topic {msg.topic}. "
                    f"Payload: {payload_str[:50]}..."
                )
                return

            # Extraer los campos esperados del JSON
            aula_id = data.get("aula_id")
            epc = data.get("epc")
            timestamp_str = data.get("timestamp")

            if not all([aula_id, epc, timestamp_str]):
                logger.warning(
                    f"Campos clave (aula_id, epc, timestamp) faltantes en el payload JSON: "
                    f"{data} (Topic: {msg.topic})"
                )
                return

            # Convertir el timestamp ISO 8601 a un objeto datetime aware de Django
            try:
                # El formato es '2025-10-07T10:30:00'. fromisoformat maneja esto.
                leido_en = datetime.fromisoformat(timestamp_str)
                # Si el timestamp no incluye zona horaria (como en el ejemplo), asumimos UTC o la configuración de Django
                if (
                    leido_en.tzinfo is None
                    or leido_en.tzinfo.utcoffset(leido_en) is None
                ):
                    leido_en = timezone.make_aware(leido_en)
            except ValueError:
                logger.error(f"Formato de timestamp ('{timestamp_str}') inválido.")
                return

            # Validar la existencia del Aula
            try:
                Aula.objects.get(pk=aula_id)
            except Aula.DoesNotExist:
                logger.error(
                    f"Aula con ID {aula_id} no encontrada en la BD "
                    f"(Reportada por {msg.topic})."
                )
                return

            # Almacenamiento en caché de Django
            cache_key = CACHE_KEY_FORMAT.format(aula_id)
            data_to_cache = {
                "epc": epc,
                "leido_en": leido_en,
            }
            epc_cache.set(cache_key, data_to_cache, timeout=CACHE_TIMEOUT_SECONDS)

            # Agregar al batch processor
            self.batch_processor.add_epc(aula_id, epc, leido_en)

        except Exception as e:
            logger.exception(f"Error inesperado procesando mensaje MQTT: {e}")
