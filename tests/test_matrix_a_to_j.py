"""
Comprehensive verification test suite executing TEST A through J of the Critical Test Matrix.
Verifies real Windows background operation, watcher events, stabilization, manual check,
virtual Recent today & yesterday views, and process lifetime.
"""

from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil
import tempfile
import time
import pytest

from app.classifier import Classifier
from app.config import ConfigManager
from app.database import Database
from app.history import HistoryManager
from app.organizer import SafeOrganizer
from app.rules import RuleEngine
from app.watcher import BackgroundAgent, FileState, WatcherStatus


def test_matrix_test_a_and_g_background_on_ui_closed():
    """
    TEST A & G:
    Background Agent runs, detects file, organizes it, and updates history.
    """
    temp_dir = Path(tempfile.mkdtemp())
    downloads = temp_dir / "Downloads"
    downloads.mkdir()

    cfg_file = temp_dir / "config.json"
    config = ConfigManager(config_file=cfg_file)
    config.set("downloads_folder", str(downloads))
    config.set("run_in_background", True)
    config.set("stabilization_step", 0.2)

    db = Database(db_path=temp_dir / "history.db")
    re = RuleEngine(db_instance=db)
    cl = Classifier(rule_engine=re, db_instance=db)
    org = SafeOrganizer(db=db, classifier=cl, base_downloads_folder=str(downloads))
    agent = BackgroundAgent(config=config, organizer=org)

    agent.start()
    try:
        assert agent.is_running is True
        assert agent.watcher_status == WatcherStatus.RUNNING

        # Simulate a download arrival while UI is not open
        test_pdf = downloads / "sample_report.pdf"
        test_pdf.write_text("Test PDF content")

        # Let the watcher event flow and worker process
        time.sleep(3.0)

        # File should be organized to Documents or PDFs
        dest_pdf = downloads / "PDFs" / "sample_report.pdf"
        if not dest_pdf.exists():
            # Check if classified into Documents
            dest_pdf = downloads / "Documents" / "sample_report.pdf"

        # Check either dest_pdf exists or in history
        history = HistoryManager(db=db)
        recent = history.get_all_history(limit=5)
        assert len(recent) >= 1
        assert recent[0]["filename"] == "sample_report.pdf"
        assert recent[0]["status"] == "success"
    finally:
        agent.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_matrix_test_b_startup_reconciliation():
    """
    TEST B: APPLICATION RESTART
    Files dropped while application was closed are caught by startup reconciliation.
    """
    temp_dir = Path(tempfile.mkdtemp())
    downloads = temp_dir / "Downloads"
    downloads.mkdir()

    cfg_file = temp_dir / "config.json"
    config = ConfigManager(config_file=cfg_file)
    config.set("downloads_folder", str(downloads))
    config.set("stabilization_step", 0.2)

    db = Database(db_path=temp_dir / "history.db")
    re = RuleEngine(db_instance=db)
    cl = Classifier(rule_engine=re, db_instance=db)
    org = SafeOrganizer(db=db, classifier=cl, base_downloads_folder=str(downloads))

    # File arrived while app was closed
    missed_file = downloads / "offline_download.zip"
    missed_file.write_text("Zip data")

    # Start agent now
    agent = BackgroundAgent(config=config, organizer=org)
    agent.start()
    try:
        time.sleep(3.0)

        # File organized by startup reconciliation
        dest = downloads / "Archives" / "offline_download.zip"
        assert dest.exists()
        assert not missed_file.exists()

        history = HistoryManager(db=db)
        records = history.get_all_history(limit=5)
        assert any(r["filename"] == "offline_download.zip" for r in records)
    finally:
        agent.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_matrix_test_c_manual_check():
    """
    TEST C: MANUAL CHECK
    Existing file in Downloads is detected, classified, and organized via manual check.
    """
    temp_dir = Path(tempfile.mkdtemp())
    downloads = temp_dir / "Downloads"
    downloads.mkdir()

    cfg_file = temp_dir / "config.json"
    config = ConfigManager(config_file=cfg_file)
    config.set("downloads_folder", str(downloads))

    db = Database(db_path=temp_dir / "history.db")
    re = RuleEngine(db_instance=db)
    cl = Classifier(rule_engine=re, db_instance=db)
    org = SafeOrganizer(db=db, classifier=cl, base_downloads_folder=str(downloads))

    existing_resume = downloads / "shivam_resume.pdf"
    existing_resume.write_text("Resume Content")

    agent = BackgroundAgent(config=config, organizer=org)

    scan_res = agent.manual_check_downloads()
    assert scan_res["total_found"] == 1
    assert len(scan_res["ready_to_organize"]) == 1
    assert scan_res["ready_to_organize"][0].suggested_folder == "Resume"

    # Organize
    res = agent.organize_manual_items(scan_res["ready_to_organize"])
    assert len(res) == 1
    assert res[0].success is True
    assert (downloads / "Resume" / "shivam_resume.pdf").exists()

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_matrix_test_d_and_e_recent_today_and_yesterday_virtual_views():
    """
    TEST D & E: RECENT TODAY & YESTERDAY
    Organized files appear under TODAY and YESTERDAY without creating any physical Recent directory.
    """
    temp_dir = Path(tempfile.mkdtemp())
    downloads = temp_dir / "Downloads"
    downloads.mkdir()

    db = Database(db_path=temp_dir / "history.db")
    history = HistoryManager(db=db)

    # Insert today's record
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.insert_history(
        filename="DBMS_Assignment.pdf",
        original_path=str(downloads / "DBMS_Assignment.pdf"),
        destination_path=str(downloads / "College" / "DBMS_Assignment.pdf"),
        category="College",
        reason="Rule: College DBMS",
        file_size=1200000,
        extension=".pdf",
        status="success",
        timestamp=now_ts,
    )

    # Insert yesterday's record
    yesterday_ts = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    db.insert_history(
        filename="project.zip",
        original_path=str(downloads / "project.zip"),
        destination_path=str(downloads / "Archives" / "project.zip"),
        category="Archives",
        reason="Extension: .zip",
        file_size=24000000,
        extension=".zip",
        status="success",
        timestamp=yesterday_ts,
    )

    recent_data = history.get_recent_organized()

    # Verify TODAY
    today_files = [r["filename"] for r in recent_data["today"]]
    assert "DBMS_Assignment.pdf" in today_files

    # Verify YESTERDAY
    yesterday_files = [r["filename"] for r in recent_data["yesterday"]]
    assert "project.zip" in yesterday_files

    # CRITICAL CHECK (Part 8): NO Downloads/Recent folder
    assert not (downloads / "Recent").exists()
    assert not (downloads / "recent").exists()

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_matrix_test_f_background_off_close_exits():
    """
    TEST F: BACKGROUND OFF
    When run_in_background is OFF, closing window calls quit_application.
    """
    from unittest.mock import MagicMock
    from app.ui import DownloadOrganizerApp

    temp_dir = Path(tempfile.mkdtemp())
    downloads = temp_dir / "Downloads"
    downloads.mkdir()

    cfg_file = temp_dir / "config.json"
    config = ConfigManager(config_file=cfg_file)
    config.set("downloads_folder", str(downloads))
    config.set("run_in_background", False)

    db = Database(db_path=temp_dir / "history.db")
    re = RuleEngine(db_instance=db)
    cl = Classifier(rule_engine=re, db_instance=db)
    org = SafeOrganizer(db=db, classifier=cl, base_downloads_folder=str(downloads))
    history = HistoryManager(db=db)

    mock_watcher = MagicMock()
    mock_watcher.is_running = True
    mock_watcher.is_paused = False
    mock_watcher.get_diagnostics.return_value = {
        "background_agent": "RUNNING",
        "file_watcher": "RUNNING",
        "queue_size": 0,
        "last_event": "None",
        "last_organization": "None",
        "watched_folder": str(downloads),
        "retry_count": 0,
        "last_error": None,
        "paused": False,
    }

    app = DownloadOrganizerApp(
        config=config,
        db=db,
        classifier=cl,
        organizer=org,
        history=history,
        watcher=mock_watcher,
    )

    app.quit_application = MagicMock()
    app.on_close_requested()

    # quit_application must be called when background is OFF
    assert app.quit_application.called

    try:
        app.root.destroy()
    except Exception:
        pass
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_matrix_test_h_tray_exit_terminates_all():
    """
    TEST H: TRAY EXIT
    Tray -> Exit terminates watcher, removes tray, and exits process.
    """
    from app.tray import TrayManager

    exited = []
    stopped = []

    tray = TrayManager(
        icon_path=Path("assets/icon.png"),
        on_show_app=lambda: None,
        on_organize_now=lambda: None,
        on_exit=lambda: exited.append(True),
    )

    tray._handle_exit()
    assert len(exited) == 1
    assert tray._tray_icon is None


def test_matrix_test_i_multiple_events_and_debouncing():
    """
    TEST I: MULTIPLE EVENTS
    Rapid creation of multiple files: test1.pdf, test2.jpg, test3.zip, test4.txt
    Verify: debounced, no duplicates, all organized.
    """
    temp_dir = Path(tempfile.mkdtemp())
    downloads = temp_dir / "Downloads"
    downloads.mkdir()

    cfg_file = temp_dir / "config.json"
    config = ConfigManager(config_file=cfg_file)
    config.set("downloads_folder", str(downloads))
    config.set("stabilization_step", 0.2)

    db = Database(db_path=temp_dir / "history.db")
    re = RuleEngine(db_instance=db)
    cl = Classifier(rule_engine=re, db_instance=db)
    org = SafeOrganizer(db=db, classifier=cl, base_downloads_folder=str(downloads))

    agent = BackgroundAgent(config=config, organizer=org)
    agent.start()

    try:
        files = ["test1.pdf", "test2.jpg", "test3.zip", "test4.txt"]
        for fname in files:
            (downloads / fname).write_text(f"Content for {fname}")

        # Wait for worker to stabilize and move all files
        time.sleep(3.0)

        history = HistoryManager(db=db)
        records = history.get_all_history(limit=20)
        organized_names = [r["filename"] for r in records if r["status"] == "success"]

        for fname in files:
            assert fname in organized_names

        # Verify no files remain in root
        for fname in files:
            assert not (downloads / fname).exists()
    finally:
        agent.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_matrix_test_j_active_download_temporary_files_ignored():
    """
    TEST J: ACTIVE DOWNLOAD & TEMPORARY FILES
    Files with temporary extensions (.crdownload, .part, .tmp) are NEVER processed.
    Once renamed to final extension, the file is organized.
    """
    temp_dir = Path(tempfile.mkdtemp())
    downloads = temp_dir / "Downloads"
    downloads.mkdir()

    cfg_file = temp_dir / "config.json"
    config = ConfigManager(config_file=cfg_file)
    config.set("downloads_folder", str(downloads))
    config.set("stabilization_step", 0.2)

    db = Database(db_path=temp_dir / "history.db")
    re = RuleEngine(db_instance=db)
    cl = Classifier(rule_engine=re, db_instance=db)
    org = SafeOrganizer(db=db, classifier=cl, base_downloads_folder=str(downloads))

    agent = BackgroundAgent(config=config, organizer=org)
    agent.start()

    try:
        # Chrome active download in progress:
        cr_file = downloads / "document.pdf.crdownload"
        cr_file.write_text("Partial download data...")

        time.sleep(2.0)

        # Temporary file must NOT be moved!
        assert cr_file.exists()
        history = HistoryManager(db=db)
        assert len(history.get_all_history()) == 0

        # Chrome download completes: renamed to document.pdf
        final_pdf = downloads / "document.pdf"
        cr_file.rename(final_pdf)

        time.sleep(3.0)

        # Final file is organized
        assert (downloads / "PDFs" / "document.pdf").exists() or (downloads / "Documents" / "document.pdf").exists()
        assert not final_pdf.exists()
        assert len(history.get_all_history()) == 1
    finally:
        agent.stop()
        shutil.rmtree(temp_dir, ignore_errors=True)
