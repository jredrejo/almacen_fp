void envio_datos(uint8_t* uid)
{
  char hex_uid[25] = {0};
  for (uint8_t i = 0; i < 12; i++) {
    sprintf(hex_uid + i * 2, "%02X", uid[i]);
  }

  time_t utc = timeClient.getEpochTime(); // Segundos desde 1970 en UTC
  time_t local = CE.toLocal(utc);
    // Convertir time_t a struct tm
  struct tm* timeinfo = localtime(&local);

  // Buffer para la fecha/hora formateada
  char timestamp[32];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", timeinfo);


  char payload[256];
  snprintf(payload, sizeof(payload),
    "{\"aula_id\":1,\"epc\":\"%s\",\"timestamp\":\"%s\"}",
    hex_uid,
    timestamp
  );

  char topic[64];
  snprintf(topic, sizeof(topic), "rfid/lectura/%s", clientId);

  if (!client.publish(topic, payload)) {
#ifdef DEBUG
    Serial.println("Error MQTT");
#endif
  }
}
