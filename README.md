# 🛡️ FIMS - File Integrity Monitor v3.0

A Python-based File Integrity Monitoring System that detects unauthorized file changes using SHA-256 hashing.

---

## ✨ Features

- 🔐 SHA-256 hashing for file integrity verification
- 👁️ Real-time Watch Mode — detects changes instantly
- ⏱️ Auto-Scan — scheduled scanning at custom intervals
- ⚠️ Quarantine Manager — isolate suspicious files
- 📧 Email Alerts — get notified on file modification
- ✈️ Telegram Alerts — instant Telegram notifications
- 📋 Report Viewer — view scan history
- 📊 Export reports as CSV or TXT
- 🌙 Light / Dark theme support

---

## 🚀 Installation

### Requirements
- Python 3.x
- tkinter (usually pre-installed)

### Linux
```bash
sudo apt install python3-tk
python3 fims.py
```

### Windows
```bash
python fims.py
```

---

## 📖 How to Use

1. **Init Baseline** — Select folder, create hash database
2. **Scan Folder** — Detect any changes since baseline
3. **Watch Mode** — Real-time continuous monitoring
4. **Check File** — Verify single file integrity

---

## 🔒 Security Note

Never share or upload these files:
- `fims_settings.json` (contains passwords/tokens)
- `baseline.json`
- `report.json`

---

## 👩‍💻 Author

Made by Prajapati Amisha
