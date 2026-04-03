#ifndef API_CLIENT_H
#define API_CLIENT_H

// =============================================================================
// Cliente HTTP para resolver EPCs via API Django
// Consulta GET /api/epc/{epc}/ y obtiene nombre de producto/persona
// =============================================================================

#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"

// --- Estructura de resultado de resolucion EPC ---
struct EpcInfo {
  String tipo;       // "producto" o "persona"
  String nombre;     // Nombre resuelto del producto o persona
  bool encontrado;   // true si la API devolvio 200 con datos validos
};

// --- Cache de EPCs resueltos recientemente ---
static constexpr int EPC_CACHE_SIZE = 8;
static constexpr unsigned long EPC_CACHE_TTL = 30000;  // 30 seconds TTL

struct EpcCacheEntry {
  char epc[64];
  EpcInfo info;
  unsigned long timestamp;
  bool valid;
};

static EpcCacheEntry epcCache[EPC_CACHE_SIZE] = {};

/**
 * Busca un EPC en la cache. Retorna puntero a la entrada si encontrado y no expirado, nullptr si no.
 */
inline EpcCacheEntry* buscarEnCache(const char* epc) {
  unsigned long ahora = millis();
  for (int i = 0; i < EPC_CACHE_SIZE; i++) {
    if (epcCache[i].valid && strcmp(epcCache[i].epc, epc) == 0) {
      if (ahora - epcCache[i].timestamp < EPC_CACHE_TTL) {
        return &epcCache[i];
      }
      epcCache[i].valid = false;  // Expired
    }
  }
  return nullptr;
}

/**
 * Guarda un resultado de resolucion EPC en la cache (reemplaza la entrada mas antigua).
 */
inline void guardarEnCache(const char* epc, const EpcInfo& info) {
  // Find oldest or invalid slot
  int oldest = 0;
  unsigned long oldestTime = ULONG_MAX;
  for (int i = 0; i < EPC_CACHE_SIZE; i++) {
    if (!epcCache[i].valid) { oldest = i; break; }
    if (epcCache[i].timestamp < oldestTime) {
      oldestTime = epcCache[i].timestamp;
      oldest = i;
    }
  }
  strncpy(epcCache[oldest].epc, epc, sizeof(epcCache[oldest].epc) - 1);
  epcCache[oldest].epc[sizeof(epcCache[oldest].epc) - 1] = '\0';
  epcCache[oldest].info = info;
  epcCache[oldest].timestamp = millis();
  epcCache[oldest].valid = true;
}

/**
 * Resuelve un EPC consultando la API Django.
 * Hace GET a /api/epc/{epc}/ con autenticacion ApiKey.
 * Timeout de 3 segundos para no bloquear el loop demasiado.
 * @param epc Codigo EPC hexadecimal a resolver
 * @return EpcInfo con tipo, nombre y flag encontrado
 */
inline EpcInfo resolverEpc(const String& epc) {
  EpcInfo info = {"", "", false};
  HTTPClient http;

  // Construir URL del endpoint
  String url = String(API_BASE_URL) + "/api/epc/" + epc + "/";

  // Configurar timeout de 3 segundos
  http.setTimeout(3000);
  http.begin(url);

  // Header de autenticacion ApiKey
  http.addHeader("Authorization", String("ApiKey ") + API_KEY);

#ifdef DEBUG
  Serial.print("[API] GET ");
  Serial.println(url);
#endif

  int httpCode = http.GET();

#ifdef DEBUG
  Serial.print("[API] HTTP code: ");
  Serial.println(httpCode);
#endif

  if (httpCode == 200) {
    // Parsear respuesta JSON
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, http.getStream());
    if (!err) {
      info.tipo = doc["type"].as<String>();
      info.nombre = doc["nombre"].as<String>();
      info.encontrado = true;

#ifdef DEBUG
      Serial.print("[API] Resuelto: tipo=");
      Serial.print(info.tipo);
      Serial.print(" nombre=");
      Serial.println(info.nombre);
#endif
    }
#ifdef DEBUG
    else {
      Serial.print("[API] Error parseando JSON: ");
      Serial.println(err.c_str());
    }
#endif
  }
#ifdef DEBUG
  else {
    Serial.print("[API] EPC no encontrado o error: ");
    Serial.println(httpCode);
  }
#endif

  // Liberar recursos siempre
  http.end();
  return info;
}

#endif // API_CLIENT_H
