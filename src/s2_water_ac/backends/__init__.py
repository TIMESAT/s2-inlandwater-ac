from typing import Dict

from .acolite import AcoliteBackend
from .base import Backend
from .c2rcc import C2rccBackend
from .polymer import PolymerBackend


BACKENDS: Dict[str, Backend] = {
    backend.name: backend
    for backend in (AcoliteBackend(), C2rccBackend(), PolymerBackend())
}


def get_backend(name: str) -> Backend:
    return BACKENDS[name]
