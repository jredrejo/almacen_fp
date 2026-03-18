// =============================================================================
// Tab5 Pantalla Almacen - Firmware principal
// Muestra notificaciones RFID con nombre de producto/persona
// =============================================================================
// Autores: Jose L. Redrejo / Claude
// Placa: M5Stack Tab5 (ESP32-P4 + ESP32-C6 coprocesador WiFi)
// =============================================================================

#include <M5Unified.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <WiFiUdp.h>
#include <NTPClient.h>
#include <Timezone.h>
#include <SD.h>

#include "config.h"
#include "wifi_manager.h"
#include "mqtt_manager.h"

// --- Clientes de red ---
WiFiClient espClient;
PubSubClient mqttClient(espClient);
WiFiUDP ntpUDP;
NTPClient timeClient(ntpUDP, "pool.ntp.org", 0, 60000);  // Sin offset, Timezone lo gestiona

// --- Timezone Espana ---
// Reglas de cambio horario: verano (CEST) y invierno (CET)
TimeChangeRule summerTime = { "CEST", Last, Sun, Mar, 1, 120 };
TimeChangeRule winterTime = { "CET", Last, Sun, Oct, 1, 60 };
Timezone spain(summerTime, winterTime);

// --- Maquina de estados principal ---
enum AppState {
  STATE_BOOTING,
  STATE_IDLE,
  STATE_NOTIFICATION,
  STATE_RECONNECTING
};

AppState appState = STATE_BOOTING;
AppState previousState = STATE_BOOTING;  // Estado anterior para volver tras reconexion

// --- Temporizador de notificacion ---
unsigned long notificationStart = 0;
const unsigned long NOTIFICATION_DURATION = 5000;  // 5 segundos (decision locked)

// --- Buffers PSRAM para imagenes cargadas desde SD ---
uint8_t* splashData = nullptr;
size_t splashSize = 0;
uint8_t* splashSmallData = nullptr;
size_t splashSmallSize = 0;

/**
 * Carga una imagen PNG desde la SD card a un buffer en PSRAM.
 * @param path Ruta del archivo en la SD (e.g., "/splash.png")
 * @param buffer Puntero al buffer donde se almacenara la imagen
 * @param size Puntero al tamano del archivo leido
 * @return true si la carga fue exitosa, false si fallo
 */
bool cargarImagenSD(const char* path, uint8_t** buffer, size_t* size) {
  File f = SD.open(path, FILE_READ);
  if (!f) {
#ifdef DEBUG
    Serial.print("Error: No se pudo abrir ");
    Serial.println(path);
#endif
    return false;
  }

  *size = f.size();
  *buffer = (uint8_t*)ps_malloc(*size);  // Usar PSRAM para buffers grandes

  if (!*buffer) {
    f.close();
#ifdef DEBUG
    Serial.print("Error: No hay memoria PSRAM para ");
    Serial.println(path);
#endif
    return false;
  }

  f.read(*buffer, *size);
  f.close();

#ifdef DEBUG
  Serial.print("Imagen cargada: ");
  Serial.print(path);
  Serial.print(" (");
  Serial.print(*size);
  Serial.println(" bytes)");
#endif
  return true;
}

/**
 * Obtiene la hora local espanola formateada como HH:MM.
 * Usa NTPClient + Timezone para conversion automatica verano/invierno.
 * @param buffer Buffer donde escribir la hora formateada
 * @param bufferSize Tamano del buffer
 */
void obtenerHoraLocal(char* buffer, size_t bufferSize) {
  time_t utc = now();
  time_t local = spain.toLocal(utc);
  struct tm* timeinfo = localtime(&local);
  strftime(buffer, bufferSize, "%H:%M", timeinfo);
}

// =============================================================================
// Setup - Inicializacion del hardware y conectividad
// =============================================================================
void setup() {
  // 1. Inicializar M5Unified
  auto cfg = M5.config();
  M5.begin(cfg);

  // 2. Puerto serie para debug
  Serial.begin(115200);

  // 3. Configurar pantalla horizontal (1280x720)
  M5.Display.setRotation(1);

#ifdef DEBUG
  Serial.println("=================================");
  Serial.println("Tab5 Pantalla Almacen - Iniciando...");
  Serial.println("=================================");
#endif

  // 4. Conectar WiFi (espera bloqueante solo aqui, max 20s)
  bool wifiOk = setupWifi();
  if (!wifiOk) {
#ifdef DEBUG
    Serial.println("AVISO: WiFi no conectado - se reintentara en loop");
#endif
  }

  // 5. Inicializar NTP y sincronizar hora
  timeClient.begin();
  if (wifiOk) {
    timeClient.update();
    setTime(timeClient.getEpochTime());
#ifdef DEBUG
    char hora[8];
    obtenerHoraLocal(hora, sizeof(hora));
    Serial.print("Hora local: ");
    Serial.println(hora);
#endif
  }

  // 6. Configurar MQTT y primer intento de conexion
  setupMqtt(mqttClient);
  if (wifiOk) {
    if (attemptMqttConnect(mqttClient)) {
      mqttState = MQTT_CONNECTED;
    } else {
      mqttState = MQTT_DISCONNECTED;
    }
  }

  // 7. Cargar imagenes desde SD a PSRAM
  bool splashOk = cargarImagenSD("/splash.png", &splashData, &splashSize);
  bool splashSmallOk = cargarImagenSD("/splash_small.png", &splashSmallData, &splashSmallSize);

  if (!splashOk || !splashSmallOk) {
#ifdef DEBUG
    Serial.println("AVISO: No se pudieron cargar imagenes desde SD");
    Serial.println("El firmware funcionara sin animacion visual");
#endif
  }

  // 8. Transicionar a estado IDLE
  appState = STATE_IDLE;

#ifdef DEBUG
  Serial.println("=================================");
  Serial.println("Setup completo - entrando en loop principal");
  Serial.println("=================================");
#endif
}

// =============================================================================
// Loop - Bucle principal no bloqueante con maquina de estados
// =============================================================================
void loop() {
  // 1. Actualizar estado del hardware M5
  M5.update();

  // 2. Verificar conectividad y gestionar reconexion
  bool wifiConnected = wifiReconnectCheck();

  if (!wifiConnected || !mqttClient.connected()) {
    // Transicionar a reconexion si no estamos ya en ese estado
    if (appState != STATE_RECONNECTING) {
      previousState = appState;  // Guardar estado anterior
      appState = STATE_RECONNECTING;
#ifdef DEBUG
      Serial.println("Entrando en estado RECONNECTING");
#endif
    }

    // Ejecutar maquina de estados MQTT solo si WiFi esta conectado
    if (wifiConnected) {
      mqttReconnectStateMachine(mqttClient);
    }

    // Verificar si se restauro la conectividad
    if (wifiConnected && mqttClient.connected()) {
      appState = (previousState == STATE_BOOTING) ? STATE_IDLE : previousState;
#ifdef DEBUG
      Serial.println("Conectividad restaurada - volviendo a estado normal");
#endif
    }
  }

  // 3. Procesar mensajes MQTT si estamos conectados
  if (mqttState == MQTT_CONNECTED) {
    mqttClient.loop();
  }

  // 4. Procesar EPC pendiente del callback MQTT
  if (hasPendingEpc) {
#ifdef DEBUG
    Serial.print("EPC recibido: ");
    Serial.println(pendingEpc);
#endif
    // La resolucion HTTP y display se implementan en plan 02
    hasPendingEpc = false;
  }

  // 5. Maquina de estados principal
  switch (appState) {
    case STATE_BOOTING:
      // No hacer nada, ya transicionamos en setup
      break;

    case STATE_IDLE:
      // Placeholder: animacion DVD-screensaver se implementa en plan 03
      break;

    case STATE_NOTIFICATION:
      // Si paso el tiempo de notificacion, volver a idle
      if (millis() - notificationStart >= NOTIFICATION_DURATION) {
        appState = STATE_IDLE;
#ifdef DEBUG
        Serial.println("Notificacion finalizada - volviendo a IDLE");
#endif
      }
      break;

    case STATE_RECONNECTING:
      // Gestionado en el bloque de conectividad (paso 2)
      break;
  }
}
