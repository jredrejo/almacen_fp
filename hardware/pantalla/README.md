# M5Stack Tab5 - Pantalla con cámara MIPI-CSI

Firmware para el M5Stack Tab5 (ESP32-P4) usando PlatformIO con framework Arduino
y componentes ESP-IDF en modo híbrido.

## Requisitos

- [PlatformIO](https://platformio.org/) (CLI o integración en IDE)
- Plataforma pioarduino con soporte ESP32-P4 (se descarga automáticamente)

## Configuración

Antes de compilar, copia una de las configuraciones disponibles como `config.h`:

```bash
cp include/config.h.instituto include/config.h   # para el instituto
cp include/config.h.casa include/config.h         # para desarrollo en casa
```

## Compilar y flashear

```bash
pio run -e tab5            # compilar
pio run -e tab5 -t upload  # flashear
pio device monitor         # monitor serie
```

## Componentes de cámara (components/)

El directorio `components/` contiene componentes Espressif de vídeo/cámara
necesarios para el build híbrido Arduino + ESP-IDF. En este modo, PlatformIO
**no ejecuta el gestor de componentes ESP-IDF**, por lo que estos componentes
deben estar presentes localmente y están versionados en git:

| Componente | Versión | Descripción |
|---|---|---|
| esp_cam_sensor | 0.7.1 | Driver sensor cámara SC202CS |
| esp_video | 0.7.0 | Pipeline de vídeo MIPI-CSI |
| esp_sccb_intf | 0.0.4 | Interfaz SCCB (I2C para cámaras) |
| esp_ipa | 0.1.0 | Algoritmos de procesado de imagen (AE/AWB/AGC) |

Estas versiones son necesarias para la compatibilidad con el build híbrido
Arduino + ESP-IDF configurado en `platformio.ini`. No borrar ni actualizar
sin verificar que la compilación sigue funcionando.

El directorio `managed_components/` (gitignored) se descarga automáticamente
por el gestor de componentes de ESP-IDF durante la primera compilación.

## Notas

- `partitions/default_16MB.csv` — tabla de particiones personalizada para flash de 16MB.
- `sdkconfig.defaults` / `sdkconfig.tab5` — configuración de SDK para el Tab5.
