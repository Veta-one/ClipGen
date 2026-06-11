import faulthandler
import os
import site
import sys


def log(message):
    print(message, flush=True)


def bootstrap_user_site():
    if sys.platform != "win32":
        return
    user_site = site.getusersitepackages()
    if os.path.isdir(user_site) and user_site not in sys.path:
        sys.path.insert(0, user_site)
    log(f"user_site={user_site}")


def model_path():
    return os.path.abspath(
        os.path.join(
            os.getcwd(),
            "Models",
            "models--Systran--faster-whisper-medium",
            "snapshots",
            "08e178d48790749d25932bbc082711ddcfdfbc4f",
        )
    )


faulthandler.enable(all_threads=True)
log("TEST 01: ctranslate2 only")
bootstrap_user_site()

import ctranslate2

log(f"ct2={ctranslate2.__version__}")
log(f"cuda_devices={ctranslate2.get_cuda_device_count()}")
path = model_path()
log(f"loading={path}")
model = ctranslate2.models.Whisper(path, device="cpu", compute_type="int8")
log("loaded_ok")
