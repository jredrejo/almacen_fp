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
#include <SPI.h>
#include <SD.h>

// --- Pines SPI de la tarjeta SD del Tab5 ---
#define SD_SPI_CS_PIN   42
#define SD_SPI_SCK_PIN  43
#define SD_SPI_MOSI_PIN 44
#define SD_SPI_MISO_PIN 39

#include "config.h"
#include "wifi_manager.h"
#include "mqtt_manager.h"
#include "api_client.h"
#include "display_manager.h"
#include "sound_manager.h"

#ifdef CAMERA_ENABLED
#include "camera_manager.h"
#endif

// --- Colas FreeRTOS para pipeline EPC ---
// epcQueue: MQTT callback -> worker task (declared extern in mqtt_manager.h)
QueueHandle_t epcQueue = nullptr;

// Resultado del worker task para consumo thread-safe en loop()
struct EpcResult {
  char nombre[64];
  char tipo[16];
  char epc[64];    // For unknown EPCs
  char hora[6];
  bool encontrado;
};
static QueueHandle_t resultQueue = nullptr;

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

// --- Canvas para double-buffering (usado por display_manager.h) ---
M5Canvas canvas(&M5.Display);

// --- Nombre del aula para barra de estado ---
const char* NOMBRE_AULA = "Aula " AULA_ID;

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
uint8_t* fotoWavData = nullptr;
size_t fotoWavSize = 0;

// --- Variables de animacion idle DVD-screensaver ---
int idleX = 0, idleY = 0;                     // Posicion actual de splash_small
int idleDx = 3, idleDy = 2;                   // Velocidad en pixeles por frame (diagonal no repetitiva)
const int IMG_SIZE = 256;                       // splash_small.png es 256x256
unsigned long lastFrameTime = 0;
const unsigned long FRAME_INTERVAL = 33;        // ~30fps (per D-04)
int prevIdleX = -1, prevIdleY = -1;  // Previous position for dirty-flag check

// --- Buffer circular de ultimos eventos RFID para log ---
LogEntry eventLog[MAX_LOG_ENTRIES];
int eventLogCount = 0;

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

/**
 * Inicia la animacion idle con posicion aleatoria.
 * Llamar al transicionar a STATE_IDLE para que la imagen
 * aparezca en un punto diferente cada vez.
 */
void iniciarAnimacionIdle() {
  idleX = random(0, SCREEN_WIDTH - IMG_SIZE);
  idleY = random(0, SCREEN_HEIGHT - IMG_SIZE);
  prevIdleX = -1;
  prevIdleY = -1;
}

/**
 * Actualiza un frame de la animacion idle DVD-screensaver.
 * Mueve splash_small.png en diagonal, rebotando en los bordes.
 * Usa pantalla completa (sin barra de estado) con double-buffering.
 * Limita a ~60fps para rendimiento estable.
 */
void actualizarAnimacionIdle() {
  // Limitar framerate
  if (millis() - lastFrameTime < FRAME_INTERVAL) return;
  lastFrameTime = millis();

  // Mover posicion
  idleX += idleDx;
  idleY += idleDy;

  // Rebote en bordes (pantalla completa, sin barra de estado)
  if (idleX <= 0 || idleX + IMG_SIZE >= SCREEN_WIDTH) {
    idleDx = -idleDx;
    idleX = constrain(idleX, 0, SCREEN_WIDTH - IMG_SIZE);
  }
  if (idleY <= 0 || idleY + IMG_SIZE >= SCREEN_HEIGHT) {
    idleDy = -idleDy;
    idleY = constrain(idleY, 0, SCREEN_HEIGHT - IMG_SIZE);
  }

  // Skip redraw if position unchanged (per D-05)
  if (idleX == prevIdleX && idleY == prevIdleY) return;
  prevIdleX = idleX;
  prevIdleY = idleY;

  // Dibujar en canvas (double-buffering sin flicker)
  canvas.fillScreen(TFT_BLACK);
  if (splashSmallData != nullptr) {
    canvas.drawPng(splashSmallData, splashSmallSize, idleX, idleY);
  }
  canvas.pushSprite(0, 0);
}

/**
 * Anade un evento al log circular. El mas reciente queda en posicion 0.
 * Si el log esta lleno, la entrada mas antigua se descarta.
 */
void agregarEvento(const char* nombre, const char* tipo, const char* hora) {
  // Desplazar entradas hacia abajo (la mas antigua se pierde si hay MAX_LOG_ENTRIES)
  for (int i = MAX_LOG_ENTRIES - 1; i > 0; i--) {
    eventLog[i] = eventLog[i - 1];
  }
  // Insertar nueva entrada en posicion 0
  strncpy(eventLog[0].nombre, nombre, sizeof(eventLog[0].nombre) - 1);
  eventLog[0].nombre[sizeof(eventLog[0].nombre) - 1] = '\0';
  strncpy(eventLog[0].tipo, tipo, sizeof(eventLog[0].tipo) - 1);
  eventLog[0].tipo[sizeof(eventLog[0].tipo) - 1] = '\0';
  strncpy(eventLog[0].hora, hora, sizeof(eventLog[0].hora) - 1);
  eventLog[0].hora[sizeof(eventLog[0].hora) - 1] = '\0';
  eventLog[0].activo = true;
  if (eventLogCount < MAX_LOG_ENTRIES) eventLogCount++;
}

#ifdef CAMERA_ENABLED
/**
 * Tarea FreeRTOS para capturar y guardar foto en segundo plano.
 * Se crea al recibir evento RFID y se autodestruye al terminar.
 * No bloquea el loop principal ni la visualizacion de notificacion (D-05).
 */
void tareaCapturarFoto(void* param) {
  capturarYGuardarFoto();
  vTaskDelete(NULL);
}
#endif

/**
 * Tarea FreeRTOS worker para procesar EPCs: desencolear, resolver via HTTP, encolar resultado.
 * Corre permanentemente. Elimina bloqueo HTTP de 3s del loop principal.
 *
 * THREAD SAFETY: This task does HTTP + sound only. Display updates and
 * appState transitions happen in loop() via resultQueue to avoid data
 * races on appState/notificationStart and canvas (per BLOCKER 2 fix).
 */
void tareaResolverEpc(void* param) {
  EpcJob job;
  for (;;) {
    // Block waiting for next EPC job (portMAX_DELAY = wait forever)
    if (xQueueReceive(epcQueue, &job, portMAX_DELAY) == pdTRUE) {
#ifdef DEBUG
      Serial.print("Worker: procesando EPC ");
      Serial.println(job.epc);
#endif

#ifdef CAMERA_ENABLED
      // Disparar captura de foto ANTES de consultar API (per D-04)
      if (camaraInicializada) {
        xTaskCreate(tareaCapturarFoto, "foto", 8192, NULL, 1, NULL);
      }
#endif

      // Check cache first
      String epcStr(job.epc);
      EpcInfo info;
      EpcCacheEntry* cached = buscarEnCache(job.epc);
      if (cached) {
        info = cached->info;
#ifdef DEBUG
        Serial.println("Worker: EPC resuelto desde cache");
#endif
      } else {
        info = resolverEpc(epcStr);
        guardarEnCache(job.epc, info);
      }

      // Play sound from worker (sound is thread-safe, uses its own I2S)
      if (info.encontrado) {
        if (info.tipo == "persona") {
          reproducirTonoPersona();
        } else {
          reproducirTonoProducto();
        }
      } else {
        reproducirTonoProducto();
      }

      // Build result and send to loop() for display + state update
      EpcResult result;
      strncpy(result.nombre, info.nombre.c_str(), sizeof(result.nombre) - 1);
      result.nombre[sizeof(result.nombre) - 1] = '\0';
      strncpy(result.tipo, info.tipo.c_str(), sizeof(result.tipo) - 1);
      result.tipo[sizeof(result.tipo) - 1] = '\0';
      strncpy(result.epc, job.epc, sizeof(result.epc) - 1);
      result.epc[sizeof(result.epc) - 1] = '\0';
      obtenerHoraLocal(result.hora, sizeof(result.hora));
      result.encontrado = info.encontrado;

      xQueueSend(resultQueue, &result, portMAX_DELAY);
    }
  }
}

// =============================================================================
// Setup - Inicializacion del hardware y conectividad
// =============================================================================
void setup() {
  // 1. Inicializar M5Unified
  auto cfg = M5.config();
  M5.begin(cfg);

  // 2. Configurar altavoz
  setupSpeaker();

  // 3. Puerto serie para debug
  Serial.begin(115200);

  // 4. Configurar pantalla horizontal (1280x720)
  M5.Display.setRotation(1);

  // 5. Crear canvas para double-buffering (usa PSRAM automaticamente)
  canvas.createSprite(SCREEN_WIDTH, SCREEN_HEIGHT);
  memset(eventLog, 0, sizeof(eventLog));

#ifdef DEBUG
  Serial.println("=================================");
  Serial.println("Tab5 Pantalla Almacen - Iniciando...");
  Serial.println("=================================");
#endif

  // 6. Inicializar tarjeta SD via SPI (pines del Tab5)
  SPI.begin(SD_SPI_SCK_PIN, SD_SPI_MISO_PIN, SD_SPI_MOSI_PIN, SD_SPI_CS_PIN);
  if (!SD.begin(SD_SPI_CS_PIN, SPI, 40000000)) {
#ifdef DEBUG
    Serial.println("ERROR: No se detecto tarjeta SD");
#endif
  } else {
#ifdef DEBUG
    Serial.print("Tarjeta SD inicializada: ");
    Serial.print(SD.cardSize() / (1024 * 1024));
    Serial.println(" MB");
#endif
  }

  // 7. Cargar imagenes desde SD a PSRAM (antes del boot screen para mostrar splash)
  bool splashOk = cargarImagenSD("/splash.png", &splashData, &splashSize);
  bool splashSmallOk = cargarImagenSD("/splash_small.png", &splashSmallData, &splashSmallSize);

  bool fotoWavOk = cargarImagenSD("/foto.wav", &fotoWavData, &fotoWavSize);
#ifdef DEBUG
  if (fotoWavOk) {
    Serial.print("WAV obturador cargado: ");
    Serial.print(fotoWavSize);
    Serial.println(" bytes");
  } else {
    Serial.println("AVISO: No se pudo cargar foto.wav — se usara sin sonido");
  }
#endif

  if (!splashOk || !splashSmallOk) {
#ifdef DEBUG
    Serial.println("AVISO: No se pudieron cargar imagenes desde SD");
    Serial.println("El firmware funcionara sin animacion visual");
#endif
  }

  // 8. Boot screen progresivo: WiFi (antes de camara — SDIO necesita RAM interna
  //    que V4L2 mmap reclamara para los buffers de video)
  mostrarPantallaBoot(splashData, splashSize, "Conectando WiFi...");
  bool wifiOk = setupWifi();
  if (!wifiOk) {
#ifdef DEBUG
    Serial.println("AVISO: WiFi no conectado - se reintentara en loop");
#endif
  }

  // 9. Inicializar NTP y sincronizar hora
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

  // 9.5. Crear colas FreeRTOS para pipeline EPC
  epcQueue = xQueueCreate(8, sizeof(EpcJob));
  resultQueue = xQueueCreate(4, sizeof(EpcResult));

  // 10. Boot screen progresivo: MQTT
  mostrarPantallaBoot(splashData, splashSize, "Conectando MQTT...");
  setupMqtt(mqttClient);
  if (wifiOk) {
    if (attemptMqttConnect(mqttClient)) {
      mqttState = MQTT_ST_CONNECTED;
    } else {
      mqttState = MQTT_ST_DISCONNECTED;
    }
  }

  // 11. Boot screen progresivo: Camara (despues de WiFi/MQTT — V4L2 mmap consume
  //     RAM interna DMA que no debe competir con las colas SDIO de WiFi)
#ifdef CAMERA_ENABLED
  mostrarPantallaBoot(splashData, splashSize, "Iniciando camara...");
  inicializarCamara();
#endif

  // 11.5. Crear tarea worker para procesamiento EPC (off main loop, per D-09)
  xTaskCreate(tareaResolverEpc, "epcWorker", 8192, NULL, 2, NULL);

  // 12. Boot screen progresivo: Listo
  mostrarPantallaBoot(splashData, splashSize, "Listo");
  delay(1000);  // Mostrar "Listo" brevemente

  // 13. Transicionar a estado IDLE e iniciar animacion
  iniciarAnimacionIdle();
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
  // 1. Actualizar estado del hardware M5 y sonido
  M5.update();
  actualizarSonido();

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
      // Mostrar pantalla de reconexion segun el tipo de fallo
      if (!wifiConnected) {
        mostrarPantallaReconexion("Reconectando WiFi...");
      } else {
        mostrarPantallaReconexion("Reconectando MQTT...");
      }
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
  if (mqttState == MQTT_ST_CONNECTED) {
    mqttClient.loop();
  }

  // 4. Procesar resultados del worker EPC (thread-safe: display + state en loop context)
  EpcResult epcResult;
  if (xQueueReceive(resultQueue, &epcResult, 0) == pdTRUE) {
    if (epcResult.encontrado) {
      mostrarNotificacion(epcResult.nombre, epcResult.tipo, NOMBRE_AULA, epcResult.hora);
      agregarEvento(epcResult.nombre, epcResult.tipo, epcResult.hora);
    } else {
      mostrarEpcDesconocido(epcResult.epc, NOMBRE_AULA, epcResult.hora);
      agregarEvento(epcResult.epc, "desconocido", epcResult.hora);
    }
    dibujarLogEventos(eventLog, eventLogCount);
    canvas.pushSprite(0, 0);

    appState = STATE_NOTIFICATION;
    notificationStart = millis();
  }

  // 5. Maquina de estados principal
  switch (appState) {
    case STATE_BOOTING:
      // No hacer nada, ya transicionamos en setup
      break;

    case STATE_IDLE:
      actualizarAnimacionIdle();
      break;

    case STATE_NOTIFICATION:
      // Si paso el tiempo de notificacion, volver a idle con animacion
      if (millis() - notificationStart >= NOTIFICATION_DURATION) {
        iniciarAnimacionIdle();  // Reiniciar posicion aleatoria
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
