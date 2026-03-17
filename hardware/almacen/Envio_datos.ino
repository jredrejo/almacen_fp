void envio_datos(uint8_t* uid) {
  char hex_uid[25] = { 0 };
  for (uint8_t i = 0; i < 12; i++) {
    sprintf(hex_uid + i * 2, "%02X", uid[i]);
  }

  // Buffer para la fecha/hora formateada
  char timestamp[32];
  obtenerFechaHora(timestamp, sizeof(timestamp));

  char payload[256];
  snprintf(payload, sizeof(payload),
           "{\"aula_id\":\"%s\",\"epc\":\"%s\",\"timestamp\":\"%s\"}",
           aulaId,
           hex_uid,
           timestamp);

  // Publicar primero a lectura (critico para registro en Django)
  char topic[64];
  snprintf(topic, sizeof(topic), "rfid/lectura/%s", aulaId);

  if (client.publish(topic, payload)) {
    // Solo publicar a pantalla si lectura fue exitosa
    snprintf(topic, sizeof(topic), "rfid/pantalla/%s", aulaId);
    client.publish(topic, payload);
  }
#ifdef DEBUG
  else {
    Serial.println("Error MQTT publicacion lectura");
  }
#endif
}
