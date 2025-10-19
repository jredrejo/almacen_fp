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
#include <WiFi.h>             //Librería para la conexión a la wifi
#include <PubSubClient.h>     //Librería para uso de MQTT https://github.com/knolleary/pubsubclient
#include "R200.h"             //Librería para el uso del RFID R200 https://github.com/playfultechnology/arduino-rfid-R200

WiFiClient esp32Client;
PubSubClient client(esp32Client);
R200 rfid;

//Comentar esta linea para eliminar el modo DEBUG 
#define DEBUG 1


//Definicion de los pines (HARDWARE)
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
// Pines digitales I/O


//Variables Globales
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=


//Temporizaciones y contadores
//-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=


void setup() 
{
  #ifdef DEBUG
  Serial.begin(115200);                     //Inicializa la comunicación serie
  Serial.println("Comienza el programa");
  #endif
  
  setup_wifi();                             //Configura y conecta a la WiFi

  rfid.begin(&Serial2, 115200, 16, 17);     //Habilita un segundo puerto serie para la comunicación con la tarjeta RFID (hadrware serial, baudrate, rx,tx)
  // Get info
  rfid.dumpModuleInfo();

  client.setServer(mqtt_server, 1883);      //Fija la dirección y puerto del servidor MQTT
  client.setCallback(callback);             //Define al función de callback para la recepción de mensajes MQTT
}

void loop() 
{
  //Si en algún momento se desconecta de la WiFI
  if(WiFi.status() != WL_CONNECTED)
  {
    setup_wifi();
  }
  //Si no está conectado al servidor MQTT
  if (!client.connected()) 
  {
    reconexion();
  }
  client.loop();

}
