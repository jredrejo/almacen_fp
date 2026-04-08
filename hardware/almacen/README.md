# hardware/almacen -- ESP32 RFID Reader

Lector RFID con ESP32 + R200 que publica lecturas por MQTT.

## Contrato de integración

El contrato MQTT entre este lector, la pantalla Tab5 y Django vive en
[`docs/CONTRACT.md`](../../docs/CONTRACT.md) (fuente de verdad).
No modificar topics, payloads, QoS ni formatos sin actualizar primero ese documento.

## Archivos clave

- `almacen.ino` -- entrypoint, NTP sync, loop principal
- `conexionMQTT.ino` -- conexion MQTT, LWT, `rfid/sistema` online retained
- `Envio_datos.ino` -- publish de lecturas en `rfid/lectura/{aula_id}`
- `opciones.h` -- `aulaId`, `DEVICE_ID`, `ROLE`
- `bufferRepetidos.ino` -- dedup UID buffer (base del at-least-once)
