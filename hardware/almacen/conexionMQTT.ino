// Maquina de estados para reconexion MQTT no bloqueante con backoff exponencial
// (enum MqttState and extern mqttState declared in opciones.h)

// Variables de estado globales
MqttState mqttState = MS_DISCONNECTED;
unsigned long lastReconnectAttempt = 0;
unsigned long reconnectInterval = 1000;  // Empieza en 1s
const unsigned long MAX_RECONNECT_INTERVAL = 30000;  // Maximo 30s

/**
 * Intenta conectar al broker MQTT con LWT configurado
 * @return true si la conexion fue exitosa, false en caso contrario
 */
bool attemptMqttConnect() {
  // Construir payload LWT para cuando el dispositivo se desconecte (D-08)
  char lwt[192];
  snprintf(lwt, sizeof(lwt),
           "{\"device_id\":\"%s\",\"role\":\"%s\",\"aula_id\":\"%s\",\"status\":\"offline\"}",
           DEVICE_ID, ROLE, aulaId);

#ifdef DEBUG
  Serial.println("Intentando conectar MQTT con LWT...");
#endif

  // Conectar con LWT: topic, QoS=1, retain=true
  if (client.connect(DEVICE_ID, mqttUser, mqttPassword,
                     "rfid/sistema", 1, true, lwt)) {
    // Conexion exitosa - publicar mensaje online retenido
    char ts[32];
    obtenerFechaHoraUTC(ts, sizeof(ts));

    String ip = WiFi.localIP().toString();
    char onlineMsg[256];
    snprintf(onlineMsg, sizeof(onlineMsg),
             "{\"device_id\":\"%s\",\"role\":\"%s\",\"aula_id\":\"%s\","
             "\"status\":\"online\",\"ip\":\"%s\",\"version\":\"%s\","
             "\"timestamp\":\"%s\"}",
             DEVICE_ID, ROLE, aulaId, ip.c_str(), VERSION, ts);

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
    case MS_CONNECTED:
      // Verificar si seguimos conectados
      if (!client.connected()) {
        // Perdimos la conexion, transicionar a DESCONECTADO
        mqttState = MS_DISCONNECTED;
        reconnectInterval = 1000;  // Resetear intervalo de reconexion
#ifdef DEBUG
        Serial.println("MQTT desconectado - iniciando reconexion");
#endif
      }
      break;

    case MS_DISCONNECTED:
      // Intentar conectar inmediatamente
      if (attemptMqttConnect()) {
        mqttState = MS_CONNECTED;
      } else {
        // Fallo de conexion - esperar antes de reintentar
        mqttState = MS_WAITING_RETRY;
        lastReconnectAttempt = millis();
#ifdef DEBUG
        Serial.print("Reconexion fallida - siguiente intento en ");
        Serial.print(reconnectInterval);
        Serial.println(" ms");
#endif
      }
      break;

    case MS_WAITING_RETRY:
      // Verificar si es tiempo de reintentar
      if (millis() - lastReconnectAttempt >= reconnectInterval) {
        if (attemptMqttConnect()) {
          mqttState = MS_CONNECTED;
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
