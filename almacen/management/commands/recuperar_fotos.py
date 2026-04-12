"""
Phase 06.1 — Tab5 photo recovery & cleanup MQTT command publisher.

Publishes one of:
    {"action": "upload_fotos"}
    {"action": "limpiar_fotos"}
to topic `rfid/sistema/comando/<aula_id>` on the project's MQTT broker.

Usage:
    python manage.py recuperar_fotos --aula 1
    python manage.py recuperar_fotos --aula 1 --action upload
    python manage.py recuperar_fotos --aula 1 --action limpiar
"""
import json
import logging
import os
import sys

import paho.mqtt
import paho.mqtt.client as mqtt
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

# --- Broker config (match mqtt_listener.py verbatim)
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

# --- Topic template (must match firmware config.h Phase 06.1 MQTT_TOPIC_COMANDO)
MQTT_COMANDO_TOPIC_FMT = "rfid/sistema/comando/{aula_id}"

# --- Supported actions
ACTIONS = {
    "upload": "upload_fotos",
    "limpiar": "limpiar_fotos",
}


class Command(BaseCommand):
    help = (
        "Publica un comando MQTT al Tab5 para recuperar o limpiar fotos de la SD. "
        "Destino: rfid/sistema/comando/<aula_id>."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--aula",
            type=str,
            required=True,
            help="ID del aula destino (cadena decimal, ej. '1').",
        )
        parser.add_argument(
            "--action",
            type=str,
            choices=list(ACTIONS.keys()),
            default="upload",
            help="upload = pedir subida. limpiar = borrar /fotos/ del Tab5 (destructivo).",
        )

    def handle(self, *args, **options):
        aula_id = str(options["aula"]).strip()
        action_key = options["action"]
        action_value = ACTIONS[action_key]

        if not aula_id:
            raise CommandError("--aula no puede estar vacio")

        topic = MQTT_COMANDO_TOPIC_FMT.format(aula_id=aula_id)
        payload = json.dumps({"action": action_value}, separators=(",", ":"))

        self.stdout.write(
            self.style.NOTICE(
                f"[recuperar_fotos] broker={MQTT_BROKER}:{MQTT_PORT} topic={topic} payload={payload}"
            )
        )

        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"django-recuperar-fotos-{os.getpid()}",
            )
        except (AttributeError, TypeError) as exc:
            logger.warning(
                "paho-mqtt %s doesn't support CallbackAPIVersion.VERSION2, "
                "falling back to legacy API: %s",
                paho.mqtt.__version__, exc,
            )
            client = mqtt.Client(client_id=f"django-recuperar-fotos-{os.getpid()}")

        if MQTT_USER:
            client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
        except Exception as exc:
            raise CommandError(f"No se pudo conectar al broker {MQTT_BROKER}:{MQTT_PORT}: {exc}")

        client.loop_start()
        try:
            info = client.publish(topic, payload, qos=1, retain=False)
            try:
                info.wait_for_publish(timeout=5.0)
            except (ValueError, RuntimeError) as exc:
                raise CommandError(f"Error esperando PUBACK del broker: {exc}")

            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise CommandError(
                    f"Fallo al publicar (rc={info.rc})"
                )
        finally:
            client.loop_stop()
            client.disconnect()

        self.stdout.write(
            self.style.SUCCESS(
                f"[recuperar_fotos] Publicado OK: action={action_value} aula={aula_id}"
            )
        )
