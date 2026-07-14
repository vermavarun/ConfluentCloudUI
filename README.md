# Confluent ACL Manager

A native desktop app for managing Confluent Cloud ACLs, Identity Pools, Role Bindings, and Service Accounts — without needing API keys. Authentication is handled entirely via your company SSO through the Confluent CLI.

---

## Features

- **SSO Login** — signs in via `confluent login --save`; your browser opens automatically
- **ACL Permissions** — search ACLs by principal (auto-prefixes `User:` if omitted)
- **Identity Pools** — list pools for an identity provider
- **Role Bindings** — list RBAC role bindings by principal (auto-prefixes `User:` if omitted)
- **Service Accounts** — list all service accounts
- **Live filter** — search bar above all tabs filters results in real time across all tabs
- **Download CSV** — export the current tab's (optionally filtered) data to a `.csv` file
- **Environment & Cluster selector** — sidebar dropdowns auto-load on login; switching env reloads clusters automatically

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.10+ | Tested on Python 3.14 (Homebrew) |
| [Confluent CLI](https://docs.confluent.io/confluent-cli/current/install.html) | Must be installed and on `PATH` |
| macOS / Windows | Linux should work but is untested |

---

## Setup

```bash
# Clone / download the project
cd TestConfluentUI

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python app.py
```

> **macOS Tkinter note**: if you see `No module named '_tkinter'`, run:
> ```bash
> brew install python-tk@3.14
> ```
> Then recreate the venv with `rm -rf .venv && python3.14 -m venv .venv`.

---

## Usage

1. Launch the app and enter your company email
2. Click **Login with SSO →** — your browser will open automatically
3. Complete the SSO flow in the browser
4. Select an **Environment** and **Cluster** from the sidebar
5. Use the tabs to explore:

| Tab | What to enter |
|---|---|
| 🔑 ACL Permissions | Principal ID (e.g. `pool-RkAya` or `User:sa-XXXXX`) |
| 👥 Identity Pools | Identity Provider ID (e.g. `op-XXXXX`) |
| 📋 Role Bindings | Principal ID (optional; leave blank to list all) |
| 🤖 Service Accounts | No input needed — click Load |

**Filter**: type in the search bar above the tabs to filter results across all tabs in real time. Click **✕** to clear.

**Download CSV**: click **⬇ Download CSV** to export the current tab's visible rows.

---

## Packaging

See [packaging.md](packaging.md) for full instructions on building a double-click executable:

- **macOS** → `.app` bundle via PyInstaller
- **Windows** → `.exe` via PyInstaller

Quick build (macOS):
```bash
source .venv/bin/activate
pyinstaller --windowed --name "Confluent ACL Manager" --icon icon.icns --add-data "icon.png:." app.py
# Output: dist/Confluent ACL Manager.app
```

> The Confluent CLI must be installed on the end-user's machine — it is not bundled.

---

## Project Structure

```
app.py              # Main application
requirements.txt    # Python dependencies
packaging.md        # Build & distribution instructions
icon.png            # App icon
```

---

## Developer

**Varun Verma**
[github.com/vermavarun](https://github.com/vermavarun)
