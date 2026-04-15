#ifndef SOUND_MANAGER_H
#define SOUND_MANAGER_H

// =============================================================================
// Gestor de sonido para Tab5 - Sonido de obturador de camara real
// Usa archivo WAV (foto.wav) cargado desde SD a PSRAM
// M5.Speaker.playWav() reproduce los datos PCM del WAV
// El mismo sonido se usa para producto, persona y EPC desconocido
// =============================================================================

#include <M5Unified.h>

// --- Puntero a datos WAV cargados desde SD (inicializado en main.cpp) ---
extern uint8_t* fotoWavData;
extern size_t fotoWavSize;

/**
 * Configura el altavoz al volumen maximo.
 * Llamar una vez en setup() despues de M5.begin().
 */
inline void setupSpeaker() {
  M5.Speaker.setVolume(255);  // Volumen maximo (0-255)
}

/**
 * Reproduce el sonido de obturador de camara desde datos WAV en PSRAM.
 * El archivo foto.wav es PCM 16-bit stereo 44100Hz.
 * M5.Speaker.playWav() decodifica el header RIFF automaticamente.
 * Si el WAV no se cargo (fotoWavData==nullptr), no reproduce nada.
 */
inline void reproducirObturador() {
  if (fotoWavData != nullptr && fotoWavSize > 0) {
    M5.Speaker.playWav(fotoWavData, fotoWavSize, 1, -1, true);
  }
}

/**
 * Reproduce sonido de obturador para deteccion de producto.
 * Mantiene nombre original para compatibilidad con main.cpp.
 */
inline void reproducirTonoProducto() {
  reproducirObturador();
}

/**
 * Reproduce sonido de obturador para deteccion de persona.
 * Mantiene nombre original para compatibilidad con main.cpp.
 */
inline void reproducirTonoPersona() {
  reproducirObturador();
}

/**
 * Actualiza el sistema de sonido. Llamar en cada iteracion del loop().
 * Con playWav no hay segundo tono pendiente, pero se mantiene la
 * funcion para compatibilidad con main.cpp.
 */
inline void actualizarSonido() {
  // No-op: playWav gestiona la reproduccion internamente
}

#endif // SOUND_MANAGER_H
