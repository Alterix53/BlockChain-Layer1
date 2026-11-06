"""Load trusted simulation identities independently of network randomness."""
import json
from pathlib import Path

from .common import H, KeyPair
from .configuration import WORKSPACE


def identity_keys(cfg):
    """Trusted private fixture independent of the public network RNG seed."""
    path = Path(cfg.get("identity_file", "config/identities.json"))
    if not path.is_absolute():
        path = WORKSPACE / path
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    try:
        secret = bytes.fromhex(data["master_secret"])
        if len(secret) != 32:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("identity_file cần master_secret 32 byte hex") from None
    def key(role, name):
        return KeyPair(H(secret + b"\x00" + role.encode() + b"\x00" + name.encode()))
    return ([key("validator", str(i)) for i in range(cfg["n"])],
            {a: key("account", a) for a in cfg["accounts"]})
