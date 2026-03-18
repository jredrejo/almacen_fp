#ifndef SOUND_MANAGER_H
#define SOUND_MANAGER_H

// =============================================================================
// Gestor de sonido para Tab5 - Tonos diferenciados para detecciones RFID
// Producto: 1 beep 1200Hz 150ms
// Persona: 2 beeps 800Hz 100ms (no bloqueante con timer)
// =============================================================================

#include <M5Unified.h>

// --- Estado para doble tono de persona (no bloqueante) ---
static bool segundoTonoPendiente = false;
static unsigned long tiempoSegundoTono = 0;

/**
 * Configura el altavoz con volumen medio.
 * Llamar una vez en setup() despues de M5.begin().
 */
inline void setupSpeaker() {
  M5.Speaker.setVolume(128);  // Volumen medio (0-255)
}

/**
 * Reproduce un tono medio-agudo para deteccion de producto.
 * Un solo beep de 1200Hz durante 150ms.
 * Tambien se usa para EPC desconocido y API inalcanzable.
 */
inline void reproducirTonoProducto() {
  M5.Speaker.tone(1200, 150);
}

/**
 * Reproduce doble tono rapido para deteccion de persona.
 * Primer beep 800Hz 100ms inmediato, segundo beep programado
 * con timer no bloqueante (se ejecuta en actualizarSonido).
 */
inline void reproducirTonoPersona() {
  M5.Speaker.tone(800, 100);
  segundoTonoPendiente = true;
  tiempoSegundoTono = millis() + 200;  // Pausa de 200ms antes del segundo tono
}

/**
 * Actualiza el sistema de sonido. Debe llamarse en cada iteracion del loop().
 * Gestiona el segundo tono pendiente de persona de forma no bloqueante.
 */
inline void actualizarSonido() {
  if (segundoTonoPendiente && millis() >= tiempoSegundoTono) {
    M5.Speaker.tone(800, 100);
    segundoTonoPendiente = false;
  }
}

#endif // SOUND_MANAGER_H
