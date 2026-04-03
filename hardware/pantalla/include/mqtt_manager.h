#ifndef MQTT_MANAGER_H
#define MQTT_MANAGER_H

#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

// =============================================================================
// Modulo MQTT con maquina de estados para reconexion no bloqueante
// Patron replicado de hardware/almacen/conexionMQTT.ino
// =============================================================================

// Estados de la maquina de estados MQTT
// Prefijo MQTT_ST_ para evitar colision con macros de PubSubClient.h
enum MqttState {
  MQTT_ST_CONNECTED,
  MQTT_ST_DISCONNECTED,
  MQTT_ST_WAITING_RETRY
};

// Variables de estado globales MQTT
static MqttState mqttState = MQTT_ST_DISCONNECTED;
static unsigned long lastReconnectAttempt = 0;
static unsigned long reconnectInterval = 1000;  // Intervalo inicial: 1 segundo
static const unsigned long MAX_RECONNECT_INTERVAL = 30000;  // Maximo: 30 segundos

// Estructura para jobs de EPC en la cola
struct EpcJob {
  char epc[64];  // EPC hex string (max 24 chars typical, 64 safe)
};

// Cola FreeRTOS de EPCs pendientes (capacidad 8 — sufficient for burst reads)
// IMPORTANT: declared extern here, defined in main.cpp (per BLOCKER 3 fix).
// static would give each translation unit its own copy — a silent failure.
extern QueueHandle_t epcQueue;

/**
 * Callback MQTT: se ejecuta al recibir un mensaje en un topic suscrito.
 * Parsea el JSON y extrae el campo "epc", encolandolo para procesamiento async.
 * NO hace HTTP ni operaciones bloqueantes dentro del callback.
 */
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Parsear JSON del payload MQTT
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);

  if (err) {
#ifdef DEBUG
    Serial.print("Error parseando JSON MQTT: ");
    Serial.println(err.c_str());
#endif
    return;
  }

  // Extraer campo "epc" del mensaje y encolar
  const char* epc = doc["epc"];
  if (epc && epcQueue != nullptr) {
    EpcJob job;
    strncpy(job.epc, epc, sizeof(job.epc) - 1);
    job.epc[sizeof(job.epc) - 1] = '\0';
    // Non-blocking enqueue (MQTT callback runs in loop task context)
    if (xQueueSend(epcQueue, &job, 0) != pdTRUE) {
#ifdef DEBUG
      Serial.println("AVISO: Cola EPC llena, descartando evento");
#endif
    }
#ifdef DEBUG
    else {
      Serial.print("MQTT - EPC encolado: ");
      Serial.println(epc);
    }
#endif
  }
}

/**
 * Configuracion inicial del cliente MQTT.
 * Establece servidor, tamano de buffer y callback.
 * @param client Referencia al cliente PubSubClient
 */
void setupMqtt(PubSubClient& client) {
  client.setServer(MQTT_SERVER, MQTT_PORT);
  client.setBufferSize(512);  // Buffer mayor para payloads JSON
  client.setCallback(mqttCallback);
  client.setSocketTimeout(10);    // 10 seconds socket timeout (per D-11)
  client.setKeepAlive(15);        // 15 seconds keepalive (per D-11)

#ifdef DEBUG
  Serial.print("MQTT configurado - Servidor: ");
  Serial.print(MQTT_SERVER);
  Serial.print(":");
  Serial.println(MQTT_PORT);
#endif
}

/**
 * Intenta conectar al broker MQTT con LWT (Last Will and Testament).
 * Publica mensaje online con retain=true al conectar.
 * Se suscribe al topic rfid/pantalla/{aula_id} con QoS 1.
 * @param client Referencia al cliente PubSubClient
 * @return true si la conexion fue exitosa, false en caso contrario
 */
bool attemptMqttConnect(PubSubClient& client) {
  // Construir payload LWT para cuando el dispositivo se desconecte
  char lwt[128];
  snprintf(lwt, sizeof(lwt),
           "{\"client_id\":\"%s\",\"aula_id\":\"%s\",\"status\":\"offline\"}",
           CLIENT_ID, AULA_ID);

#ifdef DEBUG
  Serial.println("Intentando conectar MQTT con LWT...");
#endif

  // Conectar con LWT: topic, QoS=1, retain=true
  bool connected = false;
  if (strlen(MQTT_USER) > 0) {
    connected = client.connect(CLIENT_ID, MQTT_USER, MQTT_PASSWORD,
                               "rfid/sistema", 1, true, lwt);
  } else {
    connected = client.connect(CLIENT_ID, "rfid/sistema", 1, true, lwt);
  }

  if (connected) {
    // Publicar mensaje online con retain=true
    char onlineMsg[256];
    snprintf(onlineMsg, sizeof(onlineMsg),
             "{\"client_id\":\"%s\",\"aula_id\":\"%s\",\"status\":\"online\",\"ip\":\"%s\"}",
             CLIENT_ID, AULA_ID, WiFi.localIP().toString().c_str());

    client.publish("rfid/sistema", onlineMsg, true);

    // Suscribirse al topic de pantalla con QoS 1
    client.subscribe(MQTT_TOPIC_PANTALLA, 1);

#ifdef DEBUG
    Serial.println("MQTT conectado exitosamente");
    Serial.print("Suscrito a: ");
    Serial.println(MQTT_TOPIC_PANTALLA);
#endif
    return true;
  } else {
#ifdef DEBUG
    Serial.print("Fallo conexion MQTT, rc=");
    Serial.println(client.state());
#endif
    return false;
  }
}

/**
 * Maquina de estados para reconexion MQTT no bloqueante.
 * Identica en estructura a conexionMQTT.ino del reader Arduino.
 * Debe llamarse en cada iteracion del loop().
 * @param client Referencia al cliente PubSubClient
 */
void mqttReconnectStateMachine(PubSubClient& client) {
  switch (mqttState) {
    case MQTT_ST_CONNECTED:
      // Verificar si seguimos conectados
      if (!client.connected()) {
        // Perdimos la conexion, transicionar a DESCONECTADO
        mqttState = MQTT_ST_DISCONNECTED;
        reconnectInterval = 1000;  // Resetear intervalo de reconexion
#ifdef DEBUG
        Serial.println("MQTT desconectado - iniciando reconexion");
#endif
      }
      break;

    case MQTT_ST_DISCONNECTED:
      // Intentar conectar inmediatamente
      if (attemptMqttConnect(client)) {
        mqttState = MQTT_ST_CONNECTED;
      } else {
        // Fallo de conexion - esperar antes de reintentar
        mqttState = MQTT_ST_WAITING_RETRY;
        lastReconnectAttempt = millis();
#ifdef DEBUG
        Serial.print("Reconexion fallida - siguiente intento en ");
        Serial.print(reconnectInterval);
        Serial.println(" ms");
#endif
      }
      break;

    case MQTT_ST_WAITING_RETRY:
      // Verificar si es tiempo de reintentar
      if (millis() - lastReconnectAttempt >= reconnectInterval) {
        if (attemptMqttConnect(client)) {
          mqttState = MQTT_ST_CONNECTED;
        } else {
          // Backoff exponencial: duplicar intervalo hasta el maximo
          reconnectInterval = min(reconnectInterval * 2, MAX_RECONNECT_INTERVAL);
          lastReconnectAttempt = millis();
#ifdef DEBUG
          Serial.print("Reconexion fallida - siguiente intento en ");
          Serial.print(reconnectInterval);
          Serial.println(" ms");
#endif
        }
      }
      break;
  }
}

#endif // MQTT_MANAGER_H
