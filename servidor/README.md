# Despliegue en Producción

Configuraciones para desplegar Almacén FP en un servidor con Nginx + uWSGI.

La ruta de instalación asumida en todos los archivos es `/opt/almacen_fp`.

## Archivos incluidos

| Archivo | Descripción |
|---|---|
| `almacen.conf` | Configuración Nginx (HTTP→HTTPS redirect + SSL + proxy uWSGI) |
| `almacen_uwsgi.ini` | Configuración uWSGI (4 procesos, socket en `/tmp/almacen.sock`) |
| `almacen-uwsgi.service` | Servicio systemd para uWSGI |
| `mqtt-rfid.service` | Servicio systemd para el listener MQTT (`manage.py mqtt_listener`) |
| `setup_mqtt_logging.sh` | Script auxiliar para configurar logging MQTT |

## Instalación

### 1. Dependencias del sistema

```bash
sudo apt install -y uwsgi uwsgi-plugin-python3 nginx redis-server mosquitto mosquitto-clients
```

### 2. Clonar y preparar el proyecto

```bash
sudo mkdir -p /opt/almacen_fp
sudo chown www-data:www-data /opt/almacen_fp
# Clonar el repo en /opt/almacen_fp
cd /opt/almacen_fp
uv sync
cp .env.example .env   # rellenar SECRET_KEY, GOOGLE client id/secret, etc.
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
```

### 3. uWSGI

```bash
sudo cp servidor/almacen_uwsgi.ini /etc/uwsgi/apps-available/almacen_uwsgi.ini
sudo cp servidor/almacen-uwsgi.service /etc/systemd/system/almacen-uwsgi.service
sudo systemctl daemon-reload
sudo systemctl enable --now almacen-uwsgi
```

### 4. Nginx

```bash
sudo cp servidor/almacen.conf /etc/nginx/sites-available/almacen_fp
sudo ln -sf /etc/nginx/sites-available/almacen_fp /etc/nginx/sites-enabled/almacen_fp
sudo nginx -t && sudo systemctl reload nginx
```

### 5. Certificado SSL (Let's Encrypt)

```bash
sudo certbot certonly --manual --preferred-challenges=dns -d fp.santiagoapostol.net
```

El certificado se espera en `/etc/letsencrypt/live/fp.santiagoapostol.net/`.

### 6. Servicio MQTT listener

```bash
sudo cp servidor/mqtt-rfid.service /etc/systemd/system/mqtt-rfid.service
sudo systemctl daemon-reload
sudo systemctl enable --now mqtt-rfid.service
```

## Verificación

```bash
sudo systemctl status almacen-uwsgi mqtt-rfid.service
sudo journalctl -u almacen-uwsgi -f
sudo journalctl -u mqtt-rfid -f
```
