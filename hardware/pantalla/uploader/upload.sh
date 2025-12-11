#!/usr/bin/env bash
set -e

DEVICE_PORT=${1:-/dev/ttyACM0}
ROOT_DIR="$(dirname "$(realpath "$0")")/.."
CHECKSUM_DB="$ROOT_DIR/uploader/checksum_db.txt"
EXCLUDE_LIST="$ROOT_DIR/uploader/exclude.lst"

echo "🔌 Using device port: $DEVICE_PORT"
echo "📁 Project root: $ROOT_DIR"
echo "📄 Excluding patterns in: $EXCLUDE_LIST"

mkdir -p "$(dirname "$CHECKSUM_DB")"
touch "$CHECKSUM_DB"

# Function: calculate checksum
calc_checksum() {
    sha256sum "$1" | awk '{print $1}'
}

# Function: check if path matches exclusion patterns
matches_pattern() {
    local file="$1"
    while IFS= read -r pattern; do
        [[ "$pattern" == "" ]] && continue
        # Patrón con glob: usar extglob match
        if [[ "$pattern" == *"*"* ]]; then
            [[ "$file" == $pattern ]] && return 0
        else
            # Patrón literal: buscar como substring
            [[ "$file" == *"$pattern"* ]] && return 0
        fi
    done < "$EXCLUDE_LIST"
    return 1
}

echo "🔍 Scanning for changes…"

# Arrays para archivos a subir
declare -a FILES_TO_UPLOAD=()
declare -a REMOTE_PATHS=()
declare -a CHECKSUMS=()
declare -a DIRS_TO_CREATE=()

# Recopilar archivos que necesitan subirse
while IFS= read -r -d '' file; do
    rel="${file#$ROOT_DIR/}"

    # Exclusion checks
    if matches_pattern "$rel"; then
        echo "⏭️  Skipping excluded: $rel"
        continue
    fi

    checksum=$(calc_checksum "$file")
    oldsum=$(grep "^$rel:" "$CHECKSUM_DB" 2>/dev/null | cut -d':' -f2 || true)

    if [[ "$checksum" == "$oldsum" ]]; then
        echo "✓ Unchanged: $rel"
    else
        echo "📦 Pending: $rel"
        FILES_TO_UPLOAD+=("$file")
        REMOTE_PATHS+=("$rel")
        CHECKSUMS+=("$checksum")

        # Registrar directorio si no es el raíz
        remote_dir=$(dirname "$rel")
        if [[ "$remote_dir" != "." ]]; then
            # Añadir solo si no está ya en la lista
            if [[ ! " ${DIRS_TO_CREATE[*]} " =~ " ${remote_dir} " ]]; then
                DIRS_TO_CREATE+=("$remote_dir")
            fi
        fi
    fi

done < <(find "$ROOT_DIR" -type f ! -path "$ROOT_DIR/uploader/*" -print0)

# Si no hay archivos para subir, terminar
if [[ ${#FILES_TO_UPLOAD[@]} -eq 0 ]]; then
    echo "✅ Nothing to upload. Everything is up to date."
    exit 0
fi

echo ""
echo "🚀 Uploading ${#FILES_TO_UPLOAD[@]} file(s)…"

# Construir comando mpremote con todos los archivos
MPREMOTE_CMD="mpremote connect $DEVICE_PORT"

# Crear directorios necesarios dentro de la cadena de comandos
for dir in "${DIRS_TO_CREATE[@]}"; do
    echo "📁 Creating directory: $dir"
    MPREMOTE_CMD+=" + fs mkdir $dir"
done

# Añadir comandos de copia
for i in "${!FILES_TO_UPLOAD[@]}"; do
    local_file="${FILES_TO_UPLOAD[$i]}"
    remote_path="${REMOTE_PATHS[$i]}"
    echo "⬆️  Uploading: $remote_path"
    MPREMOTE_CMD+=" + fs cp \"$local_file\" \":$remote_path\""
done

# Añadir reset al final
MPREMOTE_CMD+=" + reset"

# Ejecutar comando único (filtrando errores de directorio existente y traceback)
echo ""
echo "📤 Executing mpremote..."
eval "$MPREMOTE_CMD" 2>&1 | grep -v -E "(EEXIST|Traceback|File \"<stdin>\"|OSError|^$)" || true

# Actualizar checksums solo si la subida fue exitosa
echo ""
echo "💾 Updating checksums..."
for i in "${!FILES_TO_UPLOAD[@]}"; do
    rel="${REMOTE_PATHS[$i]}"
    checksum="${CHECKSUMS[$i]}"
    # Eliminar entrada anterior y añadir nueva
    grep -v "^$rel:" "$CHECKSUM_DB" > "$CHECKSUM_DB.tmp" || true
    echo "$rel:$checksum" >> "$CHECKSUM_DB.tmp"
    mv "$CHECKSUM_DB.tmp" "$CHECKSUM_DB"
done

echo "🎉 Done! Uploaded ${#FILES_TO_UPLOAD[@]} file(s)."
