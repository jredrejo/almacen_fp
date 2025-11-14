// Credenciales del almacen
const char* clientId = "almacen_1";
const char* aulaId = "1";

const float potenciaAntena = 19.0;  //Entre 15 y 26 dBm

const byte uidBufferSize = 10;      // hasta 10 ids en el buffer para evitar envíos repetidos
const long uidTTL = 10000;          // 10 seconds TTL