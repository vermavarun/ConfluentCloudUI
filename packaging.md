# Packaging — Confluent ACL Manager

## Prerequisites

Make sure dependencies are installed in your virtual environment:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## macOS — `.app` Bundle

### 1. (Optional) Convert icon to `.icns` for a proper dock icon

```bash
mkdir icon.iconset
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 64  64    icon.png --out icon.iconset/icon_64x64.png
sips -z 32  32    icon.png --out icon.iconset/icon_32x32.png
iconutil -c icns icon.iconset
```

### 2. Build

```bash
source .venv/bin/activate

pyinstaller --windowed \
  --name "Confluent ACL Manager" \
  --icon icon.icns \
  --add-data "icon.png:." \
  app.py
```

> Remove `--icon icon.icns` and use `--icon icon.png` if you skipped step 1.

### 3. Output

```
dist/Confluent ACL Manager.app
```

Drag it to `/Applications` to install, or zip `dist/Confluent ACL Manager.app` to distribute.

---

## Windows — `.exe`

> PyInstaller builds for the **host OS only**. Run this on a Windows machine.

### 1. Convert icon to `.ico`

Run this once in Python:

```python
from PIL import Image
Image.open("icon.png").save(
    "icon.ico",
    format="ICO",
    sizes=[(256, 256), (128, 128), (64, 64), (32, 32)],
)
```

### 2. Install dependencies

```bat
pip install customtkinter pexpect Pillow pyinstaller
```

### 3. Build

```bat
pyinstaller --onefile --windowed ^
  --name "Confluent ACL Manager" ^
  --icon icon.ico ^
  --add-data "icon.png;." ^
  app.py
```

### 4. Output

```
dist\Confluent ACL Manager.exe
```

Distribute the single `.exe` file.

---

## Notes

- The **Confluent CLI** (`confluent`) must be installed on the end-user's machine. It is not bundled — the app calls it via subprocess.
- The `build/` and `dist/` folders and the generated `.spec` file can be added to `.gitignore`.

```gitignore
build/
dist/
*.spec
```
