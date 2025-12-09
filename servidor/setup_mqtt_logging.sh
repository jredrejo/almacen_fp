#!/bin/bash

# Script para configurar permisos y rotación de logs para mqtt-listener

set -e

echo "Configurando logging para mqtt-listener..."

# Verificar si estamos en un sistema Linux (no Windows)
if [ -d "/var/log" ]; then
    # Crear el archivo de log si no existe
    LOG_FILE="/var/log/mqtt-listener.log"
    
    # Crear el archivo vacío si no existe
    touch "$LOG_FILE"
    
    # Configurar permisos para que www-data pueda escribir
    echo "Configurando permisos para $LOG_FILE..."
    chown www-data:www-data "$LOG_FILE"
    chmod 664 "$LOG_FILE"
    
    # Configurar logrotate para el archivo
    echo "Configurando logrotate..."
    LOGROTATE_CONFIG="/etc/logrotate.d/mqtt-listener"
    
    cat > "$LOGROTATE_CONFIG" << 'EOF'
/var/log/mqtt-listener.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 664 www-data www-data
    postrotate
        systemctl reload mqtt-rfid.service > /dev/null 2>&1 || true
    endscript
}
EOF
    
    echo "Permisos configurados correctamente."
    echo "Logrotate configurado en $LOGROTATE_CONFIG"
else
    echo "No se detectó /var/log - probablemente no estás en un sistema Linux."
    echo "El script de Python usará automáticamente un archivo local 'logs/mqtt-listener.log'."
fi

echo "El servicio mqtt-rfid.service debe ser reiniciado para aplicar los cambios."