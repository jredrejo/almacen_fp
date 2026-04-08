// Credenciales del almacen
const char* clientId = "almacen_1";
const char* aulaId = "1";

const float potenciaAntena = 26.0;  //Entre 15 y 26 dBm

const byte uidBufferSize = 10;      // hasta 10 ids en el buffer para evitar envíos repetidos
const long uidTTL = 10000;          // 10 seconds TTL

//Mixer Gain, IF amplifier gain, Signal demodulation threshold
const uint8_t mixerGain = 5;        //2=6dB, 3=9dB.. 6=16dB , default=3
const uint8_t ganacia_IF = 6;           //0=12dB,6=36dB,7=40dB, default=6
const uint16_t demodulationThreshold = 150;        // default 176


const char* version_almacen="0.1.0";

// Identity for rfid/sistema messages (D-08, docs/CONTRACT.md)
// Keep in sync with aulaId
const char* DEVICE_ID = "almacen-aula1";  // device_id: role + aula
const char* ROLE      = "reader";
const char* VERSION   = "1.1.0";

// MQTT reconnect state machine (used in loop + conexionMQTT)
enum MqttState {
  MS_CONNECTED,
  MS_DISCONNECTED,
  MS_WAITING_RETRY
};
extern MqttState mqttState;