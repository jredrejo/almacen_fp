void envio_datos(uint8_t* uid) {
  char hex_uid[25] = { 0 };
  for (uint8_t i = 0; i < 12; i++) {
    sprintf(hex_uid + i * 2, "%02X", uid[i]);  // %02X = uppercase, satisfies epc regex
  }

  char ts[32];
  obtenerFechaHoraUTC(ts, sizeof(ts));  // D-10: UTC with Z

  char payload[256];
  // Field name is 'timestamp' (NOT 'ts') -- user decision Phase 6
  snprintf(payload, sizeof(payload),
           "{\"aula_id\":\"%s\",\"epc\":\"%s\",\"timestamp\":\"%s\"}",
           aulaId, hex_uid, ts);

  char topic[64];
  snprintf(topic, sizeof(topic), "rfid/lectura/%s", aulaId);
  client.publish(topic, payload);
  // NOTE: PubSubClient has NO QoS-1 publish overload. Wire QoS is 0.
  // End-to-end at-least-once = reader UID dedup buffer + Django last_epc cache.
  // A2: removed former dual-publish to pantalla topic.
}
