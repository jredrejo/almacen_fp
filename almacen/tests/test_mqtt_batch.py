"""
Script de prueba para simular mensajes MQTT al listener de batch RFID.

Uso:
    python test_mqtt_batch.py

Asegúrate de tener el broker MQTT corriendo y el listener activo:
    python manage.py mqtt_listener --batch-time 3
"""

import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime

# Configuración
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "rfid/lectura"

# EPCs de ejemplo (reemplaza con tus EPCs reales)
PERSONA_EPC = "E200001234567890ABCD1234"  # EPC de una persona en tu BD
PRODUCTO_1_EPC = "E200001111111111AAAA1111"  # EPC de producto 1
PRODUCTO_2_EPC = "E200002222222222BBBB2222"  # EPC de producto 2
AULA_ID = 1  # ID del aula donde ocurre la lectura


def enviar_lectura(client, aula_id, epc, delay=0):
    """Envía una lectura RFID al broker MQTT."""
    timestamp = datetime.now().isoformat()
    payload = {"aula_id": aula_id, "epc": epc, "timestamp": timestamp}

    if delay > 0:
        time.sleep(delay)

    result = client.publish(MQTT_TOPIC, json.dumps(payload))
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] Enviado EPC: {epc[:20]}... a Aula {aula_id}"
    )
    return result


def test_prestamo():
    """Prueba 1: Persona toma productos (crear préstamos)."""
    print("\n" + "=" * 60)
    print("PRUEBA 1: TOMAR PRODUCTOS (Crear Préstamos)")
    print("=" * 60)

    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    print("Simulando lectura de persona + 2 productos...")
    enviar_lectura(client, AULA_ID, PERSONA_EPC)
    enviar_lectura(client, AULA_ID, PRODUCTO_1_EPC, delay=0.5)
    enviar_lectura(client, AULA_ID, PRODUCTO_2_EPC, delay=0.5)

    print("Esperando procesamiento del batch (3 segundos)...")
    time.sleep(4)

    client.loop_stop()
    client.disconnect()


def test_devolucion():
    """Prueba 2: Persona devuelve productos (cerrar préstamos)."""
    print("\n" + "=" * 60)
    print("PRUEBA 2: DEVOLVER PRODUCTOS (Cerrar Préstamos)")
    print("=" * 60)

    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    print("Simulando lectura de persona + 2 productos (devolución)...")
    enviar_lectura(client, AULA_ID, PERSONA_EPC)
    enviar_lectura(client, AULA_ID, PRODUCTO_1_EPC, delay=0.5)
    enviar_lectura(client, AULA_ID, PRODUCTO_2_EPC, delay=0.5)

    print("Esperando procesamiento del batch (3 segundos)...")
    time.sleep(4)

    client.loop_stop()
    client.disconnect()


def test_sin_persona():
    """Prueba 3: Solo productos sin persona (debe generar error)."""
    print("\n" + "=" * 60)
    print("PRUEBA 3: PRODUCTOS SIN PERSONA (Debe generar ERROR)")
    print("=" * 60)

    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    print("Simulando lectura de productos SIN persona...")
    enviar_lectura(client, AULA_ID, PRODUCTO_1_EPC)
    enviar_lectura(client, AULA_ID, PRODUCTO_2_EPC, delay=0.5)

    print("Esperando procesamiento del batch (3 segundos)...")
    time.sleep(4)

    client.loop_stop()
    client.disconnect()


def test_epc_desconocido():
    """Prueba 4: EPC desconocido (debe generar warning)."""
    print("\n" + "=" * 60)
    print("PRUEBA 4: EPC DESCONOCIDO (Debe generar WARNING)")
    print("=" * 60)

    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    EPC_DESCONOCIDO = "E200009999999999ZZZZ9999"

    print("Simulando lectura de persona + EPC desconocido...")
    enviar_lectura(client, AULA_ID, PERSONA_EPC)
    enviar_lectura(client, AULA_ID, EPC_DESCONOCIDO, delay=0.5)

    print("Esperando procesamiento del batch (3 segundos)...")
    time.sleep(4)

    client.loop_stop()
    client.disconnect()


def test_aula_incorrecta():
    """Prueba 5: Producto detectado en aula diferente (debe actualizar)."""
    print("\n" + "=" * 60)
    print("PRUEBA 5: AULA INCORRECTA (Debe actualizar ubicación)")
    print("=" * 60)

    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    OTRA_AULA_ID = 2  # Asegúrate de que existe en tu BD

    print(f"Simulando lectura en Aula {OTRA_AULA_ID} (diferente a la registrada)...")
    enviar_lectura(client, OTRA_AULA_ID, PERSONA_EPC)
    enviar_lectura(client, OTRA_AULA_ID, PRODUCTO_1_EPC, delay=0.5)

    print("Esperando procesamiento del batch (3 segundos)...")
    time.sleep(4)

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("SCRIPT DE PRUEBA - MQTT BATCH LISTENER")
    print("=" * 60)
    print("\nIMPORTANTE: Antes de ejecutar estas pruebas:")
    print("1. Actualiza los EPCs en este script con valores reales de tu BD")
    print("2. Asegúrate de que el broker MQTT esté corriendo")
    print("3. Inicia el listener: python manage.py mqtt_listener --batch-time 3")
    print("4. Observa los logs del listener en otra terminal")
    print("=" * 60)

    input("\nPresiona Enter para comenzar las pruebas...")

    try:
        # Ejecutar todas las pruebas en secuencia
        test_prestamo()
        time.sleep(2)

        test_devolucion()
        time.sleep(2)

        test_sin_persona()
        time.sleep(2)

        test_epc_desconocido()
        time.sleep(2)

        # test_aula_incorrecta()  # Descomenta si tienes múltiples aulas

        print("\n" + "=" * 60)
        print("PRUEBAS COMPLETADAS")
        print("=" * 60)
        print("\nRevisa los logs del listener para ver los resultados.")

    except KeyboardInterrupt:
        print("\n\nPruebas interrumpidas por el usuario.")
    except Exception as e:
        print(f"\n\nError durante las pruebas: {e}")
