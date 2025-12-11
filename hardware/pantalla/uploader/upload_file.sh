#!/usr/bin/env bash

DEVICE_PORT="$1"
LOCAL_FILE="$2"
REMOTE_PATH="$3"

REMOTE_DIR=$(dirname "$REMOTE_PATH")
# Create directory if needed (skip if just current directory)
if [ "$REMOTE_DIR" != "." ]; then
    mpremote connect "$DEVICE_PORT" fs mkdir "$REMOTE_DIR" 2>/dev/null || true
fi

# Upload file
mpremote connect "$DEVICE_PORT" fs cp "$LOCAL_FILE" ":$REMOTE_PATH"
