#ifndef DISPLAY_MANAGER_H
#define DISPLAY_MANAGER_H

// =============================================================================
// Gestor de display para Tab5 - Pantalla de notificaciones RFID
// Funciones: boot, notificacion, EPC desconocido, barra estado, reconexion
// Usa M5Canvas para double-buffering y evitar flicker
// =============================================================================

#include <M5GFX.h>
#include <M5Unified.h>

// --- Canvas para double-buffering (se crea en main.cpp) ---
extern M5Canvas canvas;

// --- Constantes de layout ---
static constexpr int SCREEN_WIDTH = 1280;       // Ancho tras rotacion
static constexpr int SCREEN_HEIGHT = 720;        // Alto tras rotacion
static constexpr int STATUS_BAR_HEIGHT = 80;     // Alto de barra de estado inferior
static constexpr int MAIN_ZONE_HEIGHT = 440;      // Zona principal para notificaciones (reducida)
static constexpr int LOG_ZONE_HEIGHT = 200;        // Zona de log de ultimos eventos RFID
static constexpr int LOG_ZONE_Y = MAIN_ZONE_HEIGHT;                     // Y inicio del log (440)
static constexpr int STATUS_BAR_Y = MAIN_ZONE_HEIGHT + LOG_ZONE_HEIGHT; // Y inicio barra estado (640)
static constexpr int MAX_LOG_ENTRIES = 5;          // Maximo de entradas visibles en el log

// --- Colores diferenciados por tipo ---
static constexpr int COLOR_PRODUCTO = TFT_CYAN;       // Cian para productos
static constexpr int COLOR_PERSONA = TFT_YELLOW;      // Amarillo para personas
static constexpr int COLOR_DESCONOCIDO = TFT_ORANGE;  // Naranja para EPC desconocido

// --- Estructura para entrada del log de eventos ---
struct LogEntry {
  char nombre[64];    // Nombre del producto/persona/EPC
  char tipo[16];      // "producto", "persona", "desconocido"
  char hora[6];       // "HH:MM"
  bool activo;        // true si la entrada tiene datos
};

/**
 * Muestra la pantalla de boot con splash.png centrada y mensaje progresivo debajo.
 * @param splashData Datos PNG en PSRAM (puede ser nullptr si no se cargo)
 * @param splashSize Tamano de los datos PNG
 * @param mensaje Texto de estado ("Conectando WiFi...", "Conectando MQTT...", "Listo")
 */
inline void mostrarPantallaBoot(uint8_t* splashData, size_t splashSize, const char* mensaje) {
  canvas.fillScreen(TFT_BLACK);

  // Dibujar splash.png centrada, ligeramente arriba del centro
  if (splashData != nullptr) {
    canvas.drawPng(splashData, splashSize, (1280 - 512) / 2, (720 - 512) / 2 - 40);
  }

  // Texto de estado debajo de la imagen
  canvas.setTextColor(TFT_WHITE);
  canvas.setTextSize(3);
  canvas.setTextDatum(middle_center);
  canvas.drawString(mensaje, 640, (720 - 512) / 2 + 512 + 30);

  canvas.pushSprite(0, 0);
}

/**
 * Dibuja la barra de estado inferior con nombre del aula y reloj.
 * NO hace pushSprite — el caller debe hacerlo despues de dibujar todo.
 * @param nombreAula Nombre del aula (ej: "Aula 1")
 * @param horaLocal Hora formateada como HH:MM
 */
inline void dibujarBarraEstado(const char* nombreAula, const char* horaLocal) {
  // Fondo gris oscuro para la barra
  canvas.fillRect(0, STATUS_BAR_Y, SCREEN_WIDTH, STATUS_BAR_HEIGHT, TFT_DARKGREY);

  canvas.setTextColor(TFT_WHITE);
  canvas.setTextSize(3);

  // Nombre del aula a la izquierda
  canvas.setTextDatum(middle_left);
  canvas.drawString(nombreAula, 20, STATUS_BAR_Y + STATUS_BAR_HEIGHT / 2);

  // Reloj a la derecha
  canvas.setTextDatum(middle_right);
  canvas.drawString(horaLocal, SCREEN_WIDTH - 20, STATUS_BAR_Y + STATUS_BAR_HEIGHT / 2);
}

/**
 * Dibuja la zona de log de eventos con las ultimas detecciones RFID.
 * Fondo gris muy oscuro para separar de la zona principal.
 * NO hace pushSprite — el caller debe hacerlo.
 * @param entries Array de LogEntry con los eventos
 * @param count Numero de entradas activas (0 a MAX_LOG_ENTRIES)
 */
inline void dibujarLogEventos(const LogEntry* entries, int count) {
  // Fondo gris muy oscuro para la zona de log
  canvas.fillRect(0, LOG_ZONE_Y, SCREEN_WIDTH, LOG_ZONE_HEIGHT, 0x2104);

  // Linea separadora superior
  canvas.drawFastHLine(0, LOG_ZONE_Y, SCREEN_WIDTH, TFT_DARKGREY);

  if (count <= 0) return;

  // Calcular altura por entrada
  int entryHeight = LOG_ZONE_HEIGHT / MAX_LOG_ENTRIES;
  canvas.setTextSize(2);
  canvas.setTextDatum(middle_left);

  for (int i = 0; i < count && i < MAX_LOG_ENTRIES; i++) {
    if (!entries[i].activo) continue;

    int y = LOG_ZONE_Y + (i * entryHeight) + entryHeight / 2;

    // Hora en blanco
    canvas.setTextColor(TFT_WHITE);
    canvas.drawString(entries[i].hora, 20, y);

    // Nombre en color segun tipo
    int color = COLOR_DESCONOCIDO;
    if (strcmp(entries[i].tipo, "producto") == 0) {
      color = COLOR_PRODUCTO;
    } else if (strcmp(entries[i].tipo, "persona") == 0) {
      color = COLOR_PERSONA;
    }
    canvas.setTextColor(color);
    canvas.drawString(entries[i].nombre, 120, y);
  }
}

/**
 * Muestra notificacion con nombre de producto o persona en texto grande.
 * Color diferenciado segun tipo. Incluye barra de estado.
 * @param nombre Nombre del producto o persona
 * @param tipo "producto" o "persona"
 * @param nombreAula Nombre del aula para barra de estado
 * @param horaLocal Hora formateada HH:MM para barra de estado
 */
inline void mostrarNotificacion(const char* nombre, const char* tipo, const char* nombreAula, const char* horaLocal) {
  canvas.fillScreen(TFT_BLACK);

  // Determinar color segun tipo
  int color = COLOR_DESCONOCIDO;
  if (strcmp(tipo, "producto") == 0) {
    color = COLOR_PRODUCTO;
  } else if (strcmp(tipo, "persona") == 0) {
    color = COLOR_PERSONA;
  }

  // Nombre en texto grande centrado en zona principal
  canvas.setTextColor(color);
  canvas.setTextSize(7);
  canvas.setTextDatum(middle_center);
  canvas.drawString(nombre, SCREEN_WIDTH / 2, MAIN_ZONE_HEIGHT / 2);

  // Barra de estado inferior
  dibujarBarraEstado(nombreAula, horaLocal);
  // Caller debe llamar a dibujarLogEventos() y canvas.pushSprite(0,0)
}

/**
 * Muestra pantalla de EPC desconocido con mensaje y codigo EPC.
 * Se muestra cuando la API devuelve 404 o error.
 * @param epc Codigo EPC hexadecimal
 * @param nombreAula Nombre del aula para barra de estado
 * @param horaLocal Hora formateada HH:MM para barra de estado
 */
inline void mostrarEpcDesconocido(const char* epc, const char* nombreAula, const char* horaLocal) {
  canvas.fillScreen(TFT_BLACK);

  canvas.setTextColor(COLOR_DESCONOCIDO);

  // Linea 1: "EPC desconocido:"
  canvas.setTextSize(4);
  canvas.setTextDatum(middle_center);
  canvas.drawString("EPC desconocido:", SCREEN_WIDTH / 2, MAIN_ZONE_HEIGHT / 2 - 30);

  // Linea 2: codigo EPC
  canvas.setTextSize(3);
  canvas.drawString(epc, SCREEN_WIDTH / 2, MAIN_ZONE_HEIGHT / 2 + 30);

  // Barra de estado inferior
  dibujarBarraEstado(nombreAula, horaLocal);
  // Caller debe llamar a dibujarLogEventos() y canvas.pushSprite(0,0)
}

/**
 * Muestra pantalla de reconexion con mensaje de error.
 * Se usa cuando WiFi o MQTT pierden conexion.
 * @param mensaje Texto descriptivo ("Reconectando WiFi...", "Reconectando MQTT...")
 */
inline void mostrarPantallaReconexion(const char* mensaje) {
  canvas.fillScreen(TFT_BLACK);

  canvas.setTextColor(TFT_RED);
  canvas.setTextSize(4);
  canvas.setTextDatum(middle_center);
  canvas.drawString(mensaje, SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2);

  canvas.pushSprite(0, 0);
}

#endif // DISPLAY_MANAGER_H
