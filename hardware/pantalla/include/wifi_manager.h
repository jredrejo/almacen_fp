#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <WiFi.h>
#include "config.h"

// Declaracion externa del cliente NTP para re-sincronizar tras reconexion
class NTPClient;
extern NTPClient timeClient;

// =============================================================================
// Modulo de gestion WiFi con reconexion no bloqueante y backoff exponencial
// =============================================================================

// Estados de la maquina de estados WiFi
enum WifiState {
  WIFI_ST_CONNECTED,
  WIFI_ST_DISCONNECTED,
  WIFI_ST_WAITING_RETRY
};

// Variables de estado globales WiFi
static WifiState wifiState = WIFI_ST_DISCONNECTED;
static unsigned long wifiReconnectInterval = 1000;    // Intervalo inicial: 1 segundo
static unsigned long lastWifiReconnectAttempt = 0;
static const unsigned long MAX_WIFI_RECONNECT_INTERVAL = 30000;  // Maximo: 30 segundos
static bool wifiJustReconnected = false;  // Flag para re-sincronizar NTP

/**
 * Configuracion inicial de WiFi con setPins para ESP32-C6 del Tab5.
 * Espera bloqueante solo durante setup (max 20 segundos).
 * @return true si la conexion fue exitosa, false si agoto los intentos
 */
bool setupWifi() {
  // CRITICO: Configurar pines SDIO del coprocesador ESP32-C6 ANTES de WiFi.begin()
  // Pines: clk=12, cmd=13, d0=11, d1=10, d2=9, d3=8, rst=15
  WiFi.setPins(12, 13, 11, 10, 9, 8, 15);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

#ifdef DEBUG
  Serial.print("Conectando a WiFi: ");
  Serial.println(WIFI_SSID);
#endif

  // Espera bloqueante solo en setup (max 20s con intentos de 500ms)
  int intentos = 0;
  const int MAX_INTENTOS = 40;  // 40 * 500ms = 20 segundos
  while (WiFi.status() != WL_CONNECTED && intentos < MAX_INTENTOS) {
    delay(500);
    intentos++;
#ifdef DEBUG
    Serial.print(".");
#endif
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiState = WIFI_ST_CONNECTED;
    wifiReconnectInterval = 1000;  // Resetear intervalo
#ifdef DEBUG
    Serial.println();
    Serial.print("WiFi conectado - IP: ");
    Serial.println(WiFi.localIP());
#endif
    return true;
  } else {
    wifiState = WIFI_ST_DISCONNECTED;
#ifdef DEBUG
    Serial.println();
    Serial.println("Error: No se pudo conectar a WiFi en el tiempo limite");
#endif
    return false;
  }
}

/**
 * Verificacion y reconexion WiFi no bloqueante.
 * Llamar en cada iteracion del loop().
 * Usa backoff exponencial: 1s inicial, duplica en cada fallo, maximo 30s.
 * Re-sincroniza NTP tras reconexion exitosa.
 * @return true si WiFi esta conectado, false si esta desconectado
 */
bool wifiReconnectCheck() {
  switch (wifiState) {
    case WIFI_ST_CONNECTED:
      // Verificar si seguimos conectados
      if (WiFi.status() != WL_CONNECTED) {
        wifiState = WIFI_ST_DISCONNECTED;
        wifiReconnectInterval = 1000;  // Resetear intervalo
#ifdef DEBUG
        Serial.println("WiFi desconectado - iniciando reconexion");
#endif
      }
      break;

    case WIFI_ST_DISCONNECTED:
      // Intentar reconectar inmediatamente
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      // Verificar resultado despues de un breve momento
      wifiState = WIFI_ST_WAITING_RETRY;
      lastWifiReconnectAttempt = millis();
#ifdef DEBUG
      Serial.println("Intentando reconexion WiFi...");
#endif
      break;

    case WIFI_ST_WAITING_RETRY:
      if (WiFi.status() == WL_CONNECTED) {
        // Reconexion exitosa
        wifiState = WIFI_ST_CONNECTED;
        wifiReconnectInterval = 1000;
        wifiJustReconnected = true;
#ifdef DEBUG
        Serial.print("WiFi reconectado - IP: ");
        Serial.println(WiFi.localIP());
#endif
        // Re-sincronizar NTP tras reconexion exitosa
        timeClient.forceUpdate();
      } else if (millis() - lastWifiReconnectAttempt >= wifiReconnectInterval) {
        // Timeout: reintentar con backoff exponencial
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        wifiReconnectInterval = min(wifiReconnectInterval * 2, MAX_WIFI_RECONNECT_INTERVAL);
        lastWifiReconnectAttempt = millis();
#ifdef DEBUG
        Serial.print("Reconexion WiFi fallida - siguiente intento en ");
        Serial.print(wifiReconnectInterval);
        Serial.println(" ms");
#endif
      }
      break;
  }

  return (wifiState == WIFI_ST_CONNECTED);
}

#endif // WIFI_MANAGER_H
