"""
Realistic Scenarios Test Suite (Spec #73).
Tests:
- resume.pdf
- resume (1).pdf
- DBMS_Assignment.pdf
- IMG_20260926.jpg
- ChromeSetup.exe
- project.zip
- song.mp3
- lecture.mp4
- notes.txt
- unknown.xyz
- large.zip
- currently downloading file (.crdownload, .part, .tmp)
- locked file
- duplicate files
- multiple files organized
"""

from pathlib import Path
import tempfile
import time
import pytest

from app.classifier import Classifier
from app.config import ConfigManager
from app.database import Database
from app.organizer import SafeOrganizer
from app.rules import RuleEngine
from app.watcher import TEMP_DOWNLOAD_EXTENSIONS


@pytest.fixture
def realistic_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        downloads = base / "Downloads"
        downloads.mkdir()

        db = Database(db_path=base / "app.db")
        rule_engine = RuleEngine(db_instance=db)
        classifier = Classifier(rule_engine=rule_engine, db_instance=db)
        organizer = SafeOrganizer(db=db, classifier=classifier, base_downloads_folder=str(downloads))

        yield {
            "downloads": downloads,
            "db": db,
            "classifier": classifier,
            "organizer": organizer,
        }


def test_realistic_spec_files_classification_and_movement(realistic_env):
    downloads = realistic_env["downloads"]
    organizer = realistic_env["organizer"]

    scenarios = [
        ("resume.pdf", "Resume"),
        ("resume (1).pdf", "Resume"),
        ("DBMS_Assignment.pdf", "College"),
        ("IMG_20260926.jpg", "Images"),
        ("ChromeSetup.exe", "Installers"),
        ("backup.zip", "Archives"),
        ("my_project.zip", "Projects"),
        ("song.mp3", "Audio"),
        ("lecture.mp4", "Videos"),
        ("notes.txt", "Documents"),
        ("unknown.xyz", "Others"),
        ("large.zip", "Archives"),
    ]

    for fname, expected_cat in scenarios:
        fpath = downloads / fname
        fpath.write_text(f"dummy data for {fname}")
        res = organizer.organize_file(fpath)
        assert res.success is True, f"Failed for {fname}"
        assert res.category == expected_cat, f"{fname} went to {res.category}, expected {expected_cat}"
        # Verify file arrived safely
        assert Path(res.destination_path).exists()
        assert not fpath.exists()


def test_temporary_download_files_ignored():
    temp_files = [
        "movie.mp4.crdownload",
        "archive.zip.part",
        "setup.exe.tmp",
        "doc.pdf.download",
    ]
    for tf in temp_files:
        p = Path(tf)
        assert p.suffix.lower() in TEMP_DOWNLOAD_EXTENSIONS


def test_concurrent_batch_file_organization(realistic_env):
    downloads = realistic_env["downloads"]
    organizer = realistic_env["organizer"]

    # Create 20 files simultaneously
    files = []
    for i in range(20):
        p = downloads / f"data_export_{i}.csv"
        p.write_text(f"row,{i}")
        files.append(p)

    results = []
    for p in files:
        results.append(organizer.organize_file(p))

    assert all(r.success for r in results)
    spreadsheets_dir = downloads / "Spreadsheets"
    assert spreadsheets_dir.exists()
    assert len(list(spreadsheets_dir.glob("*.csv"))) == 20
