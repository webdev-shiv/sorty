"""
Unit tests for Safe File Organizer engine.
Uses temporary directories. NEVER tests against real user folders.
"""

from pathlib import Path
import tempfile
import pytest

from app.classifier import Classifier
from app.database import Database
from app.organizer import SafeOrganizer
from app.rules import RuleEngine


@pytest.fixture
def test_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        downloads = base / "Downloads"
        downloads.mkdir()

        db_file = base / "test.db"
        db = Database(db_path=db_file)
        rule_engine = RuleEngine(db_instance=db)
        classifier = Classifier(rule_engine=rule_engine, db_instance=db)
        organizer = SafeOrganizer(db=db, classifier=classifier, base_downloads_folder=str(downloads))

        yield {
            "downloads": downloads,
            "db": db,
            "classifier": classifier,
            "organizer": organizer,
        }


def test_safe_file_move_creates_folder_on_demand(test_env):
    downloads = test_env["downloads"]
    organizer = test_env["organizer"]

    # Images folder should NOT exist initially
    images_dir = downloads / "Images"
    assert not images_dir.exists()

    # Create dummy photo in downloads
    test_photo = downloads / "vacation.jpg"
    test_photo.write_text("image-bytes-simulation")

    # Organize file
    res = organizer.organize_file(test_photo)
    assert res.success is True
    assert res.category == "Images"

    # Images folder should now exist
    assert images_dir.exists()
    assert (images_dir / "vacation.jpg").exists()
    # Source file in root should no longer be there
    assert not test_photo.exists()

    # Verify content was preserved exactly
    assert (images_dir / "vacation.jpg").read_text() == "image-bytes-simulation"


def test_organizer_never_overwrites(test_env):
    downloads = test_env["downloads"]
    organizer = test_env["organizer"]

    # First PDF
    pdf1 = downloads / "notes.pdf"
    pdf1.write_text("first version")
    res1 = organizer.organize_file(pdf1)
    assert res1.success is True

    # Second PDF with same filename
    pdf2 = downloads / "notes.pdf"
    pdf2.write_text("second version")
    res2 = organizer.organize_file(pdf2)
    assert res2.success is True

    # Verify both versions exist safely without overwriting
    pdfs_dir = downloads / "PDFs"
    assert (pdfs_dir / "notes.pdf").read_text() == "first version"
    assert (pdfs_dir / "notes (1).pdf").read_text() == "second version"


def test_organizer_skips_directories(test_env):
    downloads = test_env["downloads"]
    organizer = test_env["organizer"]

    # Subdirectory created by user in downloads
    sub = downloads / "MyFolder"
    sub.mkdir()

    res = organizer.organize_file(sub)
    assert res.success is False
    assert res.status == "skipped"
    assert sub.exists()  # Directory was NOT deleted or moved


def test_organizer_blocks_path_traversal(test_env):
    downloads = test_env["downloads"]
    organizer = test_env["organizer"]

    test_file = downloads / "exploit.txt"
    test_file.write_text("safe content")

    # Attempt to use a category with path traversal
    res = organizer.organize_file(test_file, custom_category="../UnsafeFolder")
    assert res.success is False
    assert "traversal" in res.error_message.lower() or "unsafe" in res.error_message.lower()
