# almacen/ -- Django backend

Backend Django que persiste lecturas RFID, expone API REST y corre el listener MQTT.

## Contrato de integración

El contrato MQTT + REST entre Django, el lector y la pantalla Tab5 vive en
[`../docs/CONTRACT.md`](../docs/CONTRACT.md) (fuente de verdad).
El listener `management/commands/mqtt_listener.py` valida estrictamente
todo payload entrante contra ese contrato.

## Puntos clave

- `management/commands/mqtt_listener.py` -- subscriber MQTT + validacion + BatchProcessor
- `api.py` / `api_urls.py` -- endpoints REST consumidos por la pantalla
- `api_auth.py` -- auth `Authorization: ApiKey ...`
