"""
Unit tests for duplicate filename resolution and extension preservation.
"""

from pathlib import Path
import tempfile
import pytest

from app.utils import get_unique_destination_path


def test_unique_filename_when_no_collision():
    with tempfile.TemporaryDirectory() as temp_dir:
        dest_path = get_unique_destination_path(temp_dir, "resume.pdf")
        assert dest_path.name == "resume.pdf"


def test_duplicate_collision_sequence():
    with tempfile.TemporaryDirectory() as temp_dir:
        dir_path = Path(temp_dir)

        # Create original resume.pdf
        (dir_path / "resume.pdf").write_text("first")

        # Second file should become resume (1).pdf
        p1 = get_unique_destination_path(dir_path, "resume.pdf")
        assert p1.name == "resume (1).pdf"
        p1.write_text("second")

        # Third file should become resume (2).pdf
        p2 = get_unique_destination_path(dir_path, "resume.pdf")
        assert p2.name == "resume (2).pdf"
        p2.write_text("third")

        # Fourth file should become resume (3).pdf
        p3 = get_unique_destination_path(dir_path, "resume.pdf")
        assert p3.name == "resume (3).pdf"


def test_preserve_multipart_extensions():
    with tempfile.TemporaryDirectory() as temp_dir:
        dir_path = Path(temp_dir)

        # Spec #17: project.backup.zip -> project.backup (1).zip (not project.backup.zip (1))
        (dir_path / "project.backup.zip").write_text("content")

        res = get_unique_destination_path(dir_path, "project.backup.zip")
        assert res.name == "project.backup (1).zip"
        assert not res.name.endswith(".zip (1)")


def test_filenames_without_extension():
    with tempfile.TemporaryDirectory() as temp_dir:
        dir_path = Path(temp_dir)

        (dir_path / "README").write_text("content")
        res = get_unique_destination_path(dir_path, "README")
        assert res.name == "README (1)"
