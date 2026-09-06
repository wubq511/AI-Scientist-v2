from __future__ import annotations

import socket
from typing import Any

from .errors import fail


def _deny_network(*_args: Any, **_kwargs: Any) -> None:
    fail(
        "NETWORK_ACCESS_DENIED",
        "Local-ranking workers cannot access the network during scoring",
    )


def install_network_guard() -> None:
    """Deny Python socket DNS/connect paths for the lifetime of one worker."""

    class DeniedSocket(socket.socket):
        def connect(self, *_args: Any, **_kwargs: Any) -> None:
            _deny_network()

        def connect_ex(self, *_args: Any, **_kwargs: Any) -> int:
            _deny_network()

    socket.socket = DeniedSocket
    socket.create_connection = _deny_network
    socket.getaddrinfo = _deny_network
