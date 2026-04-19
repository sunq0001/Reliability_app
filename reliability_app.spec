# -*- mode: python ; coding: utf-8 -*-

import sys
import os

# 获取 matplotlib 字体目录
import matplotlib
matplotlib_font_dir = os.path.dirname(matplotlib.matplotlib_fname())
font_cache_dir = os.path.join(os.path.dirname(matplotlib_font_dir), 'fontdata')

# 收集数据文件
datas = [
    (matplotlib_font_dir, 'matplotlib/mpl-data'),
]

# 如果字体缓存目录存在，也打包进去
if os.path.exists(font_cache_dir):
    datas.append((font_cache_dir, 'matplotlib/fontdata'))

a = Analysis(
    ['reliability_app.py',
     'src/data_loader.py',
     'src/analyzer.py',
     'src/chart_builder.py',
     'src/ui_components.py',
     'src/project_scanner.py',
     'src/image_scanner.py',
     'src/chart_viewer.py',
     'src/image_viewer.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'numpy', 'pandas', 'scipy',
        'tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox',
        'matplotlib', 'matplotlib.pyplot', 'matplotlib.figure',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends._backend_tk',
        'matplotlib.font_manager',
        'PIL', 'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='reliability_app',
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
