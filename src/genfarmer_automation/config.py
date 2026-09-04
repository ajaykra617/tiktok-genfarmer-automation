from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    genfarmer_base_url: str = os.getenv("GENFARMER_BASE_URL", "http://127.0.0.1:PORT")
    xproxy_host: str = os.getenv("XPROXY_HOST", "XPROXY_LAN_IP")
    default_device_adb: str = os.getenv("DEFAULT_DEVICE_ADB", "DEVICE_IP:5555")
    evidence_dir: str = os.getenv("EVIDENCE_DIR", "./evidence")
