from __future__ import annotations

import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.classifier import Classifier

from app.config import ConfigManager, get_logs_dir
from app.database import Database
from app.history import HistoryManager
from app.notifications import NotificationManager
from app.organizer import SafeOrganizer
from app.rules import RuleEngine
from app.tray import TrayManager
from app.ui import DownloadOrganizerApp
from app.watcher import DownloadWatcher


def enable_windows_high_dpi() -> None:
    """Enable per-monitor DPI awareness on modern Windows for crisp rendering."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except Exception:
            pass


def setup_logging(logs_dir: Path) -> None:
    """Configure rotating log file in AppData and clean console output."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 5 MB max per log, keep up to 3 rotations
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logging.info("Logging initialized at %s", log_file)


def quick_organize_all(downloads_folder: Optional[str] = None, notify: bool = True) -> int:
    """
    Instantly organize all unorganized files in the Downloads folder within seconds.
    Zero prompts, completely safe, records full reversible Undo history.
    """
    import time
    start_time = time.time()

    config = ConfigManager()
    db = Database()
    rule_engine = RuleEngine(db_instance=db)
    classifier = Classifier(rule_engine=rule_engine, db_instance=db)

    target_dir = Path(downloads_folder or config.downloads_folder).resolve()
    organizer = SafeOrganizer(db=db, classifier=classifier, base_downloads_folder=str(target_dir))

    if not target_dir.exists():
        logging.warning("Downloads folder %s does not exist.", target_dir)
        return 0

    from app.watcher import TEMP_DOWNLOAD_EXTENSIONS

    files_to_sort = []
    for item in target_dir.iterdir():
        if item.is_file() and not item.name.startswith("."):
            if item.suffix.lower() not in TEMP_DOWNLOAD_EXTENSIONS:
                files_to_sort.append(item)

    organized_count = 0
    categories_used = set()

    for file_path in files_to_sort:
        try:
            res = organizer.organize_file(file_path)
            if res.success:
                organized_count += 1
                categories_used.add(res.category)
        except Exception as exc:
            logging.error("Failed to organize %s: %s", file_path.name, exc)

    elapsed = time.time() - start_time
    summary_msg = f"Organized {organized_count} files in {elapsed:.2f}s."
    logging.info(summary_msg)

    if notify and organized_count > 0:
        notifier = NotificationManager(is_enabled_getter=lambda: True)
        cats_str = ", ".join(sorted(list(categories_used))[:4])
        notifier.send_notification(
            title="Sorty",
            message=f"✓ Sorted {organized_count} files into {cats_str} ({elapsed:.1f}s)",
        )

    return organized_count


def main() -> None:
    # Check for 1-click CLI flags (--quick, --organize-now, -q, -o)
    args = sys.argv[1:]
    if any(arg in ("--quick", "--organize-now", "-q", "-o", "quick", "organize") for arg in args):
        setup_logging(get_logs_dir())
        count = quick_organize_all()
        print(f"[SUCCESS] Sorted {count} files in your Downloads folder within seconds.")
        return

    # Check for 1-click Undo CLI flags (--undo, --undo-last, -u, undo)
    if any(arg in ("--undo", "--undo-last", "-u", "undo") for arg in args):
        setup_logging(get_logs_dir())
        db = Database()
        history = HistoryManager(db=db)
        count, msg = history.undo_last_batch()
        print(f"[UNDO] {msg}")
        return

    # Single-instance activation: if already running, bring existing window to foreground
    import socket
    import threading

    def check_single_instance(port: int = 49281) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
            s.sendall(b"SHOW\n")
            s.close()
            return False
        except Exception:
            return True

    def start_single_instance_server(app_show_callback, port: int = 49281):
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.bind(("127.0.0.1", port))
            server_sock.listen(5)

            def _listen():
                while True:
                    try:
                        conn, _ = server_sock.accept()
                        data = conn.recv(1024)
                        conn.close()
                        if b"SHOW" in data:
                            app_show_callback()
                    except Exception:
                        break

            t = threading.Thread(target=_listen, daemon=True, name="SingleInstanceServer")
            t.start()
            return server_sock
        except Exception as exc:
            logging.debug("Could not bind single instance port: %s", exc)
            return None

    if not check_single_instance():
        print("Sorty is already running in the background. Window brought to foreground.")
        return

    start_minimized = any(arg in ("--minimized", "--tray", "--background", "-m", "-b") for arg in args)

    enable_windows_high_dpi()

    logs_dir = get_logs_dir()
    setup_logging(logs_dir)

    logging.info("Starting Sorty...")

    # Load configuration
    config = ConfigManager()

    # Initialize SQLite database
    db = Database()

    # Initialize rules engine and deterministic classifier
    rule_engine = RuleEngine(db_instance=db)
    classifier = Classifier(rule_engine=rule_engine, db_instance=db)

    # Initialize safe organizer
    organizer = SafeOrganizer(
        db=db,
        classifier=classifier,
        base_downloads_folder=config.downloads_folder,
    )

    # Initialize history manager
    history = HistoryManager(db=db)

    # Notification Manager
    notifier_tray_callback = [None]
    notifier = NotificationManager(
        is_enabled_getter=lambda: config.notifications,
        tray_notifier=lambda title, msg: notifier_tray_callback[0](title, msg) if notifier_tray_callback[0] else None,
    )

    def on_file_organized(res):
        if res.success:
            notifier.notify_organized(res.filename, res.category)

    # Initialize and start Background Agent (Part 1: runs independently of UI)
    background_agent = DownloadWatcher(
        config=config,
        organizer=organizer,
        on_file_organized=on_file_organized,
    )
    background_agent.start()

    # Resolve icon path
    base_dir = Path(__file__).resolve().parent.parent
    icon_path = base_dir / "assets" / "icon.ico"
    if not icon_path.exists():
        icon_path = base_dir / "assets" / "icon.png"

    # Instantiate UI (UI is only a control panel)
    app = DownloadOrganizerApp(
        config=config,
        db=db,
        classifier=classifier,
        organizer=organizer,
        history=history,
        watcher=background_agent,
        icon_path=icon_path if icon_path.exists() else None,
    )

    # Initialize Tray Manager
    tray_manager = TrayManager(
        icon_path=icon_path,
        on_show_app=app.show_window,
        on_check_downloads=app.check_downloads_dialog,
        on_organize_now=app.manual_organize_now,
        on_pause=lambda: (background_agent.set_paused(True), app.update_status_indicator(), tray_manager.update_menu()),
        on_resume=lambda: (background_agent.set_paused(False), app.update_status_indicator(), tray_manager.update_menu()),
        on_toggle_pause=lambda: (app.toggle_pause(), tray_manager.update_menu()),
        on_open_downloads=app.open_downloads_folder,
        on_open_settings=lambda: (app.show_window(), app.navigate("settings")),
        on_exit=app.quit_application,
        is_paused_getter=lambda: background_agent.is_paused,
        on_undo_last=app.handle_undo_last_batch,
    )
    app.set_tray_manager(tray_manager)
    notifier_tray_callback[0] = tray_manager.notify
    tray_manager.start()

    single_instance_sock = start_single_instance_server(app.show_window)

    try:
        app.run(start_minimized=start_minimized)
    finally:
        logging.info("Shutting down Sorty...")
        if single_instance_sock:
            try:
                single_instance_sock.close()
            except Exception:
                pass
        tray_manager.stop()
        background_agent.stop()


if __name__ == "__main__":
    main()
