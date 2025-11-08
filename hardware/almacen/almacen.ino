/* PROGRAMA PARA LA GESTIÓN DE ALMACEN (ENTRADA/SALIDA MEDIANTE MQTT+RFID)       */
/* Autor: Raúl Diosdado                                                          */
/* Fecha: 11/10/2025                                                             */
/* PLACA: M5STACK (Procesador: ESP32-C6)                                         */
/* El programa realizará las siguientes funciones:                               */
/*    -Lectura de los datos del sensor RFID (R200)                               */
/*    -Envio de los datos a través de MQTT a servidor via WiFi                   */
/*-------------------------------------------------------------------------------*/

//Definición de librerías y elementos externos
#include "credenciales.h"
#include <WiFi.h>          //Librería para la conexión a la wifi
#include <PubSubClient.h>  //Librería para uso de MQTT https://github.com/knolleary/pubsubclient
#include "R200.h"          //Librería para el uso del RFID R200 https://github.com/playfultechnology/arduino-rfid-R200
#include <WiFiUdp.h>
#include <NTPClient.h>    // para ponerlo en hora a través de Internet
#include <Timezone.h>  // para el cambio de hora
WiFiClient esp32Client;
PubSubClient client(esp32Client);
R200 rfid;
WiFiUDP ntpUDP;
NTPClient timeClient(ntpUDP, "pool.ntp.org", 0, 60000); // Sin offset, porque se hará con Timezone


// Definición reglas horario de verano (Ejemplo Europa Central)
TimeChangeRule CEST = {"CEST", Last, Sun, Mar, 2, 120}; // Horario verano UTC+2h
TimeChangeRule CET = {"CET", Last, Sun, Oct, 3, 60};    // Horario normal UTC+1h
Timezone CE(CEST, CET);

//Comentar esta linea para eliminar el modo DEBUG
#define DEBUG 1


//Definicion de los pines (HARDWARE)
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
// Pines digitales I/O


//Variables Globales
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=


//Temporizaciones y contadores
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=


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
  timeClient.setTimeOffset(7200); // GMT + 2
  timeClient.update();
  setTime(timeClient.getEpochTime());
 rfid.dumpModuleInfo();



#ifdef DEBUG
  Serial.println("Configuramos mqtt: ");
#endif
  client.setServer(mqtt_server, 1883);  //Fija la dirección y puerto del servidor MQTT
#ifdef DEBUG
  Serial.println("Configuramos mqtt callback: ");
#endif
  client.setCallback(callback);  //Define al función de callback para la recepción de mensajes MQTT

 delay(1000);
 //rfid.setMultiplePollingMode(true);
 delay(100);

}
unsigned long lastResetTime = 0;
unsigned long lastDebugTime = 0;
uint8_t lastUid[12] = {0};  // Para detectar cambios de tarjeta


void uid_to_string(uint8_t *uid, char *str) {
  for (int i = 0; i < 12; i++) {
    sprintf(&str[i*2], "%02X", uid[i]);
  }
  str[24] = '\0';
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



 // IMPORTANTE: Procesar datos del RFID en cada iteración
  // El lector enviará datos continuamente en multiple polling mode
  rfid.loop();

  // Verificar si hay una tarjeta presente
  const uint8_t blankUid[12] = {0};

  if (memcmp(rfid.uid, blankUid, 12) != 0) {
    // Hay una tarjeta detectada

    // Verificar si es una tarjeta diferente a la anterior
    if (memcmp(rfid.uid, lastUid, 12) != 0) {
      // Nueva tarjeta detectada
#ifdef DEBUG
      Serial.print("Nueva tarjeta detectada: ");
      rfid.dumpUIDToSerial();
      Serial.println();
#endif

      // Guardar el UID actual
      memcpy(lastUid, rfid.uid, 12);

      // Enviar datos por MQTT
      envio_datos(rfid.uid);
    }
  } else {
    // No hay tarjeta (limpieza)
    if (memcmp(lastUid, blankUid, 12) != 0) {
      // La tarjeta acaba de ser removida
#ifdef DEBUG
      Serial.print("Tarjeta removida: ");
      Serial.println();
#endif
      memset(lastUid, 0, 12);
    }
  }

#ifdef DEBUG
  // Debug info periódico (cada 5 segundos)
  if (millis() - lastDebugTime > 5000) {
    Serial.println("Loop activo - Multiple Polling en funcionamiento");
    lastDebugTime = millis();
  }
#endif

  // Check if a card is present
  // const uint8_t blankUid[12] = { 0 };
  // if (memcmp(rfid.uid, blankUid, sizeof(rfid.uid)) != 0) {
  //   envio_datos(rfid.uid);
  // }
}
