"""
PyInstaller entry point for the comprestimator backend.

Port-allocation strategy (race-condition-free):
  1. Bind a TCP socket on 127.0.0.1:0  →  OS assigns a free ephemeral port.
  2. Announce the chosen port as a JSON line on stdout BEFORE uvicorn starts.
     Electron reads that line to know where to open the browser window.
  3. Pass the pre-bound socket directly to uvicorn so it never releases and
     re-binds — eliminating the TOCTOU window that causes [Errno 48].
"""
from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import socket
import sys


async def _serve(sock: socket.socket) -> None:
    import uvicorn
    from backend.main import app  # noqa: PLC0415 — deferred import intentional

    config = uvicorn.Config(app, log_level="info")
    server = uvicorn.Server(config)
    await server.serve(sockets=[sock])


def main() -> None:
    # Bind the socket here so the port is reserved for the lifetime of this
    # process.  Passing it to uvicorn means uvicorn never needs to call bind()
    # itself — the "already in use" race cannot occur.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    requested_port = int(os.environ.get("PORT", "0"))  # 0 = let OS pick
    sock.bind(("127.0.0.1", requested_port))
    sock.listen(128)
    actual_port = sock.getsockname()[1]

    # Write the port as a JSON line on stdout.  Uvicorn logs go to stderr, so
    # this line will always be the first stdout output Electron sees.
    sys.stdout.write(json.dumps({"port": actual_port}) + "\n")
    sys.stdout.flush()

    asyncio.run(_serve(sock))


if __name__ == "__main__":
    # Required for PyInstaller + Python multiprocessing on macOS/Windows.
    multiprocessing.freeze_support()
    main()
