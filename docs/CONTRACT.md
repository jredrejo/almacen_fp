# Almacen FP -- Contrato de Integracion

Fuente de verdad del contrato MQTT + REST + Resilience + Tests entre
`hardware/almacen` (reader), `hardware/pantalla` (display) y `almacen/` (Django).

Ultima actualizacion: Phase 6 (MQTT). Phases 7-9 rellenaran REST/Resilience/Tests.

---

## MQTT

### Topics

| topic | publisher | subscriber(s) | QoS (wire) | retain | purpose |
|---|---|---|---|---|---|
| `rfid/lectura/{aula_id}` | reader | Django listener, pantalla | 0 (see Semantics) | false | RFID read events |
| `rfid/sistema` | reader + pantalla | Django listener (logging only) | 1 (subscribe), 1 (LWT) | true | presence + LWT |

### Payload schema -- `rfid/lectura/{aula_id}`

```json
{"aula_id": "3", "epc": "E2000017221101441890C7B5", "timestamp": "2026-04-08T10:30:00Z"}
```

Required fields: `aula_id` (string), `epc` (string), `timestamp` (string).
Unknown extra fields MUST be ignored.

### Payload schema -- `rfid/sistema` (online + LWT)

```json
{"device_id": "almacen-aula3", "role": "reader", "aula_id": "3",
 "status": "online", "ip": "192.168.1.42", "version": "1.2.0",
 "timestamp": "2026-04-08T10:30:00Z"}
```

- `device_id`: unified identity (replaces `reader_id` and `client_id`).
- `role`: `"reader"` | `"display"`.
- `status`: `"online"` | `"offline"`. LWT sends `"offline"`.
- `ip`, `version`, `timestamp` optional in LWT.

### Field formats (normative)

- **`aula_id`**: decimal integer string, canonical form (`"3"`, not `3` or `"03"`). String in payload, `int` only inside Django.
- **`epc`**: hex uppercase, regex `^[0-9A-F]{8,24}$`. Reader MUST uppercase before publishing; Django MUST re-validate (defence in depth).
- **`timestamp`**: ISO-8601 UTC with literal `Z` suffix, format `YYYY-MM-DDTHH:MM:SSZ`. Reader emits directly in UTC via `gmtime()`. Django MUST reject naive or offset-only forms.

### QoS & delivery semantics

- Subscribe QoS: 1 (reader + pantalla + Django listener).
- LWT QoS on `rfid/sistema`: 1, retain=true.
- **Publish QoS on `rfid/lectura/{aula_id}` is 0 on the wire** -- `PubSubClient` does not support QoS>0 on `publish()` (see 06-RESEARCH.md Pitfall 5). End-to-end at-least-once is achieved via: (a) reader UID dedup buffer (`bufferRepetidos.ino`), (b) Django `last_epc:{aula_id}` cache (35s TTL). This is an acknowledged library limitation; do NOT "fix" by calling `client.publish(topic, payload, 1)` -- that overload does not exist.

### Listener validation rules (MQTT-06)

On every message on `rfid/lectura/{aula_id}`, Django MUST validate and on failure log and discard WITHOUT crashing. Rejection reasons (enum):

- `json_decode` -- payload is not valid JSON
- `schema` -- missing `aula_id`, `epc` or `timestamp`
- `epc_format` -- `epc` fails `^[0-9A-F]{8,24}$`
- `ts_format` -- `timestamp` fails `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`
- `aula_mismatch` -- `data["aula_id"]` (string-compared) != `aula_id` from topic

Rejections MUST be logged via stdlib `logging.warning("mqtt_payload_rejected", extra={"topic", "reason", "payload_preview"[:80]})` and counted in an in-process `collections.Counter`. The counter MUST be logged aggregated at listener shutdown.

`aula_mismatch` policy: strict reject (not warn-and-continue).

### Audit findings -- hallazgos -> fix -> smoke

| ID | Hallazgo | Fix | Smoke verificado |
|----|----------|-----|------------------|
| A1 | Reader publica `rfid/lectura/{aula}` con QoS 0 implicito (PubSubClient no soporta QoS>0 en publish) | Document QoS 0 reality; rely on reader dedup + Django cache | [x] Documented, reader dedup + Django cache confirm at-least-once |
| A2 | Dual-publish a `rfid/pantalla/{aula}` desde reader | Eliminar las dos lineas del dual-publish en `Envio_datos.ino` | [x] grep confirms no rfid/pantalla/ publish; pantalla still receives events via rfid/lectura |
| A3 | Pantalla se suscribe a `MQTT_TOPIC_PANTALLA` en vez de a `rfid/lectura/{AULA_ID}` | Cambiar suscripcion a `rfid/lectura/{AULA_ID}`; renombrar macro | [x] grep confirms MQTT_TOPIC_LECTURA; live smoke pantalla displays event |
| A4 | Reader timestamp usa hora local Espana (CET/CEST) sin sufijo `Z` | Nuevo helper `obtenerFechaHoraUTC()` con `gmtime()` + `"%Y-%m-%dT%H:%M:%SZ"` | [x] Django receives timestamps with Z suffix, no naive rejection on happy path |
| A5 | Campo temporal se llama `timestamp` en todos los componentes; CONTEXT.md proponia renombrar a `ts` | OUT OF SCOPE -- Deferred: keep `timestamp`, user decision Phase 6 plan-phase | [-] OUT OF SCOPE per user decision Phase 6 -- field stays 'timestamp' |
| A6 | Django no valida formato hex del `epc` antes de consultar `Producto` | Anadir `validate_epc(epc)` con regex `^[0-9A-F]{8,24}$` | [x] mosquitto_pub zz → reason=epc_format, counter +1 |
| A7 | Django acepta `timestamp` naive via `fromisoformat` + `make_aware`; D-10 requiere rechazar | Reemplazar con regex gate + `strptime("%Y-%m-%dT%H:%M:%SZ")` + `.replace(tzinfo=timezone.utc)` | [x] mosquitto_pub '2026-04-08 10:30' → reason=ts_format, counter +1 |
| A8 | Django no tiene rechazo estructurado ni contadores; solo `logger.warning/error` simples | Anadir `self.reject_counts = Counter()`, helper `reject(reason)`, log con `extra={"topic","reason","payload_preview"}`, volcado en shutdown | [x] 5/5 reject reasons logged with reason+topic+payload; shutdown summary shows counts |
| A9 | `aula_mismatch` entre topic y payload se loggea como warning y continua | Sustituir por `reject("aula_mismatch"); return` | [x] aula_id=9 on topic /1 → reason=aula_mismatch, counter +1 |
| A10 | LWT reader usa `reader_id`, LWT pantalla usa `client_id`; campos online divergen | Unificar a `device_id` + `role` en ambos; anadir `version` + `timestamp` en ambos online | [x] rfid/sistema shows device_id+role for both reader and pantalla; retained offline LWT has device_id |
| A11 | Broker conserva retained anterior en `rfid/sistema` con `reader_id`/`client_id` | Anadir paso en smoke test: `mosquitto_pub -h <broker> -t rfid/sistema -r -n` antes del primer arranque con firmware nuevo | [x] Stale retained cleared; new device overwrote on boot |
| A12 | Los 3 READMEs no referencian contrato canonico (no existia `docs/CONTRACT.md`) | Crear `docs/CONTRACT.md` con seccion MQTT + anadir link en los 3 README | [x] File exists, 3 READMEs link to it |
| A13 | Listener no persiste tabla de rechazos en CONTRACT.md | Escribir tabla hallazgo -> fix -> smoke verificado en `docs/CONTRACT.md` (esta seccion) | [x] This row -- table itself is now filled in |

### Deployment / smoke procedure

Document the smoke steps (to be executed in Plan 05):

1. Clear stale retained message: `mosquitto_pub -h <broker> -t rfid/sistema -r -n`.
2. Re-flash reader and pantalla with new firmware.
3. Start Django listener: `python manage.py mqtt_listener`.
4. Happy path: simulate 1 real read from reader; confirm pantalla renders and Django persists.
5. Malformed-path (one per rejection reason), injected via `mosquitto_pub -h <broker> -t rfid/lectura/3 -m '<payload>'`:
   - `json_decode`: `not json`
   - `schema`: `{"aula_id":"3","epc":"E200..."}`
   - `epc_format`: `{"aula_id":"3","epc":"zz","timestamp":"2026-04-08T10:30:00Z"}`
   - `ts_format`: `{"aula_id":"3","epc":"E2000017221101441890C7B5","timestamp":"2026-04-08 10:30"}`
   - `aula_mismatch`: to topic `rfid/lectura/3`, payload with `"aula_id":"9"`
6. Confirm listener logs one `mqtt_payload_rejected` per case, never crashes, and shutdown summary shows counts.

---

## REST

_To be defined in Phase 7 -- REST API Contract Alignment._

---

## Resilience

_To be defined in Phase 8 -- Resilience & Error Handling._

---

## Tests

_To be defined in Phase 9 -- Integration Tests & CI._
