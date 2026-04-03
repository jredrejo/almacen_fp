/**
 * Glue de deteccion para build hibrido Arduino+ESP-IDF.
 *
 * esp_video_init() y la ISP buscan sensores e IPAs via arrays en secciones
 * especiales del linker. En pioarduino no existen esas secciones, asi que
 * definimos los simbolos start aqui y end via --defsym en platformio.ini.
 */

// --- Sensor SC202CS ---
#include "esp_cam_sensor_types.h"
#include "sc202cs.h"

extern esp_cam_sensor_device_t *sc202cs_detect(esp_cam_sensor_config_t *config);

const esp_cam_sensor_detect_fn_t __esp_cam_sensor_detect_fn_array_start
    __attribute__((used, aligned(4))) = {
    .detect = (esp_cam_sensor_device_t *(*)(void *))sc202cs_detect,
    .port = ESP_CAM_SENSOR_MIPI_CSI,
    .sccb_addr = SC202CS_SCCB_ADDR,
};

_Static_assert(sizeof(esp_cam_sensor_detect_fn_t) == 12,
    "sizeof(esp_cam_sensor_detect_fn_t) cambio: actualizar --defsym en platformio.ini");

// --- IPA (Image Processing Algorithms): AE, AWB, AGC, etc. ---
// No incluir esp_ipa_detect.h para evitar conflicto de tipo con el extern
// (header declara __start como struct individual, necesitamos array).

// Tipo opaco de IPA
struct esp_ipa;
typedef struct esp_ipa esp_ipa_t;

// Struct de deteccion IPA (replicada de esp_ipa_detect.h)
typedef struct {
    const char *name;
    esp_ipa_t *(*detect)(void *);
} ipa_detect_entry_t;

// Funciones de deteccion de IPA definidas en libesp_ipa.a del componente
extern esp_ipa_t *__esp_ipa_detect_fn_awb_gray_world(void *config);
extern esp_ipa_t *__esp_ipa_detect_fn_agc_threshold(void *config);
extern esp_ipa_t *__esp_ipa_detect_fn_denoising_gain_feedback(void *config);
extern esp_ipa_t *__esp_ipa_detect_fn_sharpen_freq_feedback(void *config);
extern esp_ipa_t *__esp_ipa_detect_fn_gamma_lumma_feedback(void *config);
extern esp_ipa_t *__esp_ipa_detect_fn_cc_linear(void *config);

// Array contiguo de detectores IPA. __esp_ipa_detect_array_start es el nombre
// que esp_video busca. __end (via --defsym +48) apunta despues del ultimo.
ipa_detect_entry_t __esp_ipa_detect_array_start[]
    __attribute__((used, aligned(4))) = {
    { .name = "awb.gray",      .detect = __esp_ipa_detect_fn_awb_gray_world },
    { .name = "agc.threshold", .detect = __esp_ipa_detect_fn_agc_threshold },
    { .name = "denoising.gf",  .detect = __esp_ipa_detect_fn_denoising_gain_feedback },
    { .name = "sharpen.ff",    .detect = __esp_ipa_detect_fn_sharpen_freq_feedback },
    { .name = "gamma.lf",      .detect = __esp_ipa_detect_fn_gamma_lumma_feedback },
    { .name = "cc.linear",     .detect = __esp_ipa_detect_fn_cc_linear },
};

_Static_assert(sizeof(ipa_detect_entry_t) == 8,
    "sizeof(ipa_detect_entry_t) cambio: actualizar --defsym en platformio.ini");
