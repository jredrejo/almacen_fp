# almacen_fp

Esta aplicación está pensada para usarla para gestionar el almacén de un instituto de FP

## Créditos
Realizada en el IES Santiago Apóstol de Almendralejo



# Desarrollo
# Principales herramientas (RFID + Django + HTMX + Tailwind)

Características
- Google Workspace login (`santiagoapostol.net`) via `django-allauth`.
- Los profesores pertenecen al grupo de Django **ProfesoresFP**.
- La ficha de producto captura el campo RFID EPC
- Multi-taller mediante el modelo **Aula**  (cada producto pertenece a un aula).
- Inventario con edición y borrado en línea mediante HTMX
- Página de préstamos (un vistazo rápido a quién tiene qué).
- Registro de localización (**Ubicacion**) para saber en qué almacén está cada producto
- CSS mediante bootstrap. HTMX para un UX dinámico. No se usa ningún framework de JavaScript.

## Puesta en marcha rápida (con uv)
```bash
# 1) Crea el  env & instala dependencias
uv sync

# 2) Configura env
cp .env.example .env
# rellena GOOGLE client id/secret, SECRET_KEY, etc.
# Authorized redirect URI:
http://localhost:8000/accounts/google/login/callback/

Login mediante "Sign in with Google" (restringido a santiagoapostol.net).

# 3) Migraciones & crea superuser
uv run python manage.py migrate
uv run python manage.py createsuperuser

# 4) Crea el grupo de profesores
uv run python manage.py shell -c "from django.contrib.auth.models import Group; Group.objects.get_or_create(name='ProfesoresFP')"

# 5) Arrancar el servidor
uv run python manage.py runserver
```


## Antes de arrancar el servidor en producción recuerda:
- cambiar DEBUG=1 por DEBUG=0 en .env
- ejecutar `python manage.py collectstatic`


### El formato de los mensajes MQTT será:
```json
{
  "epc": "3034257BF7194E4000000001",
  "aula_id": "3",
  "timestamp": "2025-10-07T10:30:00"
}
```

## para la gestión de los mensajes que llegan mediante MQTT
- Instalar redis `sudo apt install redis-server`
- Instalar y configurar mosquitto `sudo apt install mosquitto`
- Instalar y configurar servicio mqtt-listener:
 - /etc/systemd/system/mqtt-listener.service
 - sudo systemctl daemon-reload
 - sudo systemctl enable mqtt-listener
 - sudo systemctl start mqtt-listener
 - sudo systemctl status mqtt-listener

## verificar funcionamiento:
```bash
# Ver logs del listener
sudo journalctl -u mqtt-listener -f

# O con supervisor
sudo tail -f /var/log/mqtt-listener.log
# Publicar un EPC de prueba
mosquitto_pub -h localhost -t "rfid/3/epc" -m '{"epc": "TEST123456", "aula_id": "3"}'
```
