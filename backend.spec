# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — bundles backend_entry.py + all Python deps + frontend/dist
into a single self-contained macOS binary: dist/comprestimator-backend
"""

from pathlib import Path

ROOT = Path(SPECPATH)  # repo root (where this .spec lives)

a = Analysis(
    [str(ROOT / "backend_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Bundle the pre-built React app so FastAPI can serve it statically.
        # backend/main.py resolves the path via Path(__file__).parents[1],
        # which points to sys._MEIPASS in a frozen executable — so this
        # relative destination must match exactly.
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    ],
    hiddenimports=[
        # uvicorn internals that PyInstaller misses via static analysis
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # async / network
        "anyio",
        "anyio._backends._asyncio",
        "h11",
        "h11._readers",
        "h11._writers",
        "websockets",
        "websockets.legacy",
        "websockets.legacy.server",
        # starlette middleware & static files
        "starlette.middleware.cors",
        "starlette.staticfiles",
        "starlette.responses",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Trim heavyweight libs that we definitely don't use.
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="comprestimator-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX compression is off — it triggers macOS Gatekeeper warnings on
    # binaries that aren't notarized, and slows cold startup noticeably.
    upx=False,
    console=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
