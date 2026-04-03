#ifndef CAMERA_MANAGER_H
#define CAMERA_MANAGER_H

#ifdef CAMERA_ENABLED

// =============================================================================
// Gestor de camara para Tab5 - Captura de fotos con sensor SC2356 (MIPI-CSI)
// Funciones: inicializar sensor, capturar frame, codificar JPEG (HW), guardar SD
// Usa ESP-IDF para driver MIPI-CSI y codificador JPEG por hardware del ESP32-P4
// Las fotos se guardan en /fotos/ con nombre de fecha/hora (datestamp)
// =============================================================================

#include <SD.h>
#include <SPI.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include "sys/mman.h"
#ifndef MAP_FAILED
#define MAP_FAILED ((void*)-1)
#endif
#include "linux/videodev2.h"
#include "esp_video_device.h"
#include "esp_video_isp_ioctl.h"
#include "esp_cam_sensor.h"
#include "esp_video_init.h"
#include "esp_video_pipeline_isp.h"
#include "driver/jpeg_encode.h"
#include "esp_clock_output.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

// --- Timezone y now() definidos en main.cpp ---
extern Timezone spain;

// --- Constantes de camara ---
static constexpr int CAM_WIDTH = 1280;       // Resolucion 720p (D-07)
static constexpr int CAM_HEIGHT = 720;
static constexpr int JPEG_QUALITY = 80;      // Balance calidad/tamano (D-08, CAM-03)
// Buffer JPEG maximo: basado en 1280x720 (resolucion nativa del SC202CS)
static constexpr size_t JPEG_OUT_SIZE = (1280 * 720 * 3) / 2;  // ~1.3MB max JPEG

// --- Pines del sensor SC2356 en Tab5 (de BSP oficial) ---
static constexpr gpio_num_t CAM_XCLK_GPIO = GPIO_NUM_36;    // Reloj 24MHz para sensor
static constexpr int CAM_SCCB_SDA = 31;                     // I2C SDA para control sensor
static constexpr int CAM_SCCB_SCL = 32;                     // I2C SCL para control sensor

// --- Estado global de camara ---
static bool camaraInicializada = false;     // true si la camara se inicio correctamente
static bool errorSD = false;                // Flag para indicador visual en display (D-10)
static SemaphoreHandle_t sdMutex = nullptr; // Mutex para acceso SD thread-safe
static SemaphoreHandle_t cameraMutex = nullptr;  // Mutex para pipeline de captura completo
static jpeg_encoder_handle_t jpegEncoder = nullptr;  // Handle del codificador JPEG HW

// --- Handle I2C para SCCB del sensor ---
static i2c_master_bus_handle_t i2cBusHandle = nullptr;

// --- IO Expander PI4IOE5V6408 para camera enable (BSP oficial Tab5) ---
static constexpr uint8_t PI4IOE_ADDR = 0x43;       // Direccion I2C del IO expander
static constexpr uint8_t PI4IOE_REG_OUTPUT = 0x05;  // Registro de salida
static constexpr uint8_t PI4IOE_REG_CONFIG = 0x03;  // Registro de configuracion (0=output, 1=input)
static constexpr uint8_t CAM_EN_PIN_MASK = (1 << 6); // Pin 6 = camera enable

// --- Pipeline V4L2 para captura ---
static int videoFd = -1;                    // File descriptor del dispositivo V4L2
static constexpr int V4L2_NUM_BUFS = 2;     // Buffers dobles para V4L2
static uint8_t* v4l2Buffers[V4L2_NUM_BUFS] = {};  // Buffers mmap del driver
static size_t v4l2BufLengths[V4L2_NUM_BUFS] = {};
static uint32_t capturaAncho = CAM_WIDTH;   // Resolucion real tras negociacion V4L2
static uint32_t capturaAlto = CAM_HEIGHT;
static uint32_t capturaPixFmt = 0;          // Formato pixel real (V4L2_PIX_FMT_*)

// --- Buffer JPEG de salida ---
static uint8_t* jpegBuffer = nullptr;       // Buffer para JPEG codificado (DMA-alineado)

/**
 * Genera el nombre de archivo para una foto con datestamp.
 * Formato: /fotos/YYYY-MM-DD_HH-MM-SS.jpg
 * Si el archivo ya existe (colision de segundo), anade sufijo incremental _2, _3, etc.
 * @param buffer Buffer donde escribir la ruta completa (minimo 64 bytes)
 * @param bufSize Tamano del buffer
 */
inline void generarNombreFoto(char* buffer, size_t bufSize) {
  time_t utc = now();
  time_t local = spain.toLocal(utc);
  struct tm* timeinfo = localtime(&local);

  // Generar nombre base con fecha/hora
  snprintf(buffer, bufSize, "/fotos/%04d-%02d-%02d_%02d-%02d-%02d.jpg",
           timeinfo->tm_year + 1900, timeinfo->tm_mon + 1, timeinfo->tm_mday,
           timeinfo->tm_hour, timeinfo->tm_min, timeinfo->tm_sec);

  // Si el archivo ya existe, buscar sufijo incremental (_2, _3, ...) (per pitfall 6)
  if (SD.exists(buffer)) {
    char base[64];
    snprintf(base, sizeof(base), "/fotos/%04d-%02d-%02d_%02d-%02d-%02d",
             timeinfo->tm_year + 1900, timeinfo->tm_mon + 1, timeinfo->tm_mday,
             timeinfo->tm_hour, timeinfo->tm_min, timeinfo->tm_sec);

    for (int sufijo = 2; sufijo <= 99; sufijo++) {
      snprintf(buffer, bufSize, "%s_%d.jpg", base, sufijo);
      if (!SD.exists(buffer)) break;
    }
  }
}

// Handle para clock output (necesario para mantener la senal activa)
static esp_clock_output_mapping_handle_t camClkHandle = nullptr;

/**
 * Inicializa el reloj de camara 24MHz en GPIO 36 via esp_clock_output.
 * Usa SPLL (480MHz) con divisor 20 = 24MHz exactos.
 * No usa LEDC para evitar conflicto de clock source con M5Unified
 * (M5Unified bloquea todos los timers LEDC a XTAL que no soporta 24MHz).
 */
inline bool iniciarRelojCamara() {
  // Usar SPLL (480MHz) como fuente, luego dividir por 20 = 24MHz
  esp_err_t err = esp_clock_output_start(CLKOUT_SIG_SPLL, CAM_XCLK_GPIO, &camClkHandle);
  if (err != ESP_OK) {
#ifdef DEBUG
    Serial.print("Error: esp_clock_output_start fallo: 0x");
    Serial.println(err, HEX);
#endif
    return false;
  }

  err = esp_clock_output_set_divider(camClkHandle, 20);  // 480MHz / 20 = 24MHz
  if (err != ESP_OK) {
#ifdef DEBUG
    Serial.print("Error: esp_clock_output_set_divider fallo: 0x");
    Serial.println(err, HEX);
#endif
    esp_clock_output_stop(camClkHandle);
    camClkHandle = nullptr;
    return false;
  }

#ifdef DEBUG
  Serial.println("Reloj camara 24MHz iniciado en GPIO 36 (SPLL/20)");
#endif
  return true;
}

/**
 * Inicializa el codificador JPEG por hardware del ESP32-P4.
 * El codificador HW es 10-50x mas rapido que software (libjpeg).
 */
inline bool iniciarJpegEncoder() {
  jpeg_encode_engine_cfg_t encCfg = {
    .intr_priority = 0,
    .timeout_ms = 1000,
  };
  esp_err_t err = jpeg_new_encoder_engine(&encCfg, &jpegEncoder);
  if (err != ESP_OK) {
#ifdef DEBUG
    Serial.print("Error: jpeg_new_encoder_engine fallo: 0x");
    Serial.println(err, HEX);
#endif
    return false;
  }

#ifdef DEBUG
  Serial.println("Codificador JPEG HW iniciado");
#endif
  return true;
}

/**
 * Inicializa el bus I2C para comunicacion SCCB con el sensor de camara.
 * Primero intenta obtener el bus existente (M5.begin() ya lo inicializo),
 * y solo si falla crea uno nuevo. Esto evita conflicto con M5Unified.
 */
inline bool iniciarI2C() {
  // Intentar obtener bus I2C existente de M5Unified
  // M5Unified usa I2C_NUM_1 (sda=31, scl=32) — probar primero ese
  for (int port = I2C_NUM_1; port >= I2C_NUM_0; port--) {
    esp_err_t err = i2c_master_get_bus_handle((i2c_port_t)port, &i2cBusHandle);
    if (err == ESP_OK && i2cBusHandle != nullptr) {
#ifdef DEBUG
      Serial.print("I2C: reutilizando bus existente en puerto ");
      Serial.println(port);
#endif
      return true;
    }
  }

  // Fallback: crear bus nuevo si no existe (poco probable con M5Unified)
#ifdef DEBUG
  Serial.println("I2C: creando bus nuevo (M5Unified no lo inicializo)");
#endif
  i2c_master_bus_config_t i2cConf = {
    .i2c_port = I2C_NUM_1,
    .sda_io_num = (gpio_num_t)CAM_SCCB_SDA,
    .scl_io_num = (gpio_num_t)CAM_SCCB_SCL,
    .clk_source = I2C_CLK_SRC_DEFAULT,
    .glitch_ignore_cnt = 7,
    .flags = {
      .enable_internal_pullup = true,
    },
  };
  if (i2c_new_master_bus(&i2cConf, &i2cBusHandle) != ESP_OK) {
#ifdef DEBUG
    Serial.println("Error: i2c_new_master_bus fallo");
#endif
    return false;
  }
  return true;
}

/**
 * Saca la camara de reset via IO expander PI4IOE5V6408 (pin 6 = CAM_RST).
 * Solo modifica pin 6, sin tocar otros pines (LCD_RST, TP_RST, etc.)
 * que M5Unified ya configuro. NO hacer chip reset (reg 0x01) porque
 * mataria la pantalla y el touch que ya estan activos.
 */
inline bool habilitarCamaraIOExpander() {
  if (i2cBusHandle == nullptr) return false;

  i2c_device_config_t devCfg = {};
  devCfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
  devCfg.device_address = PI4IOE_ADDR;
  devCfg.scl_speed_hz = 400000;

  i2c_master_dev_handle_t dev = nullptr;
  esp_err_t err = i2c_master_bus_add_device(i2cBusHandle, &devCfg, &dev);
  if (err != ESP_OK || dev == nullptr) {
#ifdef DEBUG
    Serial.println("IO Expander: no encontrado en 0x43");
#endif
    return false;
  }

  // Leer direccion actual y configurar pin 6 como output sin tocar otros
  uint8_t regAddr = PI4IOE_REG_CONFIG;  // 0x03 = direction register
  uint8_t dirReg = 0x00;
  i2c_master_transmit_receive(dev, &regAddr, 1, &dirReg, 1, 100);
  dirReg |= CAM_EN_PIN_MASK;  // Pin 6 = output (1=output en PI4IOE5V6408)
  uint8_t dirData[2] = {PI4IOE_REG_CONFIG, dirReg};
  i2c_master_transmit(dev, dirData, 2, 100);

  // Leer salida actual y poner pin 6 HIGH (CAM_RST = fuera de reset)
  regAddr = PI4IOE_REG_OUTPUT;  // 0x05 = output register
  uint8_t outReg = 0x00;
  i2c_master_transmit_receive(dev, &regAddr, 1, &outReg, 1, 100);
  outReg |= CAM_EN_PIN_MASK;
  uint8_t outData[2] = {PI4IOE_REG_OUTPUT, outReg};
  i2c_master_transmit(dev, outData, 2, 100);

  i2c_master_bus_rm_device(dev);
  vTaskDelay(pdMS_TO_TICKS(100));

#ifdef DEBUG
  Serial.println("IO Expander: CAM_RST=HIGH (pin 6)");
#endif
  return true;
}

/**
 * Inicializa el pipeline de video V4L2 para captura MIPI-CSI.
 * Secuencia: esp_video_init -> open -> S_FMT -> REQBUFS -> mmap -> QBUF -> STREAMON.
 * El streaming queda activo permanentemente para captura inmediata bajo demanda.
 */
inline bool iniciarVideoV4L2() {
  // 1. Inicializar subsistema de video con config MIPI-CSI
  esp_video_init_csi_config_t csiCfg = {};
  csiCfg.sccb_config.init_sccb = false;  // I2C ya inicializado
  csiCfg.sccb_config.i2c_handle = i2cBusHandle;
  csiCfg.sccb_config.freq = 400000;
  csiCfg.reset_pin = -1;  // No conectado (confirmado por BSP)
  csiCfg.pwdn_pin = -1;

  esp_video_init_config_t videoCfg = {};
  videoCfg.csi = &csiCfg;

  esp_err_t err = esp_video_init(&videoCfg);
  if (err != ESP_OK) {
#ifdef DEBUG
    Serial.print("Error: esp_video_init fallo: 0x");
    Serial.println(err, HEX);
#endif
    return false;
  }
#ifdef DEBUG
  Serial.println("esp_video_init OK");
#endif

  // 2. Abrir dispositivo V4L2 MIPI-CSI
  videoFd = open(ESP_VIDEO_MIPI_CSI_DEVICE_NAME, O_RDWR);
  if (videoFd < 0) {
#ifdef DEBUG
    Serial.println("Error: no se pudo abrir " ESP_VIDEO_MIPI_CSI_DEVICE_NAME);
#endif
    return false;
  }

  // 3. Obtener formato por defecto del sensor
  struct v4l2_format fmt = {};
  fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  if (ioctl(videoFd, VIDIOC_G_FMT, &fmt) != 0) {
#ifdef DEBUG
    Serial.println("Error: VIDIOC_G_FMT fallo");
#endif
    close(videoFd);
    videoFd = -1;
    return false;
  }
#ifdef DEBUG
  Serial.print("V4L2 formato nativo: ");
  Serial.print(fmt.fmt.pix.width);
  Serial.print("x");
  Serial.print(fmt.fmt.pix.height);
  Serial.print(" pixfmt=0x");
  Serial.println(fmt.fmt.pix.pixelformat, HEX);
#endif

  // 4. Buscar formato RGB565 entre los soportados (la ISP convierte RAW->RGB)
  struct v4l2_fmtdesc fmtdesc = {};
  fmtdesc.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  bool formatoEncontrado = false;

  while (ioctl(videoFd, VIDIOC_ENUM_FMT, &fmtdesc) == 0) {
#ifdef DEBUG
    Serial.print("  Formato disponible: ");
    Serial.println((char*)fmtdesc.description);
#endif
    if (fmtdesc.pixelformat == V4L2_PIX_FMT_RGB565) {
      formatoEncontrado = true;
    }
    fmtdesc.index++;
  }

  // Configurar RGB565 si esta disponible, sino usar formato nativo
  struct v4l2_format setFmt = {};
  setFmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  setFmt.fmt.pix.width = fmt.fmt.pix.width;    // Usar resolucion nativa del sensor
  setFmt.fmt.pix.height = fmt.fmt.pix.height;
  setFmt.fmt.pix.pixelformat = formatoEncontrado ? V4L2_PIX_FMT_RGB565 : fmt.fmt.pix.pixelformat;

  if (ioctl(videoFd, VIDIOC_S_FMT, &setFmt) != 0) {
#ifdef DEBUG
    Serial.println("Error: VIDIOC_S_FMT fallo");
#endif
    close(videoFd);
    videoFd = -1;
    return false;
  }

  // Guardar resolucion y formato reales
  capturaAncho = setFmt.fmt.pix.width;
  capturaAlto = setFmt.fmt.pix.height;
  capturaPixFmt = setFmt.fmt.pix.pixelformat;
#ifdef DEBUG
  Serial.print("V4L2 formato configurado: ");
  Serial.print(capturaAncho);
  Serial.print("x");
  Serial.print(capturaAlto);
  Serial.print(" pixfmt=0x");
  Serial.print(capturaPixFmt, HEX);
  Serial.print(" (");
  // Decodificar fourcc para log legible
  char fourcc[5] = {
    (char)(capturaPixFmt & 0xFF),
    (char)((capturaPixFmt >> 8) & 0xFF),
    (char)((capturaPixFmt >> 16) & 0xFF),
    (char)((capturaPixFmt >> 24) & 0xFF),
    0
  };
  Serial.print(fourcc);
  Serial.print("), ");
  Serial.print(setFmt.fmt.pix.sizeimage);
  Serial.println(" bytes/frame");
#endif

  // 5. Solicitar buffers MMAP
  struct v4l2_requestbuffers req = {};
  req.count = V4L2_NUM_BUFS;
  req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  req.memory = V4L2_MEMORY_MMAP;
  if (ioctl(videoFd, VIDIOC_REQBUFS, &req) != 0) {
#ifdef DEBUG
    Serial.println("Error: VIDIOC_REQBUFS fallo");
#endif
    close(videoFd);
    videoFd = -1;
    return false;
  }

  // 5. Query, mmap y encolar cada buffer
  for (int i = 0; i < V4L2_NUM_BUFS; i++) {
    struct v4l2_buffer buf = {};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = i;

    if (ioctl(videoFd, VIDIOC_QUERYBUF, &buf) != 0) {
#ifdef DEBUG
      Serial.print("Error: VIDIOC_QUERYBUF[");
      Serial.print(i);
      Serial.println("] fallo");
#endif
      close(videoFd);
      videoFd = -1;
      return false;
    }

    v4l2Buffers[i] = (uint8_t*)mmap(NULL, buf.length,
                                     PROT_READ | PROT_WRITE, MAP_SHARED,
                                     videoFd, buf.m.offset);
    v4l2BufLengths[i] = buf.length;

    if (v4l2Buffers[i] == (uint8_t*)MAP_FAILED) {
      v4l2Buffers[i] = nullptr;  // Limpiar para downstream que checks nullptr
#ifdef DEBUG
      Serial.print("Error: mmap buffer[");
      Serial.print(i);
      Serial.println("] fallo");
#endif
      close(videoFd);
      videoFd = -1;
      return false;
    }

    if (ioctl(videoFd, VIDIOC_QBUF, &buf) != 0) {
#ifdef DEBUG
      Serial.print("Error: VIDIOC_QBUF[");
      Serial.print(i);
      Serial.println("] fallo");
#endif
      close(videoFd);
      videoFd = -1;
      return false;
    }
  }

  // 6. Iniciar streaming
  int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  if (ioctl(videoFd, VIDIOC_STREAMON, &type) != 0) {
#ifdef DEBUG
    Serial.println("Error: VIDIOC_STREAMON fallo");
#endif
    close(videoFd);
    videoFd = -1;
    return false;
  }

  // Iniciar ISP pipeline controller (AE, AWB, AGC, gamma, CCM, sharpen).
  // El pipeline crea una tarea que lee estadisticas ISP en bucle continuo,
  // las pasa a los algoritmos IPA, y aplica los resultados al sensor/ISP.
  {
    static const char *ipa_names[] = {
      "awb.gray", "agc.threshold", "denoising.gf",
      "sharpen.ff", "gamma.lf", "cc.linear"
    };
    esp_video_isp_config_t ispCfg = {};
    ispCfg.cam_dev = ESP_VIDEO_MIPI_CSI_DEVICE_NAME;
    ispCfg.isp_dev = ESP_VIDEO_ISP1_DEVICE_NAME;
    ispCfg.ipa_nums = 6;
    ispCfg.ipa_names = ipa_names;

    esp_err_t ispRet = esp_video_isp_pipeline_init(&ispCfg);
#ifdef DEBUG
    if (ispRet != ESP_OK) {
      Serial.print("Aviso: ISP pipeline init fallo: ");
      Serial.println(ispRet);
    } else {
      Serial.println("ISP pipeline controller iniciado (AE/AWB/AGC/gamma/CCM/sharpen)");
    }
#endif
    // Silenciar NACK esperados: la IPA escribe gain/exposicion al sensor via SCCB
    // mientras el sensor esta en readout, produciendo NACKs esporadicos inofensivos
    esp_log_level_set("i2c.master", ESP_LOG_NONE);
    esp_log_level_set("sccb_i2c", ESP_LOG_NONE);
    esp_log_level_set("esp_video_sensor", ESP_LOG_NONE);
    esp_log_level_set("esp_video", ESP_LOG_NONE);
    esp_log_level_set("ISP", ESP_LOG_NONE);
  }

  // Warmup: ciclar frames para que la IPA converja (AE/AWB necesitan ~20 frames)
  for (int w = 0; w < 20; w++) {
    struct v4l2_buffer wBuf = {};
    wBuf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    wBuf.memory = V4L2_MEMORY_MMAP;
    if (ioctl(videoFd, VIDIOC_DQBUF, &wBuf) != 0) break;
    ioctl(videoFd, VIDIOC_QBUF, &wBuf);
  }

#ifdef DEBUG
  Serial.println("V4L2 streaming iniciado (IPA warmup completado)");
#endif
  return true;
}

/**
 * Inicializa la camara SC2356 del Tab5.
 * Debe llamarse en setup() despues de iniciar la SD card.
 * Si falla cualquier paso, camaraInicializada queda en false y el firmware
 * continua sin camara (per D-03, D-10).
 *
 * Secuencia de inicializacion:
 * 1. Crear mutex para acceso thread-safe a SD
 * 2. Crear directorio /fotos/ en SD si no existe
 * 3. Iniciar reloj 24MHz para sensor via LEDC en GPIO 36
 * 4. Iniciar I2C (reutiliza bus existente de M5Unified si es posible)
 * 4.5. Habilitar sensor via IO expander PI4IOE5V6408 (si es necesario)
 * 5. Iniciar codificador JPEG por hardware
 * 6. Reservar buffer JPEG de salida (DMA-alineado)
 * 7. Iniciar pipeline V4L2 (esp_video_init + open + mmap + streaming)
 */
inline void inicializarCamara() {
#ifdef DEBUG
  Serial.println("Inicializando camara SC2356...");
#endif

  // 1. Crear mutex SD para acceso thread-safe entre tarea de foto y loop principal
  sdMutex = xSemaphoreCreateMutex();
  if (sdMutex == nullptr) {
#ifdef DEBUG
    Serial.println("Error: No se pudo crear mutex SD");
#endif
    return;
  }

  // Crear mutex de camara para proteger pipeline V4L2+JPEG contra concurrencia (per D-06)
  cameraMutex = xSemaphoreCreateMutex();
  if (cameraMutex == nullptr) {
#ifdef DEBUG
    Serial.println("Error: No se pudo crear mutex de camara");
#endif
    return;
  }

  // 2. Crear directorio /fotos/ si no existe (per pitfall 4)
  if (!SD.exists("/fotos")) {
    if (!SD.mkdir("/fotos")) {
#ifdef DEBUG
      Serial.println("Error: No se pudo crear directorio /fotos/");
#endif
      // No es fatal: se intentara crear al guardar la primera foto
    } else {
#ifdef DEBUG
      Serial.println("Directorio /fotos/ creado en SD");
#endif
    }
  }

  // 3. Iniciar reloj de camara 24MHz
  if (!iniciarRelojCamara()) {
#ifdef DEBUG
    Serial.println("Error: No se pudo iniciar reloj de camara");
#endif
    return;
  }

  // 4. Iniciar I2C (reutiliza bus existente de M5Unified si es posible)
  if (!iniciarI2C()) {
#ifdef DEBUG
    Serial.println("Error: No se pudo iniciar bus I2C para camara");
#endif
    return;
  }

  // 4.5. Habilitar sensor via IO expander (si es necesario)
  // No es fatal si falla: el sensor puede estar habilitado por defecto
  habilitarCamaraIOExpander();

  // 5. Iniciar codificador JPEG por hardware (antes de reservar buffers,
  //    porque jpeg_alloc_encoder_mem necesita el driver JPEG inicializado)
  if (!iniciarJpegEncoder()) {
#ifdef DEBUG
    Serial.println("Error: No se pudo iniciar codificador JPEG HW");
#endif
    return;
  }

  // 6. Reservar buffer JPEG de salida con alineacion DMA requerida
  jpeg_encode_memory_alloc_cfg_t jpegMemCfg = {
    .buffer_direction = JPEG_ENC_ALLOC_OUTPUT_BUFFER,
  };
  size_t jpegAllocSize = 0;
  jpegBuffer = (uint8_t*)jpeg_alloc_encoder_mem(JPEG_OUT_SIZE, &jpegMemCfg, &jpegAllocSize);
  if (jpegBuffer == nullptr) {
#ifdef DEBUG
    Serial.print("Error: jpeg_alloc_encoder_mem fallo para buffer JPEG (");
    Serial.print(JPEG_OUT_SIZE);
    Serial.println(" bytes)");
#endif
    return;
  }
#ifdef DEBUG
  Serial.print("Buffer JPEG reservado: ");
  Serial.print(jpegAllocSize);
  Serial.println(" bytes (DMA alineado)");
#endif

  // 7. Inicializar pipeline V4L2 (esp_video_init + open + mmap + streaming)
  // Los buffers de frame los proporciona el driver via mmap (v4l2Buffers[])
  if (!iniciarVideoV4L2()) {
#ifdef DEBUG
    Serial.println("Error: No se pudo iniciar pipeline V4L2");
#endif
    free(jpegBuffer);
    jpegBuffer = nullptr;
    return;
  }

  camaraInicializada = true;

#ifdef DEBUG
  Serial.println("Camara inicializada correctamente");
#endif
}

/**
 * Captura una foto desde la camara SC2356, la codifica a JPEG y la guarda en SD.
 * Debe llamarse al recibir un evento RFID (per D-04: capturar inmediatamente).
 * Si la camara no esta inicializada, retorna inmediatamente sin error.
 * Si la escritura SD falla, marca errorSD=true para indicador visual (D-10).
 *
 * Flujo:
 * 1. Verificar que la camara esta inicializada
 * 2. Capturar frame del sensor MIPI-CSI a buffer PSRAM
 * 3. Codificar frame a JPEG con HW encoder (quality=70)
 * 4. Tomar mutex SD, generar nombre con datestamp, escribir archivo
 * 5. Liberar mutex SD
 *
 * NOTA: Para operacion no bloqueante (D-05), el caller deberia ejecutar
 * esta funcion en una tarea FreeRTOS separada:
 *   xTaskCreate(tareaCapturarFoto, "foto", 8192, NULL, 1, NULL);
 */
inline void capturarYGuardarFoto() {
  // Si la camara no se inicializo, salir silenciosamente
  if (!camaraInicializada || videoFd < 0) return;

  // Tomar mutex de camara para proteger pipeline V4L2+JPEG contra concurrencia (per D-06)
  if (xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(5000)) != pdTRUE) {
#ifdef DEBUG
    Serial.println("Aviso: Otra captura en curso, descartando esta");
#endif
    return;
  }

  // 1. Drenar buffers viejos y ciclar frames frescos para que la IPA
  //    re-ajuste exposicion (los buffers pueden tener frames antiguos
  //    capturados la ultima vez que hubo buffers libres).
  // Drenar solo los buffers pre-encolados para obtener frame fresco
  // La IPA ya convergio durante streaming continuo (per D-07)
  static constexpr int WARMUP_FRAMES = 2;
  struct v4l2_buffer v4l2Buf = {};
  for (int i = 0; i < WARMUP_FRAMES; i++) {
    memset(&v4l2Buf, 0, sizeof(v4l2Buf));
    v4l2Buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    v4l2Buf.memory = V4L2_MEMORY_MMAP;
    if (ioctl(videoFd, VIDIOC_DQBUF, &v4l2Buf) != 0) {
#ifdef DEBUG
      Serial.println("Error: VIDIOC_DQBUF fallo");
#endif
      xSemaphoreGive(cameraMutex);
      return;
    }
    if (i < WARMUP_FRAMES - 1) {
      ioctl(videoFd, VIDIOC_QBUF, &v4l2Buf);
    }
  }

  uint8_t* frameData = v4l2Buffers[v4l2Buf.index];
  size_t frameSize = v4l2Buf.bytesused;

#ifdef DEBUG
  Serial.print("Frame capturado: buf[");
  Serial.print(v4l2Buf.index);
  Serial.print("] bytesused=");
  Serial.print(frameSize);
  Serial.print(" buflen=");
  Serial.print(v4l2BufLengths[v4l2Buf.index]);
  // Muestrear bytes del frame para diagnostico (inicio y medio)
  Serial.print(" inicio=");
  for (int d = 0; d < 8 && d < (int)frameSize; d++) {
    if (frameData[d] < 0x10) Serial.print("0");
    Serial.print(frameData[d], HEX);
    Serial.print(" ");
  }
  size_t mid = frameSize / 2;
  Serial.print(" medio=");
  for (int d = 0; d < 8 && mid + d < frameSize; d++) {
    if (frameData[mid + d] < 0x10) Serial.print("0");
    Serial.print(frameData[mid + d], HEX);
    Serial.print(" ");
  }
  Serial.println();
#endif

  // 2. Codificar frame a JPEG usando HW encoder del ESP32-P4
  jpeg_encode_cfg_t encodeCfg = {};
  encodeCfg.height = capturaAlto;
  encodeCfg.width = capturaAncho;
  encodeCfg.src_type = JPEG_ENCODE_IN_FORMAT_RGB565;
  encodeCfg.sub_sample = JPEG_DOWN_SAMPLING_YUV422;
  encodeCfg.image_quality = JPEG_QUALITY;
  if (capturaPixFmt == V4L2_PIX_FMT_RGB24) {
    encodeCfg.src_type = JPEG_ENCODE_IN_FORMAT_RGB888;
  } else if (capturaPixFmt == V4L2_PIX_FMT_YUV422P || capturaPixFmt == V4L2_PIX_FMT_YUYV) {
    encodeCfg.src_type = JPEG_ENCODE_IN_FORMAT_YUV422;
  }

  uint32_t jpegSize = 0;
  esp_err_t err = jpeg_encoder_process(jpegEncoder, &encodeCfg,
                                        frameData, frameSize,
                                        jpegBuffer, JPEG_OUT_SIZE,
                                        &jpegSize);

  // 3. Devolver buffer al pipeline V4L2 (QBUF) antes de escribir SD
  if (ioctl(videoFd, VIDIOC_QBUF, &v4l2Buf) != 0) {
#ifdef DEBUG
    Serial.println("Error: VIDIOC_QBUF re-enqueue fallo");
#endif
  }

  if (err != ESP_OK) {
#ifdef DEBUG
    Serial.print("Error: codificacion JPEG fallo: 0x");
    Serial.println(err, HEX);
#endif
    xSemaphoreGive(cameraMutex);
    return;
  }

  // Liberar mutex de camara: pipeline V4L2+JPEG completo, SD tiene su propio mutex
  xSemaphoreGive(cameraMutex);

#ifdef DEBUG
  Serial.print("JPEG codificado: ");
  Serial.print(jpegSize);
  Serial.println(" bytes");
#endif

  // Tomar mutex SD antes de escribir (thread-safe)
  if (xSemaphoreTake(sdMutex, pdMS_TO_TICKS(2000)) != pdTRUE) {
#ifdef DEBUG
    Serial.println("Error: Timeout esperando mutex SD para guardar foto");
#endif
    return;
  }

  // Generar nombre de archivo con datestamp (con anti-colision)
  char ruta[64];
  generarNombreFoto(ruta, sizeof(ruta));

  // Escribir archivo JPEG en SD
  File f = SD.open(ruta, FILE_WRITE);
  if (!f) {
#ifdef DEBUG
    Serial.print("Error: No se pudo crear archivo ");
    Serial.println(ruta);
#endif
    errorSD = true;
    xSemaphoreGive(sdMutex);
    return;
  }

  size_t escritos = f.write(jpegBuffer, jpegSize);
  f.close();
  xSemaphoreGive(sdMutex);

  if (escritos != jpegSize) {
#ifdef DEBUG
    Serial.print("Error: Escritura incompleta en ");
    Serial.print(ruta);
    Serial.print(" (");
    Serial.print(escritos);
    Serial.print("/");
    Serial.print(jpegSize);
    Serial.println(" bytes)");
#endif
    errorSD = true;
    return;
  }

  errorSD = false;

#ifdef DEBUG
  Serial.print("Foto guardada: ");
  Serial.print(ruta);
  Serial.print(" (");
  Serial.print(jpegSize);
  Serial.println(" bytes)");
#endif
}

/**
 * Retorna si hay error de escritura en SD.
 * El display_manager puede consultar esta funcion para mostrar un indicador
 * visual de error de SD (per D-10).
 * @return true si la ultima escritura de foto fallo
 */
inline bool hayErrorSD() {
  return errorSD;
}

/**
 * Retorna si la camara esta inicializada y lista para capturar.
 * Util para que main.cpp sepa si debe intentar capturar fotos.
 * @return true si la camara se inicializo correctamente
 */
inline bool camaraLista() {
  return camaraInicializada;
}

#endif // CAMERA_ENABLED

#endif // CAMERA_MANAGER_H
