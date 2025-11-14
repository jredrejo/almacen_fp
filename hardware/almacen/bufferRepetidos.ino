// ===== BUFFER PARA EVITAR ENVÍOS DUPLICADOS DE UID =====
struct UidEntry {
  uint8_t uid[12];
  unsigned long timestamp;
  bool active;
};

UidEntry uidBuffer[uidBufferSize];
int uidBufferIndex = 0;

// Initialize the UID buffer
void initUidBuffer() {
  for (int i = 0; i < uidBufferSize; i++) {
    memset(uidBuffer[i].uid, 0, 12);
    uidBuffer[i].timestamp = 0;
    uidBuffer[i].active = false;
  }
}

// Comprueba si el UID ya existe en el buffer y todavía es válido (no ha pasado el TTL)
bool isUidInBuffer(uint8_t* uid) {
  unsigned long currentTime = millis();

  for (int i = 0; i < uidBufferSize; i++) {
    if (uidBuffer[i].active) {
      // Comprueba si ha expirado
      if (currentTime - uidBuffer[i].timestamp > uidTTL) {
        uidBuffer[i].active = false;
#ifdef DEBUG
        Serial.print("UID buffer entry ");
        Serial.print(i);
        Serial.println(" expired");
#endif
        continue;
      }

      // Comprueba si coinciden los UID
      if (memcmp(uidBuffer[i].uid, uid, 12) == 0) {
#ifdef DEBUG
        Serial.print("UID found in buffer at index ");
        Serial.print(i);
        Serial.print(" (age: ");
        Serial.print((currentTime - uidBuffer[i].timestamp) / 1000.0);
        Serial.println("s)");
#endif
        return true;
      }
    }
  }
  return false;
}

// Añade el UID al buffer (el buffer funciona de forma circular, FIFO)
void addUidToBuffer(uint8_t* uid) {
  memcpy(uidBuffer[uidBufferIndex].uid, uid, 12);
  uidBuffer[uidBufferIndex].timestamp = millis();
  uidBuffer[uidBufferIndex].active = true;

#ifdef DEBUG
  Serial.print("UID added to buffer at index ");
  Serial.println(uidBufferIndex);
#endif

  // Mueve a la siguiente posición (circular)
  uidBufferIndex = (uidBufferIndex + 1) % uidBufferSize;
}

// Limpieza de entradas expiradas (opcional, para debugging)
void cleanupUidBuffer() {
  unsigned long currentTime = millis();
  int cleaned = 0;

  for (int i = 0; i < uidBufferSize; i++) {
    if (uidBuffer[i].active && (currentTime - uidBuffer[i].timestamp > uidTTL)) {
      uidBuffer[i].active = false;
      cleaned++;
    }
  }

#ifdef DEBUG
  if (cleaned > 0) {
    Serial.print("Cleaned ");
    Serial.print(cleaned);
    Serial.println(" expired entries from buffer");
  }
#endif
}
