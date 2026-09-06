# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os

block_cipher = None

# Collect all resources for qtawesome (vector fonts, metadata, json definitions)
datas = collect_data_files('qtawesome')

# Hidden imports ensuring all modules, QtSvg widgets, pyodbc and inventree client are included
hiddenimports = [
    'pyodbc',
    'qtawesome',
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'olefile',
    'svgwrite',
    'pyaltiumlib',
    'inventree_client',
]
hiddenimports += collect_submodules('qtawesome')

pathex = [
    os.path.abspath('.'),
]
if os.path.exists(r'D:\mansouri\Programs\Inventree\rack-viewer'):
    pathex.append(r'D:\mansouri\Programs\Inventree\rack-viewer')

a = Analysis(
    ['run_app.py'],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy', 'IPython', 'notebook'],
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
    name='AltiumDbLibManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
