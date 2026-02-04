# PyInstaller spec: сборка FundingRate.exe
# Запуск: pyinstaller FundingRate.spec
# Перед сборкой: pip install -r requirements.txt (чтобы uvicorn был в окружении)

# -*- mode: python ; coding: utf-8 -*-
import os
# Папка со spec (текущая при запуске pyinstaller из папки проекта)
spec_dir = os.getcwd()

block_cipher = None

a = Analysis(
    ['run_gui.py'],
    pathex=[spec_dir],
    binaries=[],
    datas=[],
    hiddenimports=[
        'app_state',
        'config',
        'main',
        'routers',
        'routers.funding',
        'services',
        'services.exchange_fetcher',
        'storage',
        'storage.parquet_cache',
        'gui',
        'gui.window',
        'uvicorn',
        'fastapi',
        'httpx',
        'starlette',
    ],
    hookspath=[os.path.join(spec_dir, 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FundingRate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # без консоли — только окно GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
