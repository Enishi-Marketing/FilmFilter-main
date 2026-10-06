# Build the existing Qt editor with its Python runtime and stock presets.
from pathlib import Path
version = Path('VERSION').read_text().strip()
a = Analysis(['gui.py'], pathex=[], binaries=[], datas=[('presets', 'presets'), ('VERSION', '.')],
             hiddenimports=['objc', 'Foundation', 'AppKit'], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FilmFilter', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FilmFilter')
app = BUNDLE(coll, name='Film Filter.app', icon='assets/app_icon.icns', bundle_identifier='jp.ac.enishi.film-filter',
             info_plist={'CFBundleShortVersionString': version, 'CFBundleVersion': version,
                         'NSHighResolutionCapable': True, 'LSMinimumSystemVersion': '14.0'})
