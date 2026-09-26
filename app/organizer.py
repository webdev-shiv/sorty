"""
Safe File Movement Engine for Download Organizer.
CRITICAL SAFETY INVARIANTS:
1. NEVER deletes files.
2. NEVER overwrites files.
3. NEVER executes files.
4. NEVER modifies file contents.
5. Only moves files safely with atomic/standard filesystem operations.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, Optional, Tuple

from app.classifier import ClassificationResult, Classifier
from app.database import Database
from app.utils import (
    format_size,
    get_file_metadata,
    get_unique_destination_path,
    is_file_accessible,
    is_safe_path,
)

logger = logging.getLogger("DownloadOrganizer.Organizer")


@dataclass
class OrganizerResult:
    success: bool
    filename: str
    original_path: str
    destination_path: str
    category: str
    reason: str
    file_size: int
    extension: str
    history_id: Optional[int] = None
    error_message: Optional[str] = None
    status: str = "success"  # 'success', 'failed', 'skipped'


class SafeOrganizer:
    """
    Handles safe file classification, directory creation (only when needed),
    duplicate avoidance, and movement into destination categories.
    """

    def __init__(self, db: Database, classifier: Classifier, base_downloads_folder: str):
        self.db = db
        self.classifier = classifier
        self.base_downloads = Path(base_downloads_folder).resolve()

    def set_base_folder(self, new_folder: str) -> None:
        self.base_downloads = Path(new_folder).resolve()

    def organize_file(
        self,
        file_path: str | Path,
        custom_category: Optional[str] = None,
        custom_reason: Optional[str] = None,
    ) -> OrganizerResult:
        """
        Organize a single file safely.
        """
        src = Path(file_path).resolve()

        # Step 1: Safety validation of source file
        if not src.exists():
            return OrganizerResult(
                success=False,
                filename=src.name,
                original_path=str(src),
                destination_path="",
                category="Unknown",
                reason="Source file does not exist",
                file_size=0,
                extension=src.suffix.lower(),
                error_message="File not found",
                status="failed",
            )

        if not src.is_file():
            return OrganizerResult(
                success=False,
                filename=src.name,
                original_path=str(src),
                destination_path="",
                category="Unknown",
                reason="Item is a directory or special file, not a regular file",
                file_size=0,
                extension="",
                error_message="Not a regular file",
                status="skipped",
            )

        # Ensure file is in base downloads folder or a direct child of it
        # (Avoid moving files that are already inside a subcategory folder!)
        if src.parent.resolve() != self.base_downloads:
            return OrganizerResult(
                success=False,
                filename=src.name,
                original_path=str(src),
                destination_path="",
                category="Already Organized",
                reason="File is already inside an organized subfolder",
                file_size=0,
                extension=src.suffix.lower(),
                error_message="Already inside subfolder",
                status="skipped",
            )

        # Step 2: Metadata retrieval
        meta = get_file_metadata(src)
        if meta is None:
            return OrganizerResult(
                success=False,
                filename=src.name,
                original_path=str(src),
                destination_path="",
                category="Unknown",
                reason="Could not read file metadata",
                file_size=0,
                extension=src.suffix.lower(),
                error_message="Metadata read error",
                status="failed",
            )

        file_size, ext, mtime = meta

        # Step 3: Check accessibility/lock
        if not is_file_accessible(src):
            return OrganizerResult(
                success=False,
                filename=src.name,
                original_path=str(src),
                destination_path="",
                category="Locked",
                reason=f"Couldn't organize {src.name} because the file is currently in use.",
                file_size=file_size,
                extension=ext,
                error_message="File locked or in use",
                status="failed",
            )

        # Step 4: Classify file deterministically
        if custom_category:
            category = custom_category
            reason = custom_reason or f"Manually assigned to {custom_category}"
        else:
            res: ClassificationResult = self.classifier.classify(
                file_path=src,
                file_size=file_size,
                mtime=mtime,
            )
            category = res.category
            reason = res.reason

        # Step 5: Resolve destination path safely
        dest_dir = self.base_downloads / category

        # Verify path safety against traversal attacks
        if not is_safe_path(self.base_downloads, dest_dir):
            error_msg = f"Path traversal attempt or unsafe destination path: {dest_dir}"
            logger.warning(error_msg)
            return OrganizerResult(
                success=False,
                filename=src.name,
                original_path=str(src),
                destination_path="",
                category=category,
                reason=reason,
                file_size=file_size,
                extension=ext,
                error_message=error_msg,
                status="failed",
            )

        # Step 6: Create destination folder ONLY when needed
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.error("Failed to create destination directory %s: %s", dest_dir, exc)
            return OrganizerResult(
                success=False,
                filename=src.name,
                original_path=str(src),
                destination_path=str(dest_dir),
                category=category,
                reason=reason,
                file_size=file_size,
                extension=ext,
                error_message=f"Directory creation failed: {exc}",
                status="failed",
            )

        # Step 7: Resolve duplicate collision with non-destructive renaming
        final_dest_path = get_unique_destination_path(dest_dir, src.name)

        # Step 8: Safe Move (Preserves metadata, NEVER overwrites)
        try:
            # shutil.move preserves timestamps and permissions
            shutil.move(str(src), str(final_dest_path))

            # Verify successful placement
            if not final_dest_path.exists():
                raise FileNotFoundError(f"Verification failed: {final_dest_path} does not exist after move")

            # Step 9: Record into SQLite history
            history_id = self.db.insert_history(
                filename=final_dest_path.name,
                original_path=str(src),
                destination_path=str(final_dest_path),
                category=category,
                reason=reason,
                file_size=file_size,
                extension=ext,
                status="success",
            )

            logger.info("Successfully organized '%s' -> '%s' (Reason: %s)", src.name, final_dest_path, reason)

            return OrganizerResult(
                success=True,
                filename=final_dest_path.name,
                original_path=str(src),
                destination_path=str(final_dest_path),
                category=category,
                reason=reason,
                file_size=file_size,
                extension=ext,
                history_id=history_id,
                status="success",
            )

        except Exception as exc:
            logger.error("Error moving file '%s' to '%s': %s", src, final_dest_path, exc)
            # Record failed event in DB
            self.db.insert_history(
                filename=src.name,
                original_path=str(src),
                destination_path=str(final_dest_path),
                category=category,
                reason=reason,
                file_size=file_size,
                extension=ext,
                status="failed",
            )
            return OrganizerResult(
                success=False,
                filename=src.name,
                original_path=str(src),
                destination_path=str(final_dest_path),
                category=category,
                reason=reason,
                file_size=file_size,
                extension=ext,
                error_message=str(exc),
                status="failed",
            )
