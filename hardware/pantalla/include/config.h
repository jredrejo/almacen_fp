#ifndef CONFIG_H
#define CONFIG_H

// =============================================================================
// Configuracion del Tab5 - Pantalla de notificaciones RFID
// =============================================================================
// Rellenar estos valores con los datos de tu red y servidor antes de compilar.
// Este archivo NO debe subirse a control de versiones con credenciales reales.
// =============================================================================

// --- Credenciales WiFi ---
// SSID y contrasena de la red WiFi a la que se conectara el Tab5
#define WIFI_SSID        "TU_SSID"
#define WIFI_PASSWORD    "TU_PASSWORD"

// --- Configuracion MQTT ---
// Direccion IP o hostname del broker MQTT (Mosquitto)
#define MQTT_SERVER      "192.168.1.100"
#define MQTT_PORT        1883
// Usuario y contrasena del broker MQTT (dejar vacio si no requiere autenticacion)
#define MQTT_USER        ""
#define MQTT_PASSWORD    ""

// --- Identificacion del dispositivo ---
// ID del aula donde esta instalado el Tab5 (debe coincidir con el aula en Django)
#define AULA_ID          "1"
// ID unico del cliente MQTT para este dispositivo
#define CLIENT_ID        "tab5_aula_" AULA_ID

// --- API Django ---
// URL base del servidor Django (sin barra final)
#define API_BASE_URL     "http://192.168.1.100:8000"
// Clave de API para autenticacion (header: Authorization: ApiKey <clave>)
#define API_KEY          "TU_API_KEY"

// --- Topics MQTT ---
// Topic donde el Tab5 recibe notificaciones de EPCs detectados
// Formato: rfid/pantalla/{aula_id}
#define MQTT_TOPIC_PANTALLA  "rfid/pantalla/" AULA_ID

// --- Modo debug ---
// Comentar esta linea para desactivar los mensajes por Serial
#define DEBUG 1

#endif // CONFIG_H
