How to use this code to upload a project to m5stack Tab5



Perfect — here is a **fully-featured Linux upload system** for your M5Stack Tab5 (MicroPython).  
It includes:

- 🔄 **Only changed files uploaded**

- 🚀 **Fast dev cycle**

- 🔍 **Progress for each file**

- 🧹 **Auto-avoid .git, venv, caches**

- 💾 **Checksum database prevents unnecessary writes**

- ⚙️ **Works with Tab5 / any ESP32 MicroPython

- ✔ Safe for large projects

- ✔ Works with `mpremote`

- ✔ Configurable port



Everything is in one folder and ready to use.

---
# ✅ **Previous conditions**
- mpremote must be installed `sudo apt install micropython-mpremote`
- usb port in the computer after the tab5 is connected is `/dev/ttyACM0`. If not you must modify upload.sh and clean_flash.sh

# ✅ **Expected project structure**

You will end up with:

```
project/
   uploader/
      upload.sh
      upload_file.sh
      checksum_db.txt
      exclude.lst
   main.py
   lib/
   assets/
```

Below are the list of files and their functions

---

# 📌 1. `uploader/upload.sh`

**This is the main script** you run.  
Uploads only changed files, shows progress, and excludes unwanted paths.---

# 📌 2. `uploader/upload_file.sh`

Handles uploading **one** file to `/flash/…`.

# 📌 3. `uploader/exclude.lst`

Patterns and paths to **ignore**. Add anything else you want excluded.

---



# ▶️ How to Use

## **One-time setup**

```bash
chmod +x uploader/*.sh
```

## **Normal incremental upload**

```bash
./uploader/upload.sh
```

## **If your device port is different**

```bash
./uploader/upload.sh /dev/ttyACM0
```

## **Clean device flash**

```bash
./uploader/clean_flash.sh
```


# Arduino libraries documentation:

https://docs.m5stack.com/en/arduino/m5gfx/m5gfx
https://docs.m5stack.com/en/arduino/m5gfx/m5gfx_functions


# Para depurar:
mpremote connect /dev/ttyACM0 repl
# Borrar un fichero manualmente:
mpremote connect /dev/ttyACM0 fs rm :nombre_fichero
# Copiar un fichero manualmente
mpremote connect /dev/ttyACM0 fs cp nombre_fichero  :nombre_fichero
