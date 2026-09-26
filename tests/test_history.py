"""
Unit tests for History audit trail and reversible Undo operations.
"""

from pathlib import Path
import tempfile
import pytest

from app.classifier import Classifier
from app.database import Database
from app.history import HistoryManager
from app.organizer import SafeOrganizer
from app.rules import RuleEngine


@pytest.fixture
def history_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        downloads = base / "Downloads"
        downloads.mkdir()

        db_file = base / "history_test.db"
        db = Database(db_path=db_file)
        rule_engine = RuleEngine(db_instance=db)
        classifier = Classifier(rule_engine=rule_engine, db_instance=db)
        organizer = SafeOrganizer(db=db, classifier=classifier, base_downloads_folder=str(downloads))
        history_mgr = HistoryManager(db=db)

        yield {
            "downloads": downloads,
            "db": db,
            "organizer": organizer,
            "history": history_mgr,
        }


def test_undo_restores_file(history_env):
    downloads = history_env["downloads"]
    organizer = history_env["organizer"]
    history_mgr = history_env["history"]

    # Place and organize a resume file
    resume = downloads / "resume.pdf"
    resume.write_text("my-resume-data")

    res = organizer.organize_file(resume)
    assert res.success is True
    assert res.history_id is not None

    # Verify moved to PDFs (or Resume if rule applied)
    dest_path = Path(res.destination_path)
    assert dest_path.exists()
    assert not resume.exists()

    # Trigger Undo
    success, msg = history_mgr.undo_move(res.history_id)
    assert success is True
    assert "Restored" in msg

    # File should be back in original Downloads root
    assert resume.exists()
    assert resume.read_text() == "my-resume-data"
    assert not dest_path.exists()

    # History status should now be 'undone'
    rec = history_env["db"].get_history_by_id(res.history_id)
    assert rec["status"] == "undone"


def test_undo_never_overwrites_existing_file(history_env):
    downloads = history_env["downloads"]
    organizer = history_env["organizer"]
    history_mgr = history_env["history"]

    doc = downloads / "document.docx"
    doc.write_text("original content")

    res = organizer.organize_file(doc)
    assert res.success is True

    # User creates a new document.docx in Downloads root in the meantime
    new_doc = downloads / "document.docx"
    new_doc.write_text("new content created later")

    # Undo previous move
    success, msg = history_mgr.undo_move(res.history_id)
    assert success is True

    # Original new file must remain intact
    assert new_doc.read_text() == "new content created later"

    # Restored file safely renamed to document (1).docx
    restored = downloads / "document (1).docx"
    assert restored.exists()
    assert restored.read_text() == "original content"


def test_undo_missing_file_reports_error(history_env):
    downloads = history_env["downloads"]
    organizer = history_env["organizer"]
    history_mgr = history_env["history"]

    f = downloads / "temp.txt"
    f.write_text("hello")
    res = organizer.organize_file(f)

    # Simulate external deletion of organized file
    Path(res.destination_path).unlink()

    success, msg = history_mgr.undo_move(res.history_id)
    assert success is False
    assert "no longer exists" in msg
