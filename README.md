# Almacén FP

Sistema de gestión de inventario mediante RFID para talleres de Formación Profesional utilizando Django, HTMX y hardware ESP32.

## 📋 Descripción General

Esta aplicación está pensada para usarla para gestionar el almacén de un instituto de FP mediante tecnología RFID para el tracking de productos y herramientas.

**Créditos**: Realizada en el IES Santiago Apóstol de Almendralejo

## 🏗️ Arquitectura Tecnológica

### Stack Principal

- **Django 5.1+** - Framework web Python con base de datos SQLite
- **Python 3.11+** - Lenguaje de programación principal
- **HTMX + Bootstrap** - Frontend dinámico sin frameworks JavaScript
- **Redis** - Capa de caché para datos RFID EPC
- **MQTT (Mosquitto)** - Mensajería en tiempo real desde hardware RFID
- **ESP32 + RFID R200** - Hardware para lectura de etiquetas RFID

## 🎯 Funcionalidades Principales

1. **Autenticación Google Workspace** - Login restringido al dominio santiagoapostol.net
2. **Gestión de Inventario RFID** - Seguimiento de productos mediante códigos EPC con lectores ESP32
3. **Soporte Multi-Taller** - Inventario separado por aula/taller
4. **Control de Acceso por Aula** - Restringe el acceso de usuarios a aulas específicas (el personal omite restricciones)
5. **Integración RFID en Tiempo Real** - Mensajes MQTT para detección de etiquetas en vivo
6. **Sistema de Seguimiento de Préstamos** - Check-in/check-out de productos con asignación de usuario
7. **Interfaz HTMX** - Interfaz dinámica sin recargas de página

## 📁 Estructura del Proyecto

```
[root]/
  📱 manage.py              # CLI de gestión Django
  🧩 almacen/               # App Django principal (gestión de inventario)
  📄 core/                  # Configuración del proyecto Django
  🔧 hardware/              # Código Arduino ESP32 para lectores RFID y planos para impresi
  🛠️ templates/             # Plantillas Django con parciales HTMX
  🎨 static/                # CSS, JS, imágenes (Bootstrap)
  🧪 tests/                 # Suite de pruebas pytest para control de acceso y funcionalidad principal
  📊 requirements/          # Dependencias Python
  🌐 servidor/              # Configuraciones de despliegue en producción
```

## 🚀 Puesta en Marcha Rápida (con uv)

### Requisitos Previos

- Python 3.11+
- uv (gestor de paquetes Python)
- Redis Server
- Mosquitto MQTT Broker

### Instalación y Configuración

```bash
# 1) Crear entorno virtual e instalar dependencias
uv sync

# 2) Configurar variables de entorno
cp .env.example .env
# Rellenar GOOGLE client id/secret, SECRET_KEY, etc.
# URI de redirección autorizada:
http://localhost:8000/accounts/google/login/callback/

# Login mediante "Sign in with Google" (restringido a santiagoapostol.net).

# 3) Migraciones y crear superusuario
uv run python manage.py migrate
uv run python manage.py createsuperuser

# 4) Crear el grupo de profesores
uv run python manage.py shell -c "from django.contrib.auth.models import Group; Group.objects.get_or_create(name='ProfesoresFP')"

# 5) Iniciar el servidor de desarrollo
uv run python manage.py runserver
```

### Acceso a la Aplicación

- **Servidor de desarrollo**: http://127.0.0.1:8000
- **Panel de administración**: http://127.0.0.1:8000/admin
- **Broker MQTT**: localhost:1883
- **Caché Redis**: localhost:6379

## Compilación de la aplicación del esp32 (con Arduino IDE)

1. Abre con el ide de Arduino el archivo `almacen.ino` de la carpeta hardware/almacen.
2. En el menú Herramientas -> Placas -> Gestor de Placas busca e instala "esp32 de Espressif Systems"
3. Instala las librerías necesarias con la opción "Gestionar Bibliotecas". Las librerías están listadas en la sección siguiente.
4. Seleciona la tarjeta "ESP32 Dev Module" en el menú Herramientas.
5. Compila, exportálo usando el menú Sketch -> Exportar binario compilado
6. Localiza la ip del esp32 y ve a http://ip/update y sube el archivo almacen.ino.bin de la carpeta hardware/almacen/build

### Librerías necesarias

* [Timezone](https://github.com/JChristensen/Timezone) (v1.2.6)
* [NTPClient](https://github.com/arduino-libraries/NTPClient) (v3.2.1
* [PubSubClient](https://github.com/knolleary/pubsubclient) (v2.8)
* [AsyncTCP](https://github.com/ESP32Async/AsyncTCP) (v3.4.10)
* [ESPAsyncWebServer](https://github.com/ESP32Async/ESPAsyncWebServer) (v3.10.3)
* [ElegantOTA](https://github.com/ayushsharma82/ElegantOTA) (v3.1.7)

**IMPORTANTE**: ElegantOTA require un cambio en su código fuente para compilar. En ~/Arduino/libraries/ElegantOTA/src/ElegantOTA.h:
```diff
26  #ifndef ELEGANTOTA_USE_ASYNC_WEBSERVER
27 -  #define ELEGANTOTA_USE_ASYNC_WEBSERVER 0
27 +  #define ELEGANTOTA_USE_ASYNC_WEBSERVER 1
```

## Compilación del firmware del M5Stack Tab5 (con PlatformIO)

El firmware de la pantalla Tab5 se encuentra en `hardware/pantalla/` y usa PlatformIO con la plataforma pioarduino para el ESP32-P4.

### Requisitos previos

- [PlatformIO CLI](https://platformio.org/install/cli) instalado (`pipx install platformio`)
- Cable USB-C conectado al Tab5
- **Nota:** Si usas Python 3.12+ y ves errores de `click`/`esptool`, ejecuta:
  ```bash
  # Instalar version compatible de click en el entorno de PlatformIO
  $(dirname $(which pio))/../lib/python*/site-packages/../../../bin/python -m pip install "click<8.2"
  ```

### Compilar el firmware

```bash
cd hardware/pantalla
pio run -e tab5
```

La primera compilación descarga las dependencias automáticamente (M5Unified, M5GFX, PubSubClient, ArduinoJson, NTPClient, Timezone). Compilaciones posteriores son más rápidas.

### Subir el firmware al Tab5

1. Conecta el Tab5 por USB-C al ordenador
2. Comprueba qeu hardware/pantalla/includes/config.h contiene tus credenciales e ips. Ejecuta:
   ```bash
   cd hardware/pantalla
   pio run --target clean
   pio run -e tab5 -t upload
   ```
3. PlatformIO detecta el puerto automáticamente. Si hay varios dispositivos, especifica el puerto:
   ```bash
   pio run -e tab5 -t upload --upload-port /dev/ttyACM0
   ```

### Subir archivos a la tarjeta SD

El directorio `hardware/pantalla/data/` contiene los archivos que deben copiarse a la tarjeta SD del Tab5:

- `splash.png` — Imagen de arranque
- `splash_small.png` — Imagen para animación idle
- `foto.wav` — Sonido de obturador de cámara

Copia estos archivos manualmente a la raíz de la tarjeta microSD del Tab5.

### Monitor serie

Para ver los logs de depuración del Tab5:

```bash
cd hardware/pantalla
pio device monitor
```

### Configuración WiFi y MQTT

Antes de compilar, edita `hardware/pantalla/include/config.h` con los datos de tu red:

- `WIFI_SSID` y `WIFI_PASSWORD` — Credenciales WiFi
- `MQTT_SERVER` — IP del broker MQTT
- `API_BASE_URL` — URL base de la API Django (ej: `http://192.168.1.100:8000`)
- `AULA_ID` — ID del aula asignada al Tab5

## 🔧 Configuración de Servicios Externos

### Redis (Caché para EPC RFID)

```bash
# Instalar Redis
sudo apt install redis-server
# Iniciar servicio
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### Mosquitto (MQTT Broker)

```bash
# Instalar Mosquitto
sudo apt install mosquitto mosquitto-clients
# Iniciar servicio
sudo systemctl start mosquitto
sudo systemctl enable mosquitto
```

### Servicio MQTT Listener

Crear servicio systemd para procesar mensajes MQTT:

```bash
# Crear archivo de servicio
sudo nano /etc/systemd/system/mqtt-listener.service
```

Contenido del servicio:

```ini
[Unit]
Description=MQTT Listener for RFID EPC data
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/src/almacen_fp
ExecStart=/opt/src/almacen_fp/.venv/bin/python /opt/src/almacen_fp/hardware/mqtt_listener.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Recargar y activar servicio
sudo systemctl daemon-reload
sudo systemctl enable mqtt-listener
sudo systemctl start mqtt-listener
sudo systemctl status mqtt-listener
```

## 📡 Formato de Mensajes MQTT

Los mensajes MQTT siguen este formato JSON:

```json
{
  "epc": "3034257BF7194E4000000001",
  "aula_id": "3",
  "timestamp": "2025-10-07T10:30:00"
}
```

**Estructura de topics MQTT**:

- Topic: `rfid/{aula_id}/epc`
- Los mensajes EPC se cachean en Redis durante 30 segundos

## 🔐 Control de Acceso por Aula

### Implementación

- **Modelo Persona**: incluye campo `aulas_access` (ManyToManyField) para restringir acceso a aulas
- **Restricciones**: Usuarios no staff solo pueden acceder a productos de aulas asignadas
- **Privilegios Staff**: Usuarios con `is_staff=True` omiten todas las restricciones de aula
- **Acceso por Defecto**: Usuarios sin aulas asignadas tienen acceso completo (compatibilidad hacia atrás)
- **Gestión Administrativa**: Interfaz PersonaAdmin para gestionar permisos de acceso a aulas

### Configuración

```bash
# Asignar aulas a usuarios mediante Django Admin
# 1. Ir a http://127.0.0.1:8000/admin
# 2. Navegar a Persona → Editar usuario
# 3. Asignar "Aulas accesibles" específicas
```

## ✅ Verificación y Testing

### Comandos de Verificación

```bash
# Verificación completa del proyecto
uv run python manage.py check && uv run mypy almacen/ && uv run black --check .

# Ejecutar suite de pruebas
uv run pytest tests/

# Ver logs del listener MQTT
sudo journalctl -u mqtt-listener -f

# Publicar EPC de prueba
mosquitto_pub -h localhost -u usuario -P password -t "rfid/pantalla/1" -m '{"epc": "TEST123456", "aula_id": "1"}'

```

### Estrategia de Testing

- **Control de Acceso**: Suite pytest completa en `tests/test_access_control_simple.py`
- Tests Django para modelos y vistas con pytest
- Validación de formato de mensajes MQTT
- Tests de procesamiento RFID EPC
- Tests de integración para endpoints HTMX
- Cumplimiento del control de acceso en todas las vistas y operaciones

## 🏭 Despliegue en Producción

### Configuración Previa al Despliegue

```bash
# Cambiar modo debug
sed -i 's/DEBUG=1/DEBUG=0/' .env

# Recopilar archivos estáticos
uv run python manage.py collectstatic --noinput

# Verificar configuración
uv run python manage.py check --deploy
```

### Consideraciones de Seguridad

- Validar todas las entradas EPC RFID
- **Control de Acceso**: Aplicar permisos a nivel de vistas para usuarios no staff
- Integración segura Google OAuth
- Usar HTTPS en producción
- Sanitizar todas las entradas de usuario en plantillas Django
- Restringir topics MQTT con ACLs
- **Omisión de Restricciones**: Usuarios staff (`is_staff=True`) omiten todas las restricciones de aula

### Autenticación sin Google Workspace

Para configurar el sistema con autenticación estándar de Django en lugar de Google Workspace OAuth, sigue estos pasos:

#### 1. Configurar settings.py

```python

# Configurar autenticación estándar de Django
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
```

#### 2. Modificar los templates de autenticación
Modifica el archivo  `templates/account/login.html`:

Reemplaza la sección:
```html
                    {% get_providers as providers %}
                    {% if providers %}
                        {% for p in providers %}
                            {% if p.id == 'google' %}
                                <p class="text-muted">
                                    Usa tu cuenta de correo electrónico de
                                    <strong>santiagoapostol.net</strong>.
                                </p>
                                <a
                                    class="btn btn-outline-dark w-100"
                                    href="{% provider_login_url 'google' %}"
                                    hx-boost="false"
                                    data-turbo="false"
                                >
                                    <img
                                        alt=""
                                        src="{% static 'img/google.svg' %}"
                                        width="20"
                                        class="me-2"
                                    />
                                    Entrar con el correo del instituto
                                </a>
                            {% endif %}
                        {% endfor %}
                    {% endif %}

```


por:
```html
           <form method="post" class="login-form">
                        {% csrf_token %}


                        <div class="mb-3">
                            <label class="form-label" for="{{ form.email.id_for_label }}">
                                <i class="fas fa-user me-1"></i>
                                Para usuarios que no tengan cuenta del IES Santiago Apóstol:
                            </label>
                            <div class="input-with-icon">
                                <i class="fas fa-user input-icon"></i>
                                <input
                                    type="email"
                                    name="{{ form.login.name }}"
                                    class="form-control ps-5"
                                    id="{{ form.login.id_for_label }}"
                                    placeholder="Correo electrónico"
                                    required
                                    autofocus
                                >
                            </div>
                            {% if form.username.errors %}
                                <div class="invalid-feedback d-block">
                                    {{ form.username.errors.0 }}
                                </div>
                            {% endif %}
                        </div>

                        <div class="mb-4">
                            <label class="form-label" for="{{ form.password.id_for_label }}">
                                <i class="fas fa-lock me-1"></i>
                                Contraseña
                            </label>
                            <div class="input-with-icon">
                                <i class="fas fa-lock input-icon"></i>
                                <input
                                    type="password"
                                    name="{{ form.password.name }}"
                                    class="form-control ps-5"
                                    id="{{ form.password.id_for_label }}"
                                    placeholder="Ingresa tu contraseña"
                                    required
                                >
                            </div>
                            {% if form.password.errors %}
                                <div class="invalid-feedback d-block">
                                    {{ form.password.errors.0 }}
                                </div>
                            {% endif %}
                        </div>

                        <div class="d-grid">
                            <button type="submit" class="btn btn-primary btn-login">
                                <i class="fas fa-sign-in-alt me-2"></i>
                                Iniciar Sesión
                            </button>
                        </div>

                        {% if next %}
                            <input type="hidden" name="next" value="{{ next }}">
                        {% endif %}
                    </form>




                <!-- Footer Links -->
                    <div class="login-footer">
                        <a href="{% url 'account_reset_password' %}" class="text-decoration-none">
                            <i class="fas fa-question-circle me-1"></i>
                            ¿Olvidaste tu contraseña?
                        </a>
                    </div>
                </div>

```
#### 3. Probar la configuración

1. Inicia el servidor de desarrollo
2. Accede a `http://127.0.0.1:8000/accounts/login/`
3. Inicia sesión con las credenciales de un usuario creado
4. Verifica que el acceso al sistema funciona correctamente

## 🛠️ Comandos de Desarrollo Adicionales

```bash
# Formateo de código
uv run black .

# Verificación de tipos
uv run mypy almacen/

# Crear migraciones
uv run python manage.py makemigrations

# Aplicar migraciones
uv run python manage.py migrate

# Shell de Django
uv run python manage.py shell

# Recopilar estáticos
uv run python manage.py collectstatic


# Creación del manual en pdf
sudo apt install texlive-fonts-recommended lmodern
pandoc "Manual de Usuario.md" -o "Manual de Usuario.pdf" --pdf-engine=xelatex --toc


```

## 📚 Patrones de Código

### Vista Django con HTMX y RFID EPC

```python
@login_required
def get_latest_epc(request):
    """Endpoint HTMX que devuelve el último RFID EPC desde caché"""
    current_aula = get_current_aula(request)
    if not current_aula:
        return HttpResponse(status=204)

    cache_key = CACHE_KEY_FORMAT.format(current_aula.pk)
    data = epc_cache.get(cache_key)

    if data and data.get("epc") and data.get("leido_en"):
        time_limit = timezone.now() - timedelta(seconds=30)
        if data["leido_en"] >= time_limit:
            return render(request, "almacen/_epc_input.partial.html", {
                "latest_epc": data["epc"],
                "latest_time": data["leido_en"]
            })

    return HttpResponse(status=204)
```

### Patrón de Control de Acceso por Aula

```python
@login_required
def inventory(request):
    """Vista principal de inventario con control de acceso."""
    qs = Producto.objects.all()
    current_aula = get_current_aula(request)

    # Aplicar control de acceso
    if request.user.is_authenticated:
        try:
            persona = request.user.persona
            if not persona.user.is_staff:
                # Para usuarios no staff, filtrar por aulas accesibles
                accessible_aulas = persona.get_aulas_access()
                if current_aula:
                    # Filtrar por aula actual si usuario tiene acceso
                    if persona.has_aula_access(current_aula):
                        qs = qs.filter(aula=current_aula)
                    else:
                        qs = qs.none()
                else:
                    # Mostrar todos los productos de aulas accesibles
                    qs = qs.filter(aula__in=accessible_aulas)
        except Persona.DoesNotExist:
            qs = qs.none()

    return render(request, "almacen/inventory.html", {"productos": qs})
```

## 🌟 Características Técnicas Destacadas

### Integración RFID EPC

- Códigos EPC cacheados en Redis con TTL de 30 segundos
- Estructura de topics MQTT: `rfid/{aula_id}/epc`
- Hardware ESP32 envía JSON: `{"epc": "...", "aula_id": "3", "timestamp": "..."}`
- Endpoints HTMX proporcionan actualizaciones EPC en tiempo real a formularios

### Arquitectura Multi-Taller

- Cada producto pertenece a un `Aula` (taller/clase)
- Usuarios tienen aula preferida mediante `Persona.last_aula`
- Aula actual rastreada en sesión y preferencias de usuario
- Filtrado de inventario por aula actual
