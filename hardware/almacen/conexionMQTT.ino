// Maquina de estados para reconexion MQTT no bloqueante con backoff exponencial

// Estados de la maquina de estados MQTT
enum MqttState {
  MQTT_CONNECTED,
  MQTT_DISCONNECTED,
  MQTT_WAITING_RETRY
};

// Variables de estado globales
MqttState mqttState = MQTT_DISCONNECTED;
unsigned long lastReconnectAttempt = 0;
unsigned long reconnectInterval = 1000;  // Empieza en 1s
const unsigned long MAX_RECONNECT_INTERVAL = 30000;  // Maximo 30s

/**
 * Intenta conectar al broker MQTT con LWT configurado
 * @return true si la conexion fue exitosa, false en caso contrario
 */
bool attemptMqttConnect() {
  // Construir payload LWT para cuando el dispositivo se desconecte
  char lwt[128];
  snprintf(lwt, sizeof(lwt),
           "{\"reader_id\":\"%s\",\"aula_id\":\"%s\",\"status\":\"offline\"}",
           clientId, aulaId);

#ifdef DEBUG
  Serial.println("Intentando conectar MQTT con LWT...");
#endif

  // Conectar con LWT: topic, QoS=1, retain=true
  if (client.connect(clientId, mqttUser, mqttPassword,
                     "rfid/sistema", 1, true, lwt)) {
    // Conexion exitosa - publicar mensaje online retenido
    char timestamp[32];
    obtenerFechaHora(timestamp, sizeof(timestamp));

    char onlineMsg[256];
    snprintf(onlineMsg, sizeof(onlineMsg),
             "{\"reader_id\":\"%s\",\"aula_id\":\"%s\",\"status\":\"online\",\"ip\":\"%s\",\"version\":\"%s\",\"timestamp\":\"%s\"}",
             clientId, aulaId, WiFi.localIP().toString().c_str(), version_almacen, timestamp);

    // Publicar mensaje online con retain=true para que este disponible aun si el dispositivo se apaga
    client.publish("rfid/sistema", onlineMsg, true);

#ifdef DEBUG
    Serial.println("MQTT conectado exitosamente");
    Serial.print("Mensaje online publicado: ");
    Serial.println(onlineMsg);
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
 * Maquina de estados para reconexion MQTT no bloqueante
 * Debe llamarse en cada iteracion del loop()
 */
void mqttReconnectStateMachine() {
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
      if (attemptMqttConnect()) {
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
        if (attemptMqttConnect()) {
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
