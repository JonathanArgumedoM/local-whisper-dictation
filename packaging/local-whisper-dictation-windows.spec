# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

PROJECT = Path(SPECPATH).parent
FASTER_WHISPER_DATAS = collect_data_files('faster_whisper', includes=['assets/*'])

block_cipher = None

a = Analysis(
    [str(PROJECT / 'src' / 'dictation_app.py')],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=FASTER_WHISPER_DATAS,
    hiddenimports=[
        'av',
        'ctranslate2',
        'faster_whisper',
        'huggingface_hub',
        'numpy',
        'onnxruntime',
        'openai',
        'pynput',
        'sounddevice',
        'tokenizers',
    ],
    hookspath=[],
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
    [],
    exclude_binaries=True,
    name='TravelDeskWhisper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(PROJECT / 'packaging' / 'traveldesk-whisper.ico'),
    version=str(PROJECT / 'packaging' / 'windows-version.txt'),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TravelDeskWhisper',
)
