import json
import logging
from datetime import datetime
import paho.mqtt.client as mqtt

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.cache import caches
from almacen.models import Aula

# Obtener un logger con el nombre del módulo/comando
logger = logging.getLogger(__name__)

# --- Configuración del Broker ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
# El topic puede ser general, por ejemplo 'rfid/lectura/#'
MQTT_TOPIC = "rfid/lectura/#"
# --- Configuración de Redis/Caché ---
CACHE_TIMEOUT_SECONDS = 35
CACHE_KEY_FORMAT = "last_epc:{}"

# Obtener la instancia del caché específico
try:
    epc_cache = caches["epc_cache"]
except KeyError:
    # Si 'epc_cache' no está definido, usamos el default
    epc_cache = caches["default"]


class Command(BaseCommand):
    help = "Escucha mensajes MQTT para EPC de RFID. Espera payload JSON con epc, aula_id y timestamp."

    def handle(self, *args, **options):
        logger.info("Iniciando el listener MQTT...")
        client = mqtt.Client()
        client.on_connect = self.on_connect
        client.on_message = self.on_message

        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()
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

            try:
                data = json.loads(payload_str)
            except json.JSONDecodeError:
                logger.error(
                    f"Error decodificando JSON en el mensaje del topic {msg.topic}. Payload: {payload_str[:50]}..."
                )
                return

            # Extraer los campos esperados del JSON
            aula_id = data.get("aula_id")
            epc = data.get("epc")
            timestamp_str = data.get("timestamp")

            if not all([aula_id, epc, timestamp_str]):
                logger.warning(
                    f"Campos clave (aula_id, epc, timestamp) faltantes en el payload JSON: {data} (Topic: {msg.topic})"
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
                    f"Aula con ID {aula_id} no encontrada en la BD (Reportada por {msg.topic})."
                )
                return

            # Almacenamiento en caché de Django
            cache_key = CACHE_KEY_FORMAT.format(aula_id)

            data_to_cache = {
                "epc": epc,
                "leido_en": leido_en,  # Usamos el timestamp del sensor
            }

            epc_cache.set(cache_key, data_to_cache, timeout=CACHE_TIMEOUT_SECONDS)

            logger.info(
                f"EPC '{epc}' registrado en Caché para Aula ID '{aula_id}' a las {leido_en.strftime('%H:%M:%S')}."
            )

        except Exception as e:
            logger.exception(f"Error inesperado procesando mensaje MQTT: {e}")
