import os
import time

import M5
import machine
import network
from configs import (
    MQTT_BROKER,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_USER,
    PANTALLA_ID,
    WIFI_PASSWORD,
    WIFI_SSID,
)
from machine import Pin
from umqtt.simple import MQTTClient

# Topic MQTT para esta pantalla
MQTT_TOPIC = f"rfid/pantalla/{PANTALLA_ID}"

# Variable global para controlar el estado de alerta
alerta_activa = False
alerta_tiempo_fin = 0

# Initialize M5Stack
M5.begin()

# Initialize SD card with Tab5 pins
sd = machine.SDCard(
    slot=2,
    width=4,
    cd=None,
    wp=None,
    sck=Pin(43),  # CLK
    miso=Pin(39),  # DAT0
    mosi=Pin(44),  # CMD
    cs=Pin(42),  # DAT3
)

# Mount the SD card
# try:
#     os.mount(sd, "/sd")
#     print("SD Card mounted successfully")
# except Exception as e:
#     print(f"SD Card mount failed: {e}")

# Get screen dimensions (after rotation, Tab5 should be 800x1280)
screen_width = M5.Display.width()
screen_height = M5.Display.height()
print(f"Screen size: {screen_width}x{screen_height}")

# Load both PNG images
try:
    # with open("/sd/splash.png", "rb") as f:
    with open("assets/splash.png", "rb") as f:
        png_full = f.read()
    print("Loaded splash.png (512x512)")

    # with open("/sd/splash_small.png", "rb") as f:
    with open("assets/splash_small.png", "rb") as f:
        png_small = f.read()
    print("Loaded splash_small.png (256x256)")
except Exception as e:
    print(f"Error loading images: {e}")
    print("Make sure both splash.png and splash_small.png are on the SD card")

# Image dimensions
img_full_size = 512
img_small_size = 256

# Calculate center position for full-size image
center_x = (screen_width - img_full_size) // 2
center_y = (screen_height - img_full_size) // 2

# Calculate corner positions for small image (with margin)
margin = 20

# Top-left corner
tl_x = margin
tl_y = margin

# Top-right corner
tr_x = screen_width - img_small_size - margin
tr_y = margin

# Bottom-right corner
br_x = screen_width - img_small_size - margin
br_y = screen_height - img_small_size - margin

# Bottom-left corner
bl_x = margin
bl_y = screen_height - img_small_size - margin

print(f"Center position: ({center_x}, {center_y})")
print(
    f"Corner positions: TL({tl_x},{tl_y}) TR({tr_x},{tr_y}) BR({br_x},{br_y}) BL({bl_x},{bl_y})"
)


def main():
    # ============================================
    # Conexión WiFi
    # ============================================
    print("Conectando a WiFi...")
    M5.Display.clear()
    M5.Display.setTextSize(2)
    M5.Display.drawString("Conectando WiFi...", 50, screen_height // 2)

    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    sta.connect(WIFI_SSID, WIFI_PASSWORD)

    # Esperar conexión con timeout
    wifi_timeout = 30  # segundos
    wifi_start = time.time()
    while not sta.isconnected():
        if time.time() - wifi_start > wifi_timeout:
            print("Error: Timeout conectando a WiFi")
            M5.Display.clear()
            M5.Display.drawString("Error WiFi!", 50, screen_height // 2)
            time.sleep(5)
            machine.reset()
        time.sleep(0.5)

    print(f"WiFi conectado: {sta.ifconfig()[0]}")

    # ============================================
    # Conexión MQTT
    # ============================================
    print(f"Conectando a MQTT broker {MQTT_BROKER}...")
    M5.Display.clear()
    M5.Display.drawString("Conectando MQTT...", 50, screen_height // 2)

    def mqtt_callback(topic: bytes, msg: bytes) -> None:
        """Callback cuando llega un mensaje MQTT. Activa la pantalla roja."""
        global alerta_activa, alerta_tiempo_fin
        print(f"MQTT recibido - Topic: {topic.decode()}, Mensaje: {msg.decode()}")
        alerta_activa = True
        alerta_tiempo_fin = time.time() + 5  # 5 segundos de pantalla roja

    def mostrar_pantalla_roja() -> None:
        """Muestra la pantalla completamente roja."""
        M5.Display.clear()
        M5.Display.fillRect(0, 0, screen_width, screen_height, 0xFF0000)
        M5.Display.setTextColor(0xFFFFFF)
        M5.Display.setTextSize(3)
        # Centrar el texto "ALERTA"
        M5.Display.drawString("ALERTA", screen_width // 2 - 80, screen_height // 2 - 20)
        M5.update()

    # Crear cliente MQTT con ID único y credenciales
    client_id = f"pantalla_{PANTALLA_ID}"
    mqtt_client = MQTTClient(
        client_id, MQTT_BROKER, port=MQTT_PORT, user=MQTT_USER, password=MQTT_PASSWORD
    )
    mqtt_client.set_callback(mqtt_callback)

    try:
        mqtt_client.connect()
        mqtt_client.subscribe(MQTT_TOPIC.encode())
        print(f"MQTT conectado y suscrito a: {MQTT_TOPIC}")
    except Exception as e:
        print(f"Error conectando MQTT: {e}")
        M5.Display.clear()
        M5.Display.drawString("Error MQTT!", 50, screen_height // 2)
        time.sleep(5)
        machine.reset()

    # Display centered image initially
    M5.Display.clear()
    M5.Display.drawPng(png_full, center_x, center_y)
    print("Displaying centered image for 10 seconds...")

    # Wait 10 seconds
    time.sleep(10)

    # Lista de posiciones para la animación
    posiciones_animacion = [
        ("top-left corner", png_small, tl_x, tl_y),
        ("top-right corner", png_small, tr_x, tr_y),
        ("bottom-right corner", png_small, br_x, br_y),
        ("bottom-left corner", png_small, bl_x, bl_y),
        ("center", png_full, center_x, center_y),
    ]

    def esperar_con_mqtt(duracion: float) -> None:
        """
        Espera 'duracion' segundos mientras revisa mensajes MQTT.
        Si se activa una alerta, muestra pantalla roja y espera 5 segundos.
        """
        global alerta_activa, alerta_tiempo_fin

        tiempo_fin = time.time() + duracion

        while time.time() < tiempo_fin:
            # Revisar mensajes MQTT (no bloqueante)
            try:
                mqtt_client.check_msg()
            except Exception as e:
                print(f"Error MQTT check_msg: {e}")

            # Si hay alerta activa, mostrar pantalla roja
            if alerta_activa:
                print("¡ALERTA ACTIVADA! Mostrando pantalla roja...")
                mostrar_pantalla_roja()

                # Esperar mientras la alerta esté activa
                while alerta_activa:
                    try:
                        mqtt_client.check_msg()
                    except Exception:
                        pass

                    if time.time() >= alerta_tiempo_fin:
                        alerta_activa = False
                        print("Alerta finalizada, volviendo a animación")
                        break

                    time.sleep(0.1)
                    M5.update()

                # Salir del bucle de espera para redibujar la animación
                return

            time.sleep(0.1)
            M5.update()

    # Animation loop
    print("Starting animation loop...")
    indice_posicion = 0

    while True:
        M5.update()

        # Obtener posición actual
        nombre, imagen, pos_x, pos_y = posiciones_animacion[indice_posicion]

        # Mostrar imagen en posición actual
        print(f"Moving to {nombre}")
        M5.Display.clear()
        M5.Display.drawPng(imagen, pos_x, pos_y)
        M5.update()

        # Esperar 2 segundos revisando MQTT
        esperar_con_mqtt(2)

        # Avanzar a la siguiente posición
        indice_posicion = (indice_posicion + 1) % len(posiciones_animacion)


main()
