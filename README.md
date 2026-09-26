# Download Organizer

[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-blue.svg)](https://microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero AI](https://img.shields.io/badge/Zero%20AI-100%25%20Deterministic-emerald.svg)](#zero-ai-guarantee)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

A lightweight, high-performance, deterministic Windows desktop productivity utility that automatically organizes files in your Windows Downloads folder in real time.

Built with **pure Python (Tkinter + ttk)** and designed to feel like a native, responsive Windows 11 utility rather than a script.

---

## 🛡️ Core Safety Principles

> [!IMPORTANT]
> **Safety First — Zero Data Loss Guarantee**
> - **NEVER Deletes Files**: The application contains absolutely zero deletion logic.
> - **NEVER Overwrites Files**: If `resume.pdf` exists, new arrivals are safely named `resume (1).pdf`, `resume (2).pdf`, etc. Multi-dot extensions like `project.backup.zip` become `project.backup (1).zip`.
> - **NEVER Executes Files**: Downloaded installers and scripts are never opened or run.
> - **NEVER Modifies Contents**: Files are moved atomically using standard filesystem operations while preserving metadata.
> - **100% Reversible**: Every single file movement is stored in SQLite and can be undone with one click.
> - **100% Local & Offline**: Works completely offline. No telemetry, no background network calls, and no analytics.

---

## 🚫 Absolute Zero-AI Guarantee

This project contains **ZERO artificial intelligence or machine learning**:
- No OpenAI, Gemini, Claude, Copilot, or local LLMs
- No embeddings, vector databases, or semantic search
- No machine learning classifiers or NLP models
- All file classification is 100% deterministic, transparent, and explainable.

---

## ✨ Key Features

- **Real-Time Filesystem Monitoring**: Uses `watchdog` to capture new and moved files without scanning the disk continuously.
- **Active Download Stabilization**: Automatically recognizes browser temporary files (`.crdownload`, `.part`, `.tmp`) and waits until downloads are fully written and unlocked before organizing.
- **Deterministic 5-Tier Classification**:
  1. *User Custom Rules* (Highest priority)
  2. *Extension Rules* (Images, Videos, Audio, PDFs, Documents, Archives, Installers, Code, etc.)
  3. *Filename Rules* (Case-insensitive keyword matching, e.g. `resume`, `DBMS`, `invoice`)
  4. *MIME Types*
  5. *Others* (Safe fallback)
- **Interactive Review Mode**: Optional mode allowing you to approve, skip, or redirect destinations before files are organized.
- **Comprehensive Dashboard**: Real-time stats, folder size, active status indicator, and instant undo on recent items.
- **Custom Rule Engine**: Create compound rules (AND / OR) matching filenames, extensions, file size (`> 10MB`), and dates.
- **SQLite History & Audit Trail**: Full search capability by filename, extension, category, or date without scanning the hard drive.
- **Windows System Tray & Notifications**: Runs unobtrusively in the background with grouped, non-spammy desktop notifications.
- **Start with Windows**: Toggleable startup item using standard user registry without requiring administrator permissions.

---

## 📦 Default Category Structure

Category folders are created inside your Downloads directory **only when needed**:

```
Downloads/
├── Documents/       (.doc, .docx, .txt, .rtf, .odt)
├── Images/          (.jpg, .jpeg, .png, .gif, .webp, .svg, .ico, .bmp)
├── Videos/          (.mp4, .mkv, .avi, .mov, .webm, .flv)
├── Audio/           (.mp3, .wav, .flac, .aac, .m4a, .ogg)
├── PDFs/            (.pdf)
├── Archives/        (.zip, .rar, .7z, .tar, .gz, .bz2)
├── Installers/      (.exe, .msi, .msix, .msixbundle)
├── Code/            (.py, .js, .ts, .java, .cpp, .html, .css, .json, .sql)
├── Spreadsheets/    (.xls, .xlsx, .csv, .ods)
├── Presentations/   (.ppt, .pptx, .odp)
├── Executables/     (.com, .scr)
├── Torrents/        (.torrent)
├── Resume/          (filename contains 'resume' or 'cv')
├── College/         (filename contains 'dbms', 'assignment', 'semester', 'exam')
├── Invoices/        (filename contains 'invoice', 'receipt', 'bill')
└── Others/          (unmatched files)
```

*(Note: `.exe` files default to `Installers` for safety and user convenience).*

---

## ⚡ 1-Click Instant Sort (Done in Seconds)

You can organize your entire Downloads folder in **1 click** with zero setup:

- **Option A (Desktop Batch Shortcut)**: Double-click [Organize Downloads Now.bat](file:///d:/organizer/Organize%20Downloads%20Now.bat). It sorts all files across your Downloads folder safely in 1–2 seconds and exits automatically.
- **Option B (Desktop App)**: Click the **⚡ Instant Organize (1-Click)** button on the Dashboard.
- **Option C (Command Line / Task Scheduler)**:
  ```cmd
  d:\organizer\dist\DownloadOrganizer.exe --quick
  ```

---

## ↩️ 1-Click Reversible Undo (Restore Instantly)

Changed your mind or want your files back in their original Downloads root?

- **Option A (Desktop Shortcut)**: Double-click [Undo Last Organization.bat](file:///d:/organizer/Undo%20Last%20Organization.bat) or [Undo.bat](file:///d:/organizer/Undo.bat). Restores all files back to their exact original locations in 1 second!
- **Option B (Desktop App)**: Click the **↩️ Undo Last Sort** button right next to Instant Organize on the Dashboard header or in the sidebar.
- **Option C (System Tray)**: Right-click the system tray icon and click **Undo Last Organization**.
- **Option D (Command Line)**:
  ```cmd
  d:\organizer\dist\DownloadOrganizer.exe --undo
  ```


---

## 🚀 Installation & Usage


### Option 1: Standalone Windows Executable (Recommended)

1. Download `DownloadOrganizer.exe` from GitHub Releases.
2. Double-click to launch.
3. The first-launch setup will detect your Windows Downloads folder and present an optional preview of existing files.
4. Done! No Python or terminal required.

### Option 2: Running from Source

1. Clone or download the repository:
   ```cmd
   git clone https://github.com/download-organizer/download-organizer.git
   cd download-organizer
   ```
2. Double-click `Start Download Organizer.bat` or run:
   ```cmd
   start.bat
   ```
   The launcher automatically checks your Python version (>= 3.10), sets up a local virtual environment, installs dependencies, and launches the app silently.

---

## 🛠️ Building the Standalone Executable

To compile `dist/DownloadOrganizer.exe` using PyInstaller:

```cmd
build.bat
```

Or manually:
```cmd
python -m pip install -r requirements.txt pyinstaller
python -m pytest tests/
python -m PyInstaller --clean DownloadOrganizer.spec
```

The compiled single-file executable will be generated at `dist/DownloadOrganizer.exe`.

---

## 📂 Project Structure

```
download-organizer/
├── app/
│   ├── main.py             # Application bootstrap & tray integration
│   ├── config.py           # Configuration in %APPDATA%\DownloadOrganizer\
│   ├── database.py         # SQLite connection, history & rules persistence
│   ├── watcher.py          # Watchdog observer & stabilization worker
│   ├── classifier.py       # Deterministic 5-tier classification logic
│   ├── rules.py            # Custom rule evaluation engine
│   ├── organizer.py        # Safe file movement engine (never deletes/overwrites)
│   ├── history.py          # History audit trail & one-click Undo
│   ├── tray.py             # System tray menu (pystray)
│   ├── notifications.py    # Debounced Windows desktop notifications
│   ├── ui.py               # Responsive Tkinter + ttk modern GUI
│   └── utils.py            # Windows known folders, safe paths, autostart
│
├── assets/
│   ├── icon.ico            # Windows application icon
│   └── icon.png            # High-resolution emblem
│
├── tests/
│   ├── test_classifier.py  # Tests for extension & filename mappings
│   ├── test_rules.py       # Tests for condition operators & compound rules
│   ├── test_organizer.py   # Tests for safe movements & folder creation
│   ├── test_duplicates.py  # Tests for collision numbering (e.g. file (1).ext)
│   ├── test_history.py     # Tests for audit recording & undo reversibility
│   └── test_realistic_scenarios.py # Real-world downloads validation suite
│
├── requirements.txt        # Minimal runtime dependencies
├── requirements-lock.txt   # Pinned dependency versions
├── start.bat               # Automated launcher for source distributions
├── Start Download Organizer.bat
├── build.bat               # Automated PyInstaller build script
├── DownloadOrganizer.spec  # PyInstaller configuration
├── README.md               # Documentation
└── LICENSE                 # MIT License
```

---

## 🧪 Automated Testing

All tests run in temporary directories and **never touch your real Downloads directory**:

```cmd
python -m pytest tests/ -v
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
#   s o r t y  
 