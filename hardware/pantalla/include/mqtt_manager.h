#ifndef MQTT_MANAGER_H
#define MQTT_MANAGER_H

#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"

// =============================================================================
// Modulo MQTT con maquina de estados para reconexion no bloqueante
// Patron replicado de hardware/almacen/conexionMQTT.ino
// =============================================================================

// Estados de la maquina de estados MQTT
enum MqttState {
  MQTT_CONNECTED,
  MQTT_DISCONNECTED,
  MQTT_WAITING_RETRY
};

// Variables de estado globales MQTT
static MqttState mqttState = MQTT_DISCONNECTED;
static unsigned long lastReconnectAttempt = 0;
static unsigned long reconnectInterval = 1000;  // Intervalo inicial: 1 segundo
static const unsigned long MAX_RECONNECT_INTERVAL = 30000;  // Maximo: 30 segundos

// Cola simple de EPCs pendientes (un solo EPC a la vez)
// El callback MQTT guarda aqui el EPC; el loop() lo procesa fuera del callback
static String pendingEpc = "";
static bool hasPendingEpc = false;

/**
 * Callback MQTT: se ejecuta al recibir un mensaje en un topic suscrito.
 * Parsea el JSON y extrae el campo "epc", guardandolo en pendingEpc.
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

  // Extraer campo "epc" del mensaje
  const char* epc = doc["epc"];
  if (epc) {
    pendingEpc = String(epc);
    hasPendingEpc = true;
#ifdef DEBUG
    Serial.print("MQTT - EPC recibido en callback: ");
    Serial.println(epc);
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
    case MQTT_CONNECTED:
      // Verificar si seguimos conectados
      if (!client.connected()) {
        // Perdimos la conexion, transicionar a DESCONECTADO
        mqttState = MQTT_DISCONNECTED;
        reconnectInterval = 1000;  // Resetear intervalo de reconexion
#ifdef DEBUG
        Serial.println("MQTT desconectado - iniciando reconexion");
#endif
      }
      break;

    case MQTT_DISCONNECTED:
      // Intentar conectar inmediatamente
      if (attemptMqttConnect(client)) {
        mqttState = MQTT_CONNECTED;
      } else {
        // Fallo de conexion - esperar antes de reintentar
        mqttState = MQTT_WAITING_RETRY;
        lastReconnectAttempt = millis();
#ifdef DEBUG
        Serial.print("Reconexion fallida - siguiente intento en ");
        Serial.print(reconnectInterval);
        Serial.println(" ms");
#endif
      }
      break;

    case MQTT_WAITING_RETRY:
      // Verificar si es tiempo de reintentar
      if (millis() - lastReconnectAttempt >= reconnectInterval) {
        if (attemptMqttConnect(client)) {
          mqttState = MQTT_CONNECTED;
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
