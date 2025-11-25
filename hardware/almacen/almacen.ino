/* PROGRAMA PARA LA GESTIÓN DE ALMACEN (ENTRADA/SALIDA MEDIANTE MQTT+RFID)       */
/* Autores: Raúl Diosdado  /  José L. Redrejo                                    */
/* Fecha: 11/10/2025                                                             */
/* PLACA: M5STACK (Procesador: ESP32-C6)                                         */
/* El programa realizará las siguientes funciones:                               */
/*    -Lectura de los datos del sensor RFID (R200)                               */
/*    -Envio de los datos a través de MQTT a servidor via WiFi                   */
/*-------------------------------------------------------------------------------*/

//Definición de librerías y elementos externos
#include "credenciales.h"
#include "opciones.h"
#include <WiFi.h>          //Librería para la conexión a la wifi
#include <PubSubClient.h>  //Librería para uso de MQTT https://github.com/knolleary/pubsubclient
#include "R200.h"          //Librería para el uso del RFID R200 https://github.com/playfultechnology/arduino-rfid-R200
#include <WiFiUdp.h>
#include <NTPClient.h>  // para ponerlo en hora a través de Internet
#include <Timezone.h>   // para el cambio de hora
WiFiClient esp32Client;
PubSubClient client(esp32Client);
R200 rfid;
WiFiUDP ntpUDP;
NTPClient timeClient(ntpUDP, "pool.ntp.org", 0, 60000);  // Sin offset, porque se hará con Timezone


// Definición reglas horario de verano para España
TimeChangeRule summerTime = { "CEST", Last, Sun, Mar, 1, 120 };
TimeChangeRule winterTime = { "CET", Last, Sun, Oct, 1, 60 };
Timezone spain(summerTime, winterTime);

unsigned long lastDebugTime = 0;
unsigned long lastCleanupTime = 0;

//Comentar esta linea para eliminar el modo DEBUG
#define DEBUG 1


void setup() {
#ifdef DEBUG
  Serial.begin(115200);  //Inicializa la comunicación serie
  Serial.println("Comienza el programa");
#endif


  setup_wifi();  //Configura y conecta a la WiFi

#ifdef DEBUG
  Serial.println("Configuramos el segundo puerto serie: ");
#endif

  rfid.begin(&Serial2, 115200, 16, 17);  //Habilita un segundo puerto serie para la comunicación con la tarjeta RFID (hadrware serial, baudrate, rx,tx)
#ifdef DEBUG
  Serial.println("Iniciado el servidor HTTP");
#endif
  timeClient.begin();
  timeClient.update();
  setTime(timeClient.getEpochTime());
  rfid.dumpModuleInfo();
  initUidBuffer();
  delay(100);
  while (rfid.dataAvailable()) {
    rfid.loop();  // Procesamos toda la respuesta pendiente
  }
  rfid.setPower(potenciaAntena);  // La potencia dependerá del alcance deseado
  uint8_t new_mixer_g = 2;        //2=6dB, 3=9dB.. 6=16dB
  uint8_t new_if_g = 6;           //0=12dB,6=36dB,7=40dB
  uint16_t new_thrd = 176;
  //Mixer Gain, IF amplifier gain, Signal demodulation threshold
  rfid.setDemodulatorParams(new_mixer_g, new_if_g, new_thrd);



#ifdef DEBUG
  Serial.println("Configuramos mqtt: ");
#endif
  client.setServer(mqtt_server, 1883);  //Fija la dirección y puerto del servidor MQTT

  rfid.setMultiplePollingMode(true);
  delay(100);
}


void uid_to_string(uint8_t* uid, char* str) {
  for (int i = 0; i < 12; i++) {
    sprintf(&str[i * 2], "%02X", uid[i]);
  }
  str[24] = '\0';
}


void obtenerFechaHora(char* buffer, size_t bufferSize) {
  time_t utc = now();
  time_t local = spain.toLocal(utc);
  // Convertir time_t a struct tm
  struct tm* timeinfo = localtime(&local);
  strftime(buffer, bufferSize, "%Y-%m-%d %H:%M:%S", timeinfo);
}


void loop() {
  //Si en algún momento se desconecta de la WiFI
  if (WiFi.status() != WL_CONNECTED) {
    setup_wifi();
  }
  //Si no está conectado al servidor MQTT
  if (!client.connected()) {
    reconexion();
  }
  client.loop();

  // Limpiamos el buffer periódicamente
  if (millis() - lastCleanupTime > 2000) {
    cleanupUidBuffer();
    lastCleanupTime = millis();
  }


  // IMPORTANTE: Procesar datos del RFID en cada iteración
  // El lector enviará datos continuamente en multiple polling mode
  rfid.loop();

  // Verificar si hay una tarjeta presente
  const uint8_t blankUid[12] = { 0 };

  if (memcmp(rfid.uid, blankUid, 12) != 0) {
    // Hay una tarjeta detectada

#ifdef DEBUG
    Serial.print("Nueva tarjeta detectada: ");
    rfid.dumpUIDToSerial();
    Serial.println();
#endif

    // Check if UID is in deduplication buffer
    if (!isUidInBuffer(rfid.uid)) {
      // UID not in buffer or expired - send data
#ifdef DEBUG
      Serial.println("UID not in buffer - sending MQTT message");
#endif
      // Enviar datos por MQTT
      envio_datos(rfid.uid);

      // Add UID to buffer
      addUidToBuffer(rfid.uid);
    } else {
      // UID is in buffer and still valid - skip sending
#ifdef DEBUG
      Serial.println("UID in buffer (within TTL) - skipping MQTT publish");
#endif
    }
    // Limpiar el UID después de procesar para evitar múltiples lecturas del mismo tag
    // en la misma o siguientes iteraciones. El buffer (isUidInBuffer) gestiona
    // la deduplicación basada en tiempo.
    memset(rfid.uid, 0, 12);



  }


#ifdef DEBUG
  // Debug info periódico (cada 5 segundos)
  if (millis() - lastDebugTime > 5000) {
    Serial.println("Loop activo - Multiple Polling en funcionamiento");
    lastDebugTime = millis();
  }
#endif


}
