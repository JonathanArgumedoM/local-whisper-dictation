# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

PROJECT = Path(SPECPATH).parent

block_cipher = None

a = Analysis(
    [str(PROJECT / 'src' / 'dictation_app.py')],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=[
        (str(PROJECT / 'config.json'), '.'),
        (str(PROJECT / 'README.md'), '.'),
    ],
    hiddenimports=[
        'av',
        'ctranslate2',
        'faster_whisper',
        'huggingface_hub',
        'numpy',
        'onnxruntime',
        'pynput',
        'sounddevice',
        'tokenizers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
app = BUNDLE(
    coll,
    name='TravelDeskWhisper.app',
    icon=None,
    bundle_identifier='mx.traveldesk.whisper',
    info_plist={
        'NSMicrophoneUsageDescription': 'TravelDesk Whisper needs microphone access to transcribe your voice.',
        'NSAppleEventsUsageDescription': 'TravelDesk Whisper needs accessibility permissions to paste dictated text.',
    },
)