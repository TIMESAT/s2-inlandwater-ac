from typing import Dict

from .acolite import AcoliteBackend
from .base import Backend
from .c2rcc import C2rccBackend
from .ocsmart import OcsmartBackend
from .polymer import PolymerBackend


BACKENDS: Dict[str, Backend] = {
    backend.name: backend
    for backend in (
        AcoliteBackend(),
        C2rccBackend(),
        OcsmartBackend(),
        PolymerBackend(),
    )
}


def get_backend(name: str) -> Backend:
    return BACKENDS[name]
