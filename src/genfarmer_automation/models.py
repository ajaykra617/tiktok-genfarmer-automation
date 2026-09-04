from dataclasses import dataclass
from typing import Optional

@dataclass
class Device:
    name: str
    adb_id: str
    genfarmer_id: Optional[str] = None
    xproxy_position: Optional[int] = None
    http_proxy: Optional[str] = None
    socks5_proxy: Optional[str] = None
