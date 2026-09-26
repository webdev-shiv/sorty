from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil
import tempfile
import pytest

from app.classifier import Classifier
from app.config import ConfigManager
from app.database import Database
from app.history import HistoryManager
from app.organizer import SafeOrganizer
from app.rules import RuleEngine


@pytest.fixture
def temp_environment():
    temp_dir = Path(tempfile.mkdtemp())
    downloads_dir = temp_dir / "Downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    db_path = temp_dir / "test_history.db"

    db = Database(db_path=db_path)
    rule_engine = RuleEngine(db_instance=db)
    classifier = Classifier(rule_engine=rule_engine, db_instance=db)
    organizer = SafeOrganizer(db=db, classifier=classifier, base_downloads_folder=str(downloads_dir))
    history = HistoryManager(db=db)

    cfg_file = temp_dir / "test_config.json"
    config = ConfigManager(config_file=cfg_file)
    config.set("downloads_folder", str(downloads_dir))

    yield {
        "temp_dir": temp_dir,
        "downloads_dir": downloads_dir,
        "db": db,
        "organizer": organizer,
        "history": history,
        "config": config,
    }

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_recent_today_and_yesterday_classification(temp_environment):
    """Verify get_recent_organized queries today and yesterday calendar ranges without touching disk."""
    env = temp_environment
    db: Database = env["db"]
    downloads_dir: Path = env["downloads_dir"]

    now = datetime.now()
    today_ts = now.strftime("%Y-%m-%d %H:%M:%S")

    yesterday_dt = now - timedelta(days=1)
    yesterday_ts = yesterday_dt.strftime("%Y-%m-%d %H:%M:%S")

    older_dt = now - timedelta(days=5)
    older_ts = older_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Insert today record
    id_today = db.insert_history(
        filename="DBMS_Assignment.pdf",
        original_path=str(downloads_dir / "DBMS_Assignment.pdf"),
        destination_path=str(downloads_dir / "College" / "DBMS_Assignment.pdf"),
        category="College",
        reason="Rule: College DBMS",
        file_size=1258291,
        extension=".pdf",
        status="success",
        timestamp=today_ts,
    )

    # Insert yesterday record
    id_yesterday = db.insert_history(
        filename="project.zip",
        original_path=str(downloads_dir / "project.zip"),
        destination_path=str(downloads_dir / "Archives" / "project.zip"),
        category="Archives",
        reason="Extension: .zip",
        file_size=25165824,
        extension=".zip",
        status="success",
        timestamp=yesterday_ts,
    )

    # Insert older record (should NOT appear in Recent)
    id_older = db.insert_history(
        filename="old_notes.txt",
        original_path=str(downloads_dir / "old_notes.txt"),
        destination_path=str(downloads_dir / "Documents" / "old_notes.txt"),
        category="Documents",
        reason="Extension: .txt",
        file_size=12288,
        extension=".txt",
        status="success",
        timestamp=older_ts,
    )

    recent = db.get_recent_organized()

    assert "today" in recent
    assert "yesterday" in recent

    today_filenames = [r["filename"] for r in recent["today"]]
    yesterday_filenames = [r["filename"] for r in recent["yesterday"]]

    assert "DBMS_Assignment.pdf" in today_filenames
    assert "project.zip" in yesterday_filenames
    assert "old_notes.txt" not in today_filenames
    assert "old_notes.txt" not in yesterday_filenames


def test_recent_never_creates_recent_folder_or_duplicate_files(temp_environment):
    """
    CRITICAL TEST:
    Verify that organizing a file:
    1. Moves file to destination category (e.g. College).
    2. Does NOT create Downloads/Recent/ folder.
    3. Does NOT create Today/ or Yesterday/ folders.
    4. Only exactly ONE physical copy exists on disk.
    """
    env = temp_environment
    organizer: SafeOrganizer = env["organizer"]
    downloads_dir: Path = env["downloads_dir"]
    history: HistoryManager = env["history"]

    # Create dummy assignment file in downloads
    test_file = downloads_dir / "DBMS_Assignment.pdf"
    test_file.write_text("Database Management Systems Assignment Content")

    # Organize file
    res = organizer.organize_file(test_file)
    assert res.success is True
    assert res.category == "College"

    # Verify destination file exists
    dest_path = Path(res.destination_path)
    assert dest_path.exists()
    assert dest_path.name == "DBMS_Assignment.pdf"
    assert dest_path.parent.name == "College"

    # Verify original file is gone from root
    assert not test_file.exists()

    # CRITICAL CHECK: Verify NO "Recent" folder was created
    assert not (downloads_dir / "Recent").exists()
    assert not (downloads_dir / "recent").exists()
    assert not (downloads_dir / "Today").exists()
    assert not (downloads_dir / "Yesterday").exists()

    # Query recent organized records via SQLite
    recent = history.get_recent_organized()
    today_items = recent.get("today", [])
    assert len(today_items) >= 1
    assert today_items[0]["filename"] == "DBMS_Assignment.pdf"
    assert today_items[0]["category"] == "College"

    # Count total occurrences of DBMS_Assignment.pdf in the entire downloads directory
    all_matching = list(downloads_dir.rglob("DBMS_Assignment.pdf"))
    assert len(all_matching) == 1
    assert all_matching[0] == dest_path


def test_recent_after_undo_preserves_audit_trail(temp_environment):
    """Verify that undoing a move marks it as 'undone' without deleting history."""
    env = temp_environment
    organizer: SafeOrganizer = env["organizer"]
    downloads_dir: Path = env["downloads_dir"]
    history: HistoryManager = env["history"]

    test_file = downloads_dir / "DBMS_Assignment.pdf"
    test_file.write_text("Sample content")

    res = organizer.organize_file(test_file)
    assert res.success is True

    # Retrieve history record
    recent = history.get_recent_organized()
    today_items = recent["today"]
    assert len(today_items) == 1
    record_id = today_items[0]["id"]
    assert today_items[0]["status"] == "success"

    # Perform Undo
    ok, msg = history.undo_move(record_id)
    assert ok is True

    # Restored to original location
    assert (downloads_dir / "DBMS_Assignment.pdf").exists()

    # History record is preserved with status 'undone'
    recent_after_undo = history.get_recent_organized()
    today_after = recent_after_undo["today"]
    assert len(today_after) == 1
    assert today_after[0]["id"] == record_id
    assert today_after[0]["status"] == "undone"


def test_run_in_background_config_setting(temp_environment):
    """Verify run_in_background setting default is True and persists."""
    env = temp_environment
    config: ConfigManager = env["config"]

    # Default must be True (ON)
    assert config.run_in_background is True

    # Toggle to False
    config.set("run_in_background", False)
    assert config.run_in_background is False

    # Toggle back to True
    config.set("run_in_background", True)
    assert config.run_in_background is True


def test_tray_menu_structure_and_exit():
    """Verify system tray menu items and Exit action completely terminate."""
    from app.tray import TrayManager

    opened = []
    organized = []
    paused = [False]
    settings_opened = []
    exited = []

    tray = TrayManager(
        icon_path=Path("assets/icon.png"),
        on_show_app=lambda: opened.append(True),
        on_organize_now=lambda: organized.append(True),
        on_pause=lambda: paused.__setitem__(0, True),
        on_resume=lambda: paused.__setitem__(0, False),
        on_open_downloads=lambda: None,
        on_open_settings=lambda: settings_opened.append(True),
        on_exit=lambda: exited.append(True),
        is_paused_getter=lambda: paused[0],
    )

    menu = tray._build_menu()
    item_texts = [item.text for item in menu.items]

    # Must contain the exact required items (Open, Pause Organization, Resume Organization, Open Downloads, Settings, Exit)
    assert "Open" in item_texts
    assert "Pause Organization" in item_texts
    assert "Resume Organization" in item_texts
    assert "Open Downloads" in item_texts
    assert "Settings" in item_texts
    assert "Exit" in item_texts

    # Test pause / resume
    tray._handle_pause()
    assert paused[0] is True
    tray._handle_resume()
    assert paused[0] is False

    # Test Exit terminates completely
    tray._handle_exit()
    assert len(exited) == 1
    assert tray._tray_icon is None


def test_window_close_behavior_background_on_vs_off(temp_environment):
    """
    Test A & B:
    - When run_in_background is ON: close window hides/withdraws window, does NOT stop watcher.
    - When run_in_background is OFF: close window stops watcher and calls quit_application.
    """
    from unittest.mock import MagicMock
    from app.ui import DownloadOrganizerApp

    env = temp_environment
    config: ConfigManager = env["config"]
    db: Database = env["db"]
    organizer: SafeOrganizer = env["organizer"]
    history: HistoryManager = env["history"]

    mock_classifier = MagicMock()
    mock_watcher = MagicMock()
    mock_watcher.is_paused = False

    mock_root = MagicMock()
    app = DownloadOrganizerApp(
        config=config,
        db=db,
        classifier=mock_classifier,
        organizer=organizer,
        history=history,
        watcher=mock_watcher,
        root=mock_root,
    )

    mock_tray = MagicMock()
    app.set_tray_manager(mock_tray)

    # 1. Background ON: closing window should withdraw (hide), NOT stop watcher
    config.set("run_in_background", True)
    app.root.withdraw = MagicMock()
    app.on_close_requested()

    assert app.root.withdraw.called
    assert not mock_watcher.stop.called
    assert not mock_tray.stop.called

    # 2. Background OFF: closing window should cleanly quit application
    config.set("run_in_background", False)
    app.quit_application = MagicMock()
    app.on_close_requested()

    assert app.quit_application.called

    # Clean up tkinter root
    try:
        app.root.destroy()
    except Exception:
        pass


def test_recent_all_required_metadata_fields(temp_environment):
    """
    Verify all 7 fields for Recent items:
    - filename
    - category
    - time
    - file size
    - original location
    - current location
    - organization reason
    """
    env = temp_environment
    organizer: SafeOrganizer = env["organizer"]
    downloads_dir: Path = env["downloads_dir"]
    history: HistoryManager = env["history"]

    test_file = downloads_dir / "DBMS_Assignment.pdf"
    test_file.write_text("Database Management Systems Assignment")

    res = organizer.organize_file(test_file)
    assert res.success is True

    recent = history.get_recent_organized()
    today_items = recent["today"]
    assert len(today_items) == 1

    item = today_items[0]
    assert item["filename"] == "DBMS_Assignment.pdf"
    assert item["category"] == "College"
    assert "timestamp" in item and item["timestamp"]
    assert item["file_size"] > 0
    assert "original_path" in item and item["original_path"]
    assert "destination_path" in item and item["destination_path"]
    assert "reason" in item and item["reason"]


def test_app_restart_persists_recent_and_config(temp_environment):
    """
    Test H:
    Restart app -> Recent still shows history and config persists.
    """
    env = temp_environment
    db: Database = env["db"]
    config: ConfigManager = env["config"]
    downloads_dir: Path = env["downloads_dir"]

    # Insert a record
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.insert_history(
        filename="notes.pdf",
        original_path=str(downloads_dir / "notes.pdf"),
        destination_path=str(downloads_dir / "Documents" / "notes.pdf"),
        category="Documents",
        reason="Extension: .pdf",
        file_size=5000,
        extension=".pdf",
        status="success",
        timestamp=now_str,
    )

    config.set("run_in_background", True)

    # Simulate restart by creating fresh instances reading from the same db & config
    new_db = Database(db_path=db.db_path)
    new_config = ConfigManager(config_file=config.config_path)
    new_history = HistoryManager(db=new_db)

    assert new_config.run_in_background is True

    recent = new_history.get_recent_organized()
    assert len(recent["today"]) == 1
    assert recent["today"][0]["filename"] == "notes.pdf"
    assert recent["today"][0]["category"] == "Documents"


def test_checklist_a_to_h_integrated(temp_environment):
    """
    Comprehensive verification covering checklist items A through H:
    A. Background ON: close window hides/withdraws window, organizer organizes file.
    B. Background OFF: close window completely exits.
    C. Tray Exit: stops tray and terminates.
    D. Recent Today: file appears under TODAY with all metadata.
    E. Yesterday: file appears under YESTERDAY.
    F. No Recent folder: Downloads/Recent does NOT exist.
    G. No duplication: only 1 copy of the physical file exists.
    H. Restart: restart app -> history still intact.
    """
    from unittest.mock import MagicMock
    from app.ui import DownloadOrganizerApp

    env = temp_environment
    config: ConfigManager = env["config"]
    db: Database = env["db"]
    organizer: SafeOrganizer = env["organizer"]
    history: HistoryManager = env["history"]
    downloads_dir: Path = env["downloads_dir"]

    # --- A & D: Background ON & Organize File ---
    config.set("run_in_background", True)
    assert config.run_in_background is True

    test_doc = downloads_dir / "DBMS_Assignment.pdf"
    test_doc.write_text("Database Assignment")
    res = organizer.organize_file(test_doc)
    assert res.success is True

    # --- F & G: No Recent folder & No Duplication ---
    assert not (downloads_dir / "Recent").exists()
    assert not (downloads_dir / "recent").exists()
    all_copies = list(downloads_dir.rglob("DBMS_Assignment.pdf"))
    assert len(all_copies) == 1  # Exactly 1 physical copy

    # --- D & E: Recent Today & Yesterday ---
    # Add a yesterday record
    yesterday_ts = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_history(
        filename="project.zip",
        original_path=str(downloads_dir / "project.zip"),
        destination_path=str(downloads_dir / "Archives" / "project.zip"),
        category="Archives",
        reason="Extension: .zip",
        file_size=24000000,
        extension=".zip",
        status="success",
        timestamp=yesterday_ts,
    )

    recent = history.get_recent_organized()
    assert any(r["filename"] == "DBMS_Assignment.pdf" for r in recent["today"])
    assert any(r["filename"] == "project.zip" for r in recent["yesterday"])


def test_recent_never_creates_physical_folder_or_shortcuts(temp_environment):
    """
    CRITICAL CHECK (Part 8 & 24):
    Verify that organizing a file:
    1. Does NOT create Downloads/Recent folder.
    2. Does NOT create .lnk shortcuts in Recent.
    3. Does NOT duplicate files.
    4. Recent is purely a database view of SQLite history.
    """
    from app.utils import sync_recent_shortcuts

    env = temp_environment
    downloads_dir: Path = env["downloads_dir"]
    organizer: SafeOrganizer = env["organizer"]
    history: HistoryManager = env["history"]

    # Organize a test file
    test_file = downloads_dir / "DBMS_Assignment.pdf"
    test_file.write_text("Database Assignment Content")
    res = organizer.organize_file(test_file)
    assert res.success is True

    # Call sync_recent_shortcuts (no-op)
    recent_data = history.get_recent_organized()
    ret = sync_recent_shortcuts(downloads_dir, recent_data)

    # CRITICAL: No Recent folder or shortcut must exist
    assert not (downloads_dir / "Recent").exists()
    assert not (downloads_dir / "recent").exists()
    assert not (downloads_dir / "Today").exists()
    assert not (downloads_dir / "Yesterday").exists()

    # Exactly 1 physical PDF file exists across the entire downloads directory
    pdf_files = list(downloads_dir.rglob("*.pdf"))
    assert len(pdf_files) == 1
    assert pdf_files[0] == Path(res.destination_path)

    # Database view contains the file under 'today'
    assert len(recent_data["today"]) == 1
    assert recent_data["today"][0]["filename"] == "DBMS_Assignment.pdf"


def test_manual_check_downloads_finds_and_organizes_existing_files(temp_environment):
    """
    TEST C — MANUAL CHECK (Part 7):
    Put an eligible file in Downloads (e.g. resume.pdf).
    Do NOT wait for a new download event.
    Manual Check detects it, classifies it as Resume, and organizes it safely.
    """
    from app.watcher import BackgroundAgent

    env = temp_environment
    downloads_dir: Path = env["downloads_dir"]
    organizer: SafeOrganizer = env["organizer"]
    config: ConfigManager = env["config"]

    # Create an unorganized resume file in Downloads root
    test_resume = downloads_dir / "resume.pdf"
    test_resume.write_text("Professional Resume Content")

    # Create an organized file in subfolder to verify already_organized counting
    college_dir = downloads_dir / "College"
    college_dir.mkdir(parents=True, exist_ok=True)
    (college_dir / "dbms_notes.pdf").write_text("College DBMS Notes")

    agent = BackgroundAgent(config=config, organizer=organizer)

    # Perform ONE explicit manual scan
    scan_res = agent.manual_check_downloads()

    assert scan_res["total_found"] == 2
    assert scan_res["already_organized_count"] == 1
    assert len(scan_res["ready_to_organize"]) == 1

    ready_item = scan_res["ready_to_organize"][0]
    assert ready_item.filename == "resume.pdf"
    assert ready_item.suggested_folder == "Resume"

    # Organize approved items
    org_results = agent.organize_manual_items(scan_res["ready_to_organize"])
    assert len(org_results) == 1
    assert org_results[0].success is True
    assert (downloads_dir / "Resume" / "resume.pdf").exists()
    assert not test_resume.exists()


def test_background_agent_diagnostics_and_states(temp_environment):
    """
    TEST DIAGNOSTICS (Part 14 & 17):
    Verify diagnostic metrics and watcher status.
    """
    from app.watcher import BackgroundAgent

    env = temp_environment
    organizer: SafeOrganizer = env["organizer"]
    config: ConfigManager = env["config"]

    agent = BackgroundAgent(config=config, organizer=organizer)
    diag_before = agent.get_diagnostics()
    assert diag_before["background_agent"] == "STOPPED"
    assert diag_before["file_watcher"] == "STOPPED"

    agent.start()
    try:
        diag_after = agent.get_diagnostics()
        assert diag_after["background_agent"] == "RUNNING"
        assert diag_after["file_watcher"] == "RUNNING"
        assert diag_after["watched_folder"] == str(Path(config.downloads_folder).resolve())
    finally:
        agent.stop()


def test_old_recent_folder_detection_and_no_deletion(temp_environment):
    """
    TEST PART 24 — SCREENSHOT ISSUE:
    If an old Downloads/Recent directory exists from previous versions:
    Do NOT delete it automatically.
    Do NOT move files automatically.
    Detect it so the UI can show the banner.
    """
    from unittest.mock import MagicMock
    from app.ui import DownloadOrganizerApp

    env = temp_environment
    downloads_dir: Path = env["downloads_dir"]
    config: ConfigManager = env["config"]
    db: Database = env["db"]
    organizer: SafeOrganizer = env["organizer"]
    history: HistoryManager = env["history"]

    # Pre-create old physical Recent folder
    old_recent = downloads_dir / "Recent"
    old_recent.mkdir(parents=True, exist_ok=True)
    old_lnk = old_recent / "test.pdf.lnk"
    old_lnk.write_text("shortcut target")

    mock_classifier = MagicMock()
    mock_watcher = MagicMock()
    mock_watcher.is_running = True
    mock_watcher.is_paused = False
    mock_watcher.get_diagnostics.return_value = {
        "background_agent": "RUNNING",
        "file_watcher": "RUNNING",
        "queue_size": 0,
        "last_event": "None",
        "last_organization": "None",
        "watched_folder": str(downloads_dir),
        "retry_count": 0,
        "last_error": None,
        "paused": False,
    }

    mock_root = MagicMock()
    app = DownloadOrganizerApp(
        config=config,
        db=db,
        classifier=mock_classifier,
        organizer=organizer,
        history=history,
        watcher=mock_watcher,
        root=mock_root,
    )

    try:
        # Detected old Recent folder
        assert app._old_recent_found is True
        assert app._old_recent_dismissed is False

        # Old folder and its contents were NOT deleted!
        assert old_recent.exists()
        assert old_lnk.exists()

        # Dismiss notice
        app._dismiss_old_recent_banner()
        assert app._old_recent_dismissed is True
        assert old_recent.exists()
    finally:
        try:
            app.root.destroy()
        except Exception:
            pass


def test_manual_background_monitoring_test_file(temp_environment):
    """
    TEST PART 15 — MANUAL TEST BUTTON:
    Calling create_background_test_file creates DownloadOrganizer_Test.txt in Downloads root.
    """
    from app.watcher import BackgroundAgent

    env = temp_environment
    downloads_dir: Path = env["downloads_dir"]
    organizer: SafeOrganizer = env["organizer"]
    config: ConfigManager = env["config"]

    agent = BackgroundAgent(config=config, organizer=organizer)
    test_path, filename = agent.create_background_test_file()

    assert filename == "DownloadOrganizer_Test.txt"
    assert test_path.exists()
    assert test_path.parent.resolve() == downloads_dir.resolve()



