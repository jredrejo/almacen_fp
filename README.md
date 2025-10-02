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
- CSS meidante `django-tailwind`. HTMX para un UX dinámico. No se usa ningún framework de JavaScript.

## Puesta en marcha rápida (con uv)
```bash
# 1) Crea el  env & instala dependencias
uv sync

# 2) Configura env
cp .env.example .env
# set GOOGLE client id/secret, SECRET_KEY, etc.

# 3) Migraciones & crea superuser
uv run python manage.py migrate
uv run python manage.py createsuperuser

# 4) Crea el grupo de profesores
uv run python manage.py shell -c "from django.contrib.auth.models import Group; Group.objects.get_or_create(name='ProfesoresFP')"

# 5) Compilación de Tailwind  (la primera vez y si se cambian los templates)
# Optción A: usando los comandos de django-tailwind
# (Si prefiere el  CLI, puede ejecutar `npx tailwindcss -i theme/static_src/input.css -o static/css/tailwind.css --watch`)
mkdir -p static/css
npx tailwindcss -i theme/static_src/input.css -o static/css/tailwind.css --minify

# 6) Arrancar el servidor
uv run python manage.py runserver
