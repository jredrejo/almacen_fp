#ifndef PHOTO_COMMANDS_H
#define PHOTO_COMMANDS_H

// =============================================================================
// Phase 06.1 -- Photo recovery & cleanup command handlers
// Implements the real bodies of tareaUploadFotos and tareaLimpiarFotos
// (forward-declared in mqtt_manager.h, stubbed in Plan 01, real here).
//
// Design constraints (see .planning/phases/06.1-*/06.1-RESEARCH.md):
//   * NEVER buffer JPEG in heap -- stream File* through HTTPClient::sendRequest.
//   * NEVER hold sdMutex across the whole iteration -- snapshot + release.
//   * NEVER delete on upload success -- deletion is the explicit limpiar step.
//   * NEVER block mqttCallback -- both tasks are invoked via xTaskCreate only.
//   * 10-second dedup window for replayed commands.
// =============================================================================

#include <Arduino.h>
#include <SD.h>
#include <HTTPClient.h>
#include <PubSubClient.h>
#include <vector>
#include "config.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

// Compile-time guard: AULA_ID must be defined and non-empty (WR-08).
#ifndef AULA_ID
#error "AULA_ID must be defined in config.h"
#endif

// Globals from main.cpp / camera_manager.h -- both headers are included in the
// same translation unit (main.cpp), so these symbols resolve.
extern PubSubClient mqttClient;
#ifdef CAMERA_ENABLED
// sdMutex lives in camera_manager.h as 'static SemaphoreHandle_t sdMutex'.
// It's visible only in TUs that include camera_manager.h. main.cpp does.
#endif

// --- Dedup gate: reject duplicate command within PHOTO_DEDUP_WINDOW_MS ---
static constexpr uint32_t PHOTO_DEDUP_WINDOW_MS = 10000;
static uint32_t lastUploadCommandMs = 0;
static uint32_t lastLimpiarCommandMs = 0;
static portMUX_TYPE dedupSpinlock = portMUX_INITIALIZER_UNLOCKED;

/**
 * Enumerate /fotos/ on SD under mutex SNAPSHOT (take, read, release).
 * Returns a vector of full paths like "/fotos/ABCD1234_2026-04-11_10-30-00.jpg".
 * Only includes files that LOOK like RFID photos: basename must contain at
 * least one underscore and end with ".jpg". Pre-EPC photos (no underscore-prefix
 * with hex digits) are still listed because this plan uploads ANY .jpg -- the
 * Django endpoint then filters on its own filename regex. Per D-05, pre-EPC
 * photos on SD will be rejected by Django (400) and stay on the card until
 * limpiar_fotos wipes them.
 */
inline std::vector<String> listarFotos() {
  std::vector<String> files;
#ifdef CAMERA_ENABLED
  if (sdMutex == nullptr) return files;
  if (xSemaphoreTake(sdMutex, pdMS_TO_TICKS(2000)) != pdTRUE) {
#ifdef DEBUG
    Serial.println("[foto-cmd] listarFotos: timeout tomando sdMutex");
#endif
    return files;
  }

  File dir = SD.open("/fotos");
  if (!dir) {
    xSemaphoreGive(sdMutex);
#ifdef DEBUG
    Serial.println("[foto-cmd] listarFotos: /fotos no existe");
#endif
    return files;
  }

  File entry;
  while ((entry = dir.openNextFile())) {
    if (!entry.isDirectory()) {
      String name = entry.name();  // basename only on Arduino SD
      if (name.endsWith(".jpg") || name.endsWith(".JPG")) {
        // Normalise to absolute path for SD.open / SD.remove below.
        if (name.startsWith("/fotos/")) {
          files.push_back(name);
        } else {
          files.push_back(String("/fotos/") + name);
        }
      }
    }
    entry.close();
  }
  dir.close();
  xSemaphoreGive(sdMutex);
#endif  // CAMERA_ENABLED
  return files;
}

/**
 * Upload a single file from SD to Django via streamed POST.
 * Takes sdMutex for the duration of the upload (blocks concurrent captures
 * during the transfer, but releases between files in the batch).
 * Returns true on HTTP 200 or 201 (201 = new row, 200 = duplicate idempotent).
 */
inline bool subirFoto(const String& ruta) {
#ifdef CAMERA_ENABLED
  if (sdMutex == nullptr) return false;
  if (xSemaphoreTake(sdMutex, pdMS_TO_TICKS(10000)) != pdTRUE) {
#ifdef DEBUG
    Serial.println("[foto-cmd] subirFoto: timeout tomando sdMutex");
#endif
    return false;
  }

  File f = SD.open(ruta.c_str(), FILE_READ);
  if (!f) {
    xSemaphoreGive(sdMutex);
#ifdef DEBUG
    Serial.print("[foto-cmd] subirFoto: no se pudo abrir ");
    Serial.println(ruta);
#endif
    return false;
  }
  size_t fsize = f.size();
  if (fsize == 0) {
    f.close();
    xSemaphoreGive(sdMutex);
    return false;
  }

  // Derive basename (after last '/') for X-Filename header.
  String base = ruta;
  int lastSlash = base.lastIndexOf('/');
  if (lastSlash >= 0) base = base.substring(lastSlash + 1);

  HTTPClient http;
  http.setTimeout(15000);  // 15 s -- uploads are slow vs EPC lookup
  String url = String(API_BASE_URL) + "/api/fotos/";
  if (!http.begin(url)) {
    f.close();
    xSemaphoreGive(sdMutex);
    return false;
  }
  http.addHeader("Authorization", String("ApiKey ") + API_KEY);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Filename", base);
  http.addHeader("X-Aula-Id", AULA_ID);

#ifdef DEBUG
  Serial.print("[foto-cmd] POST ");
  Serial.print(url);
  Serial.print(" X-Filename=");
  Serial.print(base);
  Serial.print(" size=");
  Serial.println(fsize);
#endif

  int code = http.sendRequest("POST", &f, fsize);
  f.close();
  http.end();
  xSemaphoreGive(sdMutex);

#ifdef DEBUG
  Serial.print("[foto-cmd] POST resultado: ");
  Serial.println(code);
#endif

  return (code == 200 || code == 201);
#else
  return false;
#endif
}

/**
 * Batch upload task. Called via xTaskCreate from mqttCallback (Plan 01 dispatch).
 * Stack sized at 12288 bytes in mqttCallback xTaskCreate.
 */
inline void tareaUploadFotos(void* param) {
  (void)param;

  // Dedup: ignore replayed command within window (atomic check-and-set)
  portENTER_CRITICAL(&dedupSpinlock);
  uint32_t now_ms = millis();
  if (lastUploadCommandMs != 0 &&
      (now_ms - lastUploadCommandMs) < PHOTO_DEDUP_WINDOW_MS) {
    portEXIT_CRITICAL(&dedupSpinlock);
#ifdef DEBUG
    Serial.println("[foto-cmd] upload_fotos ignorado (dedup window)");
#endif
    vTaskDelete(NULL);
    return;
  }
  lastUploadCommandMs = now_ms;
  portEXIT_CRITICAL(&dedupSpinlock);

  std::vector<String> files = listarFotos();
  int total = (int)files.size();
  int ok = 0, fail = 0;

#ifdef DEBUG
  Serial.print("[foto-cmd] tareaUploadFotos: ");
  Serial.print(total);
  Serial.println(" archivos a subir");
#endif

  for (int i = 0; i < total; i++) {
    bool success = false;
    for (int attempt = 0; attempt < 2; attempt++) {
      if (subirFoto(files[i])) { success = true; break; }
      vTaskDelay(pdMS_TO_TICKS(500));
    }
    if (success) ok++; else {
      fail++;
#ifdef DEBUG
      Serial.print("[foto-cmd] Fallo subiendo ");
      Serial.println(files[i]);
#endif
    }
    vTaskDelay(pdMS_TO_TICKS(100));  // throttle: cap ~10 uploads/sec
  }

  // Publish summary to rfid/sistema/estado/<AULA_ID> (QoS 0, retain false)
  char status[192];
  snprintf(status, sizeof(status),
    "{\"device_id\":\"%s\",\"action\":\"upload_fotos\",\"ok\":%d,\"fail\":%d,\"total\":%d}",
    DEVICE_ID, ok, fail, total);
  if (mqttClient.connected()) {
    mqttClient.publish(MQTT_TOPIC_ESTADO, status, false);
  }
#ifdef DEBUG
  Serial.print("[foto-cmd] upload resumen: ");
  Serial.println(status);
#endif

  vTaskDelete(NULL);
}

/**
 * Wipe-all task. Deletes every .jpg under /fotos/ on the SD.
 * Deliberately total (D-08).
 */
inline void tareaLimpiarFotos(void* param) {
  (void)param;

  portENTER_CRITICAL(&dedupSpinlock);
  uint32_t now_ms = millis();
  if (lastLimpiarCommandMs != 0 &&
      (now_ms - lastLimpiarCommandMs) < PHOTO_DEDUP_WINDOW_MS) {
    portEXIT_CRITICAL(&dedupSpinlock);
#ifdef DEBUG
    Serial.println("[foto-cmd] limpiar_fotos ignorado (dedup window)");
#endif
    vTaskDelete(NULL);
    return;
  }
  lastLimpiarCommandMs = now_ms;
  portEXIT_CRITICAL(&dedupSpinlock);

  std::vector<String> files = listarFotos();
  int total = (int)files.size();
  int removed = 0, failed = 0;

#ifdef CAMERA_ENABLED
  if (sdMutex != nullptr) {
    for (int i = 0; i < total; i++) {
      if (xSemaphoreTake(sdMutex, pdMS_TO_TICKS(2000)) != pdTRUE) {
        failed++;
        continue;
      }
      bool gone = SD.remove(files[i].c_str());
      xSemaphoreGive(sdMutex);
      if (gone) removed++; else failed++;
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
#endif

  char status[192];
  snprintf(status, sizeof(status),
    "{\"device_id\":\"%s\",\"action\":\"limpiar_fotos\",\"removed\":%d,\"failed\":%d,\"total\":%d}",
    DEVICE_ID, removed, failed, total);
  if (mqttClient.connected()) {
    mqttClient.publish(MQTT_TOPIC_ESTADO, status, false);
  }
#ifdef DEBUG
  Serial.print("[foto-cmd] limpiar resumen: ");
  Serial.println(status);
#endif

  vTaskDelete(NULL);
}

#endif // PHOTO_COMMANDS_H
