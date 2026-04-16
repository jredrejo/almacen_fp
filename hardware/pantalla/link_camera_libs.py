"""
Compile and link custom ESP-IDF camera components into the PlatformIO build.

pioarduino does not run cmake for local components/ so we compile them
directly via SCons and link the resulting static libraries.

esp_ipa uses a prebuilt library and needs --whole-archive so detection
function symbols are not garbage-collected by the linker.
"""
import os
Import("env")

project_dir = env.subst("$PROJECT_DIR")
components_dir = os.path.join(project_dir, "components")

# ---------------------------------------------------------------------------
# Helper: build a static library from component sources
# ---------------------------------------------------------------------------
def build_idf_component(name, srcs, include_dirs, priv_include_dirs=None):
    """Compile sources into a static library and add to link."""
    abs_srcs = [os.path.join(components_dir, name, s) for s in srcs]
    abs_incs = [os.path.join(components_dir, name, d) for d in include_dirs]
    abs_priv_incs = (
        [os.path.join(components_dir, name, d) for d in priv_include_dirs]
        if priv_include_dirs else []
    )

    env.Append(CPPPATH=abs_incs + abs_priv_incs)
    objects = [env.Object(src) for src in abs_srcs]
    lib = env.StaticLibrary(name, objects)
    env.Prepend(LIBS=[lib])


# ---------------------------------------------------------------------------
# esp_sccb_intf  (no conditional sources needed for ESP32-P4)
# ---------------------------------------------------------------------------
build_idf_component("esp_sccb_intf",
    srcs=[
        "src/sccb.c",
        "sccb_i2c/src/sccb_i2c.c",
    ],
    include_dirs=["include", "interface", "sccb_i2c/include"],
)

# ---------------------------------------------------------------------------
# esp_cam_sensor  (only SC202CS sensor compiled in)
# ---------------------------------------------------------------------------
build_idf_component("esp_cam_sensor",
    srcs=[
        "src/esp_cam_sensor.c",
        "sensors/sc202cs/sc202cs.c",
    ],
    include_dirs=["include", "sensors/sc202cs/include"],
    priv_include_dirs=["sensors/sc202cs/private_include"],
)

# ---------------------------------------------------------------------------
# esp_video
# ---------------------------------------------------------------------------
build_idf_component("esp_video",
    srcs=[
        "src/esp_video_buffer.c",
        "src/esp_video_init.c",
        "src/esp_video_ioctl.c",
        "src/esp_video_mman.c",
        "src/esp_video_vfs.c",
        "src/esp_video.c",
        "src/esp_video_sensor.c",
        "src/device/esp_video_csi_device.c",
        "src/device/esp_video_isp_device.c",
        "src/esp_video_isp_pipeline.c",
    ],
    include_dirs=["include"],
    priv_include_dirs=["private_include"],
)

# ---------------------------------------------------------------------------
# esp_ipa  (prebuilt library — needs --whole-archive)
# ---------------------------------------------------------------------------
esp_ipa_lib = os.path.join(
    components_dir, "esp_ipa", "lib", "esp32p4", "libesp_ipa.a"
)
env.Prepend(LINKFLAGS=[
    "-Wl,--whole-archive",
    esp_ipa_lib,
    "-Wl,--no-whole-archive",
])
