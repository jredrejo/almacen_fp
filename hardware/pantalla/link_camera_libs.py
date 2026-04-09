"""
Explicitly wire custom ESP-IDF camera components into the SCons link step.
The pioarduino framework builder compiles these components via cmake but
does not always propagate their library paths to the final SCons linker
invocation for local (non-managed) components.

esp_ipa uses a prebuilt library and must be linked with --whole-archive so
the detection function symbols (referenced via the detect array in
cam_detect_glue.c) are not garbage-collected.
"""
import os
Import("env")

build_dir = env.subst("$BUILD_DIR")
project_dir = env.subst("$PROJECT_DIR")
idf_dir = os.path.join(build_dir, "esp-idf")

# Compiled-from-source components: add their build output dirs to LIBPATH
for lib in ["esp_video", "esp_cam_sensor", "esp_sccb_intf"]:
    lib_dir = os.path.join(idf_dir, lib)
    env.Prepend(LIBPATH=[lib_dir])

env.Prepend(LIBS=["esp_video", "esp_cam_sensor", "esp_sccb_intf"])

# Prebuilt esp_ipa: link with --whole-archive so detection fn symbols survive GC
esp_ipa_lib = os.path.join(
    project_dir, "components", "esp_ipa", "lib", "esp32p4", "libesp_ipa.a"
)
env.Prepend(LINKFLAGS=[
    "-Wl,--whole-archive",
    esp_ipa_lib,
    "-Wl,--no-whole-archive",
])
