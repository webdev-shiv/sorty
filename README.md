# Sorty — Intelligent Deterministic Windows Download Organizer

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D4.svg?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![Zero AI](https://img.shields.io/badge/AI%20Status-0%25%20AI%20%7C%20100%25%20Deterministic-brightgreen.svg)](#-unique-selling-points-usps)
[![Python Version](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-Pure%20Tkinter%20%2B%20High--DPI-blueviolet.svg)](#-user-interface-architecture)
[![Safety Bar](https://img.shields.io/badge/Safety-Zero%20Data%20Loss%20Invariant-red.svg)](#-core-safety-invariants)

**Sorty** is a high-speed, lightweight, deterministic Windows desktop background agent and productivity utility that organizes files in your Windows Downloads folder in real time. Built in pure Python (Tkinter + ttk + Watchdog + SQLite) with zero heavy web runtimes or external telemetry, Sorty looks and feels like a native Windows 11 utility.

---

## 📑 Table of Contents

1. [🌟 Unique Selling Points (USPs)](#-unique-selling-points-usps)
2. [🛡️ Core Safety Invariants](#-core-safety-invariants)
3. [📊 System Flowcharts & Architecture](#-system-flowcharts--architecture)
   - [1. High-Level System Architecture](#1-high-level-system-architecture)
   - [2. Real-Time File Watcher & Stabilization Lifecycle](#2-real-time-file-watcher--stabilization-lifecycle)
   - [3. Deterministic 5-Tier Classification Engine](#3-deterministic-5-tier-classification-engine)
   - [4. Safe Movement & Collision Avoidance Flow](#4-safe-movement--collision-avoidance-flow)
   - [5. 1-Click Instant Batch Undo Workflow](#5-1-click-instant-batch-undo-workflow)
4. [📂 Comprehensive Function & Module Reference](#-comprehensive-function--module-reference)
   - [app/main.py](#1-appmainpy)
   - [app/watcher.py & app/background_agent.py](#2-appwatcherpy--appbackground_agentpy)
   - [app/classifier.py](#3-appclassifierpy)
   - [app/rules.py](#4-apprulespy)
   - [app/organizer.py](#5-apporganizerpy)
   - [app/history.py](#6-apphistorypy)
   - [app/database.py](#7-appdatabasepy)
   - [app/config.py](#8-appconfigpy)
   - [app/utils.py](#9-apputilspy)
   - [app/notifications.py](#10-appnotificationspy)
   - [app/tray.py](#11-apptraypy)
   - [app/ui.py](#12-appuipy)
5. [⚡ 1-Click Instant Sort & CLI Usage](#-1-click-instant-sort--cli-usage)
6. [↩️ Reversible Undo System](#-reversible-undo-system)
7. [🚀 Installation & Setup](#-installation--setup)
8. [📄 License](#-license)

---

## 🌟 Unique Selling Points (USPs)

| # | Unique Selling Point | Why It Matters / Technical Edge |
|---|----------------------|---------------------------------|
| **1** | **Absolute Zero AI Guarantee (100% Deterministic)** | Zero LLMs, zero hallucinations, zero prompt-injection risks, and zero token costs. All classification rules are 100% explainable, transparent, and reproducible. |
| **2** | **Zero Data Loss Invariant** | **NEVER deletes files**, **NEVER overwrites files**, **NEVER executes files**, and **NEVER modifies contents**. All operations strictly move files atomically and preserve filesystem metadata. |
| **3** | **Active Download Stabilization** | Unlike naive scripts that prematurely move half-downloaded files, Sorty detects active browser temporary extensions (`.crdownload`, `.part`, `.tmp`), monitors size stability over time, and verifies OS read-locks before moving. |
| **4** | **Sub-Second 1-Click Instant Sort** | Organizes hundreds of unorganized downloads into categorized subfolders in 1–2 seconds via the UI button, desktop batch shortcut, or CLI argument `--quick`. |
| **5** | **1-Click Batch Undo & Reversibility** | Complete SQLite audit trail with bidirectional path recording. Revert the last single move or an entire batch of hundreds of files back to their exact original locations in 1 click. |
| **6** | **WhatsApp Desktop Media Auto-Routing** | Built-in high-priority regex engine matches WhatsApp desktop file naming conventions (`IMG-YYYYMMDD-WA*`, `VID-`, `AUD-`, `DOC-`, `PTT-`, `WA_`) and routes them directly to `WhatsApp Downloads/` before standard extension rules run. |
| **7** | **Smart Multi-Dot Collision Handling** | When destination files collide, Sorty renames intelligently without clobbering compound extensions: `project.backup.zip` becomes `project.backup (1).zip`, not `project.backup.zip (1)`. |
| **8** | **Zero-Bloat Native Windows Footprint** | Pure Python with modern Tkinter and ttk styling. Consumes ~30–40 MB of RAM compared to 500+ MB for Electron/web-based file managers. High-DPI aware with crisp vector font scaling on 4K monitors. |
| **9** | **100% Offline & Private** | Zero telemetry, zero analytics, zero external network pings. Operates strictly on local filesystem and local SQLite database (`%APPDATA%\Sorty\history.db`). |
| **10** | **Non-Intrusive Background Agent & Tray** | Runs silently in the Windows system tray. Features auto-debounced Windows balloon/toast notifications (aggregating 5+ rapid moves into a single notification) and clean user-registry autostart requiring zero administrator privileges. |

---

## 🛡️ Core Safety Invariants

```
               ┌──────────────────────────────────────────────┐
               │         SORTY SAFETY INVARIANTS              │
               ├──────────────────────────────────────────────┤
               │  [x] NO File Deletion Logic in Entire Code   │
               │  [x] NO Overwrites (Collision Renaming)     │
               │  [x] NO File Execution or Script Execution   │
               │  [x] NO Modification of File Binaries/Data   │
               │  [x] Path Traversal Attack Guards            │
               │  [x] Subfolder Protection (No Re-Sorting)    │
               │  [x] Full SQLite Audit Trail for Every Move  │
               └──────────────────────────────────────────────┘
```

1. **Subfolder Isolation**: Sorty only monitors direct children of the Downloads root. Files already organized in category subfolders are strictly skipped to prevent cyclic moves.
2. **Path Traversal Protection**: `is_safe_path()` verifies that all resolved destination folders are strictly subdirectories of the designated Downloads root directory.
3. **Lock Probing**: Before organizing, Sorty tests both a non-destructive 1-byte read stream and an atomic in-place rename to detect active Windows write locks (`WinError 32`).

---

## 📊 System Flowcharts & Architecture

### 1. High-Level System Architecture

```mermaid
graph TD
    subgraph Windows Environment
        OS[Windows Filesystem: Downloads Root] -->|Filesystem Events| WD[Watchdog Observer]
        CLI[CLI Flags: --quick, --undo] --> Main[app/main.py]
        TRAY[Windows System Tray] <--> TM[app/tray.py]
    end

    subgraph Sorty Core Engine
        Main --> CFG[app/config.py]
        Main --> DB[(SQLite: history.db)]
        Main --> BA[app/watcher.py<br/>BackgroundAgent]
        
        WD -->|Events: Created / Modified / Renamed| BA
        BA -->|Debounce & Stabilization| STAB[Download Stabilizer]
        STAB -->|Ready File| CLS[app/classifier.py<br/>Deterministic Classifier]
        
        CLS -->|1. WhatsApp Regex| RES[Category Decision]
        CLS -->|2. Custom Rules Engine| RE[app/rules.py]
        RE --> RES
        CLS -->|3. Keyword Rules| RES
        CLS -->|4. Extension Map| RES
        CLS -->|5. Others Fallback| RES
        
        RES --> ORG[app/organizer.py<br/>SafeOrganizer]
        ORG -->|Atomic Move + Collision Check| OS
        ORG -->|Log Movement| DB
        ORG -->|Trigger Notification| NM[app/notifications.py]
    end

    subgraph User Presentation Layer
        Main --> UI[app/ui.py<br/>DownloadOrganizerApp]
        UI <-->|Queries & Searches| DB
        UI <-->|Batch Undo| HIST[app/history.py]
        HIST -->|Reversible Restore| OS
        HIST -->|Update Status: undone| DB
        NM -->|Debounced Toast| OS
    end
```

---

### 2. Real-Time File Watcher & Stabilization Lifecycle

```mermaid
flowchart TD
    Start([Filesystem Event in Downloads]) --> CheckDir{Is Directory or<br/>in Subfolder?}
    CheckDir -- Yes --> Ignore[Ignore Event]
    CheckDir -- No --> CheckTemp{Has Temporary<br/>Extension?<br/>.crdownload, .part, .tmp}
    
    CheckTemp -- Yes --> EnqueueTemp[Enqueue to Pending Debounce Map]
    EnqueueTemp --> WaitChange[Wait for Download Completion / Rename Event]
    WaitChange --> Start
    
    CheckTemp -- No --> EnqueueWorker[Push Path to Worker Queue]
    EnqueueWorker --> WorkerLoop[Worker Thread Dequeues Item]
    
    WorkerLoop --> StabilizeLoop[Stabilization Check:<br/>Sample File Size over Delay Interval]
    StabilizeLoop --> SizeCheck{File Size Changing?}
    SizeCheck -- Yes --> WaitStab[Sleep Interval & Retry up to 60s]
    WaitStab --> StabilizeLoop
    
    SizeCheck -- No --> LockCheck{Is File Locked<br/>by Another Process?}
    LockCheck -- Yes --> WaitLock[Wait & Retry Lock Probe]
    WaitLock --> StabilizeLoop
    
    LockCheck -- No --> ReviewCheck{Review Mode<br/>Enabled?}
    ReviewCheck -- Yes --> HeldQueue[Hold in WAITING_REVIEW Queue<br/>for User Approval in GUI]
    ReviewCheck -- No --> ExecuteOrg[Dispatch to SafeOrganizer Engine]
```

---

### 3. Deterministic 5-Tier Classification Engine

```mermaid
flowchart TD
    FileIn([Incoming File: Path, Size, MTime]) --> Tier1{Tier 1: Matches WhatsApp<br/>Pattern or Prefix?<br/>IMG-*-WA*, VID-*, WA_}
    Tier1 -- Yes --> CatWA[Destination: WhatsApp Downloads/<br/>Reason: WhatsApp filename pattern]
    
    Tier1 -- No --> Tier2A{Tier 2A: Custom Rules<br/>in SQLite Database?<br/>Evaluated by Priority DESC}
    Tier2A -- Match Found --> CatCustom[Destination: Rule Destination<br/>Reason: User rule 'Rule Name']
    
    Tier2A -- No Match --> Tier2B{Tier 2B: Keyword Rules?<br/>'resume', 'invoice',<br/>'college', 'project'}
    Tier2B -- Match Found --> CatKW[Destination: Matched Category<br/>Reason: Filename contains keyword]
    
    Tier2B -- No Match --> Tier3A{Tier 3A: Category Custom<br/>Extensions in SQLite DB?}
    Tier3A -- Match Found --> CatDBCat[Destination: Custom Category<br/>Reason: Extension .ext]
    
    Tier3A -- No Match --> Tier3B{Tier 3B: Built-in Extension Map?<br/>Images, Videos, PDFs, Docs,<br/>Installers, Archives, Code...}
    Tier3B -- Match Found --> CatExt[Destination: Category Folder<br/>Reason: Extension .ext]
    
    Tier3B -- No Match --> Tier4[Tier 4: Fallback<br/>Destination: Others/<br/>Reason: No matching rule]
```

---

### 4. Safe Movement & Collision Avoidance Flow

```mermaid
flowchart TD
    OrgStart([SafeOrganizer: organize_file]) --> V1{Source Exists &<br/>is Regular File?}
    V1 -- No --> Err1[Return Failed / Skipped Result]
    
    V1 -- Yes --> V2{Parent Folder ==<br/>Downloads Root?}
    V2 -- No --> Err2[Return Skipped: Already Organized]
    
    V2 -- Yes --> V3{File Accessible &<br/>Unlocked?}
    V3 -- No --> Err3[Return Failed: File in Use]
    
    V3 -- Yes --> Classify[Classifier.classify]
    Classify --> PathSafe{is_safe_path:<br/>Target within Downloads?}
    PathSafe -- No --> Err4[Return Failed: Path Traversal Prevented]
    
    PathSafe -- Yes --> Mkdir[Create Category Folder on Demand<br/>dest_dir.mkdir parents=True, exist_ok=True]
    Mkdir --> CollideCheck{File Already Exists<br/>in Destination Folder?}
    
    CollideCheck -- No --> DestFinal[Final Path: dest_dir / filename]
    CollideCheck -- Yes --> GenName[get_unique_destination_path:<br/>stem + ' (counter)' + suffix<br/>e.g. data.backup (1).zip]
    GenName --> DestFinal
    
    DestFinal --> Move[Atomic File Move:<br/>shutil.move src, final_path]
    Move --> Verify{Does Final Path<br/>Exist?}
    Verify -- Yes --> LogSuccess[Insert Record into SQLite history:<br/>status='success']
    LogSuccess --> Done([Return OrganizerResult: Success])
    
    Verify -- No --> LogFail[Insert Record into SQLite history:<br/>status='failed']
    LogFail --> ErrFail([Return OrganizerResult: Failed])
```

---

### 5. 1-Click Instant Batch Undo Workflow

```mermaid
flowchart TD
    UndoTrigger([User Triggers Undo:<br/>GUI Header, Tray Menu, CLI, or Undo.bat]) --> Query[Query SQLite history table:<br/>ORDER BY timestamp DESC<br/>status='success' LIMIT 500]
    Query --> CheckEmpty{Any Records<br/>Found?}
    CheckEmpty -- No --> OutEmpty[Return: No recent movements to undo]
    
    CheckEmpty -- Yes --> GroupBatch[Identify Latest Batch:<br/>All records with timestamp within<br/>60 seconds of latest event]
    GroupBatch --> Loop[Iterate Over Batch Items in Reverse]
    
    Loop --> CheckDest{Destination File<br/>Still Exists?}
    CheckDest -- No --> SkipItem[Skip Item: File moved or deleted by user]
    
    CheckDest -- Yes --> SafeOrig[Calculate Safe Restore Path in Root:<br/>get_unique_destination_path<br/>Prevent Overwriting Existing Root Files]
    SafeOrig --> MoveBack[Atomic Move:<br/>shutil.move destination_path, safe_restore_path]
    MoveBack --> UpdateDB[Update SQLite Record:<br/>status='undone']
    
    UpdateDB --> NextItem{More Items in<br/>Batch?}
    NextItem -- Yes --> Loop
    NextItem -- No --> Summary[Return Restored Count & Display Toast]
```

---

## 📂 Comprehensive Function & Module Reference

### 1. `app/main.py`
Application bootstrapper, CLI flag dispatcher, and system tray lifecycle coordinator.

| Function / Component | Signature | Description |
|----------------------|-----------|-------------|
| `enable_windows_high_dpi` | `() -> None` | Invokes `shcore.SetProcessDpiAwareness(1)` or `user32.SetProcessDpiAwarenessContext(-4)` via ctypes for crisp rendering on high-resolution displays. |
| `setup_logging` | `(logs_dir: Path) -> None` | Configures a 5 MB rotating file handler (`backupCount=3`) at `%APPDATA%\Sorty\logs\app.log` plus stdout stream output. |
| `quick_organize_all` | `(downloads_folder: Optional[str] = None, notify: bool = True) -> int` | Executes 1-click instant organization of all root files in seconds with zero GUI blocking; records full undo trail. |
| `check_single_instance` | `(port: int = 49281) -> bool` | Connects via TCP localhost socket to verify if Sorty is already running. If so, sends `SHOW` command to wake existing window and returns `False`. |
| `start_single_instance_server` | `(app_show_callback, port: int = 49281) -> Optional[socket.socket]` | Spawns a background daemon thread listening on port 49281 to bring the GUI to the foreground when repeated launches occur. |
| `main` | `() -> None` | Application entry point: evaluates CLI flags (`--quick`, `--undo`, `--minimized`), wires DB, Classifier, Organizer, History, Tray, Watcher, and starts Tkinter. |

---

### 2. `app/watcher.py` & `app/background_agent.py`
Real-time filesystem observer, event debouncer, stabilization manager, and worker loop.

| Class / Function | Methods / Parameters | Description |
|------------------|----------------------|-------------|
| `WatcherEventHandler` | `on_created`, `on_modified`, `on_moved` | Subclasses watchdog's `FileSystemEventHandler`. Captures file creations, writes, and renames (`.crdownload` -> final) in Downloads root. |
| `BackgroundAgent` | `__init__(config, organizer, on_item_updated, on_file_organized, on_status_changed)` | Initializes watchdog observer, thread-safe queue, and health state trackers. |
| `BackgroundAgent.start` | `() -> None` | Starts background observer, launches worker consumer thread, and triggers startup reconciliation. |
| `BackgroundAgent.stop` | `() -> None` | Gracefully drains queues, sets termination flags, and stops watchdog observer thread. |
| `BackgroundAgent.pause` / `resume` | `() -> None` | Suspends or resumes automatic organization while keeping the watcher active. |
| `BackgroundAgent.enqueue_event` | `(path_str: str, event_type: str) -> None` | Ignores category subdirectories and hidden files; tracks debounce timestamps to prevent redundant runs. |
| `BackgroundAgent._worker_loop` | `() -> None` | Dedicated daemon thread consuming items from `_work_queue`. |
| `BackgroundAgent._handle_file_event` | `(path_str: str) -> None` | Manages download stabilization, review mode interception, and calls organizer. |
| `BackgroundAgent._stabilize_file` | `(path: Path, max_wait: float = 60.0) -> bool` | Samples file size across intervals and tests Windows lock accessibility before permitting movement. |
| `BackgroundAgent.manual_check_downloads` | `() -> Dict[str, Any]` | "Scan Now" workflow that inspects unorganized root files on demand and returns counts/sizes. |
| `BackgroundAgent.organize_manual_items` | `(items: List[PendingItem]) -> List[OrganizerResult]` | Organizes a specified batch of scanned items. |
| `BackgroundAgent.get_diagnostics` | `() -> Dict[str, Any]` | Returns live health telemetry: watcher status, agent status, restart counts, queue length, and last errors. |
| `BackgroundAgent.create_background_test_file` | `() -> Tuple[Path, str]` | Generates a sample test file in Downloads to verify real-time monitoring end-to-end. |
| `BackgroundAgent.get_waiting_items` | `() -> List[PendingItem]` | Returns pending items waiting for user approval in Review Mode. |
| `BackgroundAgent.process_review_item` | `(item: PendingItem, approved: bool, target_category: Optional[str] = None)` | Approves, redirects, or skips a file held in review. |

---

### 3. `app/classifier.py`
Zero-AI, 100% deterministic 5-tier classification engine.

| Class / Function | Signature | Description |
|------------------|-----------|-------------|
| `is_whatsapp_file` | `(filename: str) -> bool` | Regex-evaluates filename for WhatsApp conventions (`IMG-YYYYMMDD-WA*`, `VID-`, `AUD-`, `DOC-`, `PTT-`, or `wa_` prefixes). |
| `Classifier.__init__` | `(rule_engine: Optional[RuleEngine] = None, db_instance=None)` | Initializes rule engine and SQLite references. |
| `Classifier.classify` | `(file_path: str \| Path, file_size: int = 0, mtime: Optional[float] = None, custom_rules: Optional[List[Dict[str, Any]]] = None) -> ClassificationResult` | Implements strict 5-tier classification: (1) WhatsApp patterns, (2) User custom rules, (3) Keyword matching, (4) Extension mappings, (5) Others fallback. |
| `Classifier._check_db_category_extensions` | `(ext: str) -> Optional[str]` | Checks user-defined extension mappings assigned to categories in SQLite. |

---

### 4. `app/rules.py`
Compound condition evaluator supporting AND / OR operators, size thresholds, and dates.

| Class / Function | Signature | Description |
|------------------|-----------|-------------|
| `parse_size_string` | `(val: str) -> int` | Parses size strings (e.g. `'10MB'`, `'500KB'`, `'2GB'`) into exact bytes. |
| `RuleCondition.evaluate` | `(filename: str, extension: str, file_size: int, mtime: Optional[float] = None) -> Tuple[bool, str]` | Tests a condition (`extension_is`, `filename_contains`, `filename_starts_with`, `filename_ends_with`, `filesize_gt`, `filesize_lt`, `date_is`) against file metadata. |
| `RuleEngine.__init__` | `(db_instance=None)` | Instantiates engine with optional database connection. |
| `RuleEngine.evaluate` | `(filename: str, extension: str, file_size: int, mtime: Optional[float] = None, custom_rules: Optional[List[Dict[str, Any]]] = None) -> Optional[RuleMatchResult]` | Evaluates rules ordered by descending priority, parsing compound conditions with `AND`/`OR` logic. |

---

### 5. `app/organizer.py`
File movement engine enforcing zero deletion, zero overwrite, and metadata preservation.

| Class / Function | Signature | Description |
|------------------|-----------|-------------|
| `SafeOrganizer.__init__` | `(db: Database, classifier: Classifier, base_downloads_folder: str)` | Initializes organizer with DB, classifier, and base directory. |
| `SafeOrganizer.set_base_folder` | `(new_folder: str) -> None` | Updates the active base Downloads directory. |
| `SafeOrganizer.organize_file` | `(file_path: str \| Path, custom_category: Optional[str] = None, custom_reason: Optional[str] = None) -> OrganizerResult` | Validates file existence, verifies path is in root, checks file lock, classifies, verifies path traversal safety, creates destination folder on-demand, generates unique non-conflicting filename, executes `shutil.move`, records to SQLite history, and returns `OrganizerResult`. |

---

### 6. `app/history.py`
Reversible movement audit trail and 1-click batch undo manager.

| Class / Function | Signature | Description |
|------------------|-----------|-------------|
| `HistoryManager.__init__` | `(db: Database)` | Initializes history manager with database access. |
| `HistoryManager.undo_move` | `(history_id: int) -> Tuple[bool, str]` | Reverts a single file movement back to its original path without overwriting; marks status as `undone`. |
| `HistoryManager.undo_last_move` | `() -> Tuple[bool, str]` | Reverts the single latest successful movement. |
| `HistoryManager.undo_last_batch` | `() -> Tuple[int, str]` | Identifies all files moved within the latest 60-second batch window and restores them all safely. |
| `HistoryManager.get_recent_activity` | `(limit: int = 10) -> List[Dict[str, Any]]` | Retrieves most recent movement events. |
| `HistoryManager.get_recent_organized` | `(limit: int = 200) -> Dict[str, List[Dict[str, Any]]]` | Groups organized files chronologically by date for GUI display. |
| `HistoryManager.get_all_history` | `(limit: int = 200, status_filter: Optional[str] = None) -> List[Dict[str, Any]]` | Returns full movement history with optional status filter. |
| `HistoryManager.search` | `(query: str = "", category: Optional[str] = None, extension: Optional[str] = None, date_str: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]` | High-performance search across SQLite history. |

---

### 7. `app/database.py`
SQLite persistence layer with Write-Ahead Logging (WAL) mode for concurrency.

| Class / Function | Signature | Description |
|------------------|-----------|-------------|
| `Database.__init__` | `(db_path: Optional[Path] = None)` | Initializes database path (`%APPDATA%\Sorty\history.db`) and creates tables. |
| `Database._get_connection` | `() -> sqlite3.Connection` | Opens connection with `PRAGMA journal_mode = WAL` and `PRAGMA synchronous = NORMAL`. |
| `Database._init_db` | `() -> None` | Creates `history`, `rules`, and `categories` tables and their respective indexes. |
| `Database._seed_default_categories` | `(conn: sqlite3.Connection) -> None` | Seeds initial 18 categories and extension mappings. |
| `Database._seed_default_rules` | `(conn: sqlite3.Connection) -> None` | Seeds starter rules for WhatsApp, Resumes, etc. |
| `Database.insert_history` | `(...) -> int` | Inserts an audit record and returns auto-incremented record ID. |
| `Database.update_history_status` | `(history_id: int, status: str) -> bool` | Updates movement status (`success`, `failed`, `skipped`, `undone`). |
| `Database.get_history_by_id` | `(history_id: int) -> Optional[Dict[str, Any]]` | Retrieves a specific history record by ID. |
| `Database.get_history` | `(limit: int = 100, offset: int = 0, status_filter: Optional[str] = None) -> List[Dict[str, Any]]` | Paginated retrieval of history logs. |
| `Database.get_recent_activity` | `(limit: int = 10) -> List[Dict[str, Any]]` | Returns recent successful movements. |
| `Database.get_recent_organized` | `(limit: int = 200) -> Dict[str, List[Dict[str, Any]]]` | Returns movements grouped by human-readable time labels. |
| `Database.search_history` | `(query: str = "", category: Optional[str] = None, extension: Optional[str] = None, date_str: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]` | Multi-filter query across history records. |
| `Database.get_stats` | `() -> Dict[str, Any]` | Aggregates total files sorted, total bytes moved, category distributions, and daily counts. |
| `Database.clean_old_history` | `(retention: str) -> int` | Prunes records older than specified retention (`30_days`, `90_days`, `1_year`). |
| `Database.get_rules` | `(enabled_only: bool = False) -> List[Dict[str, Any]]` | Retrieves custom rules ordered by priority descending. |
| `Database.add_rule` / `update_rule` / `delete_rule` | `(...)` | Full CRUD operations for user custom rules. |
| `Database.set_rule_priority` | `(rule_id: int, new_priority: int) -> bool` | Updates execution priority for a rule. |
| `Database.get_categories` | `() -> List[Dict[str, Any]]` | Lists all categories and associated file extensions. |
| `Database.add_category` / `update_category` / `delete_category` | `(...)` | Full CRUD operations for category management. |

---

### 8. `app/config.py`
User preferences, Windows Shell path resolvers, and JSON persistence.

| Class / Function | Signature | Description |
|------------------|-----------|-------------|
| `get_default_downloads_folder` | `() -> str` | Queries dedicated drives (e.g. `D:\downloads`), then Windows Shell API (`SHGetKnownFolderPath`), falling back to user home. |
| `get_app_data_dir` | `() -> Path` | Returns `%APPDATA%\Sorty`, with automated migration from legacy versions. |
| `get_logs_dir` | `() -> Path` | Returns `%APPDATA%\Sorty\logs`. |
| `get_db_path` | `() -> Path` | Returns `%APPDATA%\Sorty\history.db`. |
| `get_config_path` | `() -> Path` | Returns `%APPDATA%\Sorty\config.json`. |
| `ConfigManager.load` | `() -> Dict[str, Any]` | Reads configuration from disk with schema defaults. |
| `ConfigManager.save` | `() -> bool` | Atomically writes configuration to `.tmp` file and replaces destination. |
| `ConfigManager.get` / `set` / `update` | `(...)` | Property getters, setters, and bulk updates. |

---

### 9. `app/utils.py`
Filesystem utilities, collision name resolution, and Windows registry autostart.

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_windows_downloads_folder` | `() -> str` | Windows Shell API known folder resolver via `FOLDERID_Downloads` GUID. |
| `is_safe_path` | `(base_dir: str \| Path, target_path: str \| Path) -> bool` | Path traversal guard ensuring target resolves strictly inside base folder. |
| `get_unique_destination_path` | `(destination_dir: str \| Path, filename: str) -> Path` | Collision resolver preserving multi-part extensions (`file.tar (1).gz`). |
| `is_file_accessible` | `(file_path: str \| Path) -> bool` | Checks file availability by testing a read byte and in-place rename lock probe. |
| `format_size` | `(num_bytes: int) -> str` | Converts raw bytes to human-readable string (e.g. `2.4 MB`, `1.8 GB`). |
| `get_file_metadata` | `(file_path: str \| Path) -> Optional[Tuple[int, str, float]]` | Returns `(file_size, extension_with_dot, mtime)` safely. |
| `set_start_with_windows` | `(enable: bool, app_exe_or_script: Optional[str] = None) -> bool` | Updates `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` registry key. Zero admin rights required. |
| `is_start_with_windows_enabled` | `() -> bool` | Checks if Windows autostart registry entry is present. |
| `sync_recent_shortcuts` | `(...) -> Path` | Explicit no-op upholding zero-physical-shortcut architecture. |

---

### 10. `app/notifications.py`
Grouped, non-intrusive desktop notifications with auto-debouncing.

| Class / Function | Signature | Description |
|------------------|-----------|-------------|
| `NotificationManager.notify_organized` | `(filename: str, category: str) -> None` | Queues notification and arms a 1.5-second timer. |
| `NotificationManager._flush_notifications` | `() -> None` | Dispatches single file toast or aggregate summary (`Organized 5 files.`). |
| `NotificationManager.send_notification` | `(title: str, message: str) -> None` | Emits notification through system tray or PowerShell fallback. |
| `NotificationManager._show_windows_toast` | `(title: str, message: str) -> None` | Asynchronous PowerShell script displaying a Windows balloon tip. |

---

### 11. `app/tray.py`
System tray icon manager and background context menu.

| Class / Function | Signature | Description |
|------------------|-----------|-------------|
| `TrayManager.__init__` | `(...)` | Loads tray icon from assets and sets up event handlers. |
| `TrayManager.start` | `() -> None` | Starts pystray loop in a background daemon thread. |
| `TrayManager.update_menu` | `() -> None` | Refreshes menu state (dynamically updates Pause/Resume items). |
| `TrayManager.notify` | `(title: str, message: str) -> None` | Emits native tray balloon notification. |
| `TrayManager.stop` | `() -> None` | Removes system tray icon cleanly on exit. |

---

### 12. `app/ui.py`
Responsive, high-DPI Tkinter GUI control panel.

| Component / Page | Method | Description |
|------------------|--------|-------------|
| `DownloadOrganizerApp` | `__init__`, `run` | Builds main window, configures themes, and initializes navigation. |
| **Dashboard Page** | `_render_dashboard` | Displays live status, folder size metrics, 1-Click Instant Organize, 1-Click Undo, and recent files feed. |
| **Recent Files Page** | `_render_recent_page` | Chronological virtual view of all organized files with per-item undo actions. |
| **Downloads Explorer** | `_render_downloads_page` | Live inspection of unorganized root downloads with Review Mode batch approval. |
| **Rules Manager** | `_render_rules_page` | Visual CRUD manager for custom compound rules (conditions, priorities, logic operators). |
| **Categories Manager** | `_render_categories_page` | View and edit category folders, emojis, and assigned extension lists. |
| **History Page** | `_render_history_page` | Paginated, filterable audit log of every movement with individual rollback. |
| **Search Page** | `_render_search_page` | Instant full-text search across SQLite database by name, extension, date, and category. |
| **Settings Page** | `_render_settings_page` | Controls for downloads folder path, autostart, notifications, delay, retention, and diagnostics. |

---

## ⚡ 1-Click Instant Sort & CLI Usage

Organize your entire Downloads folder in seconds without opening the full UI:

- **Desktop Batch Shortcut**: Double-click [Organize Downloads Now.bat](file:///d:/sorty/sorty/Organize%20Downloads%20Now.bat).
- **GUI Dashboard**: Click the **⚡ Instant Organize (1-Click)** button on the dashboard header.
- **Command Line**:
  ```cmd
  python app/main.py --quick
  # Or with standalone executable:
  dist\Sorty.exe --quick
  ```

---

## ↩️ Reversible Undo System

Change your mind or need files back in root? Restore instantly:

- **Desktop Batch Shortcut**: Double-click [Undo Last Organization.bat](file:///d:/sorty/sorty/Undo%20Last%20Organization.bat) or [Undo.bat](file:///d:/sorty/sorty/Undo.bat).
- **GUI Dashboard**: Click **↩️ Undo Last Sort** on the dashboard.
- **System Tray**: Right-click Sorty in the system tray and select **Undo Last Organization**.
- **Command Line**:
  ```cmd
  python app/main.py --undo
  # Or with standalone executable:
  dist\Sorty.exe --undo
  ```

---

## 🚀 Installation & Setup

### Running from Source
1. Ensure Python 3.10+ is installed on Windows.
2. Clone or open the project directory:
   ```cmd
   cd d:\sorty\sorty
   ```
3. Run the automated starter batch file:
   ```cmd
   Start_Sorty.bat
   ```
   *(Automatically sets up a virtual environment, installs dependencies from `requirements.txt`, and launches Sorty).*

### Compiling Standalone Executable
To generate a single-file executable `dist/Sorty.exe`:
```cmd
build.bat
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
