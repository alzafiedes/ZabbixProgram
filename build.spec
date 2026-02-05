# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Zabbix Metrics Extractor
Build with: pyinstaller build.spec
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect CustomTkinter data files
ctk_datas = collect_data_files('customtkinter')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=ctk_datas,
    hiddenimports=[
        'pyzabbix',
        'PIL',
        'PIL.Image',
        'requests',
        'customtkinter',
        'pandas',
        'numpy',
        'reportlab',
        'reportlab.lib.pagesizes',
        'reportlab.platypus',
        'matplotlib',
        'matplotlib.pyplot',
        'matplotlib.dates',
        'zabbix_client',
        'chart_downloader',
        'trend_analyzer',
        'pdf_generator',
    ] + collect_submodules('customtkinter') + collect_submodules('pandas') + collect_submodules('reportlab'),
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ZabbixMetricsExtractor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if desired: icon='icon.ico'
)
