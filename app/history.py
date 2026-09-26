"""
History and Undo manager for Download Organizer.
Provides reversible file movements, history retrieval, and status updates.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

from app.database import Database
from app.utils import get_unique_destination_path

logger = logging.getLogger("DownloadOrganizer.History")


class HistoryManager:
    """
    Manages audit trail of file movements and provides safe, reversible Undo.
    """

    def __init__(self, db: Database):
        self.db = db

    def undo_move(self, history_id: int) -> Tuple[bool, str]:
        """
        Revert a previous file organization.
        Moves the file back from destination_path to original_path.
        Never overwrites files.
        """
        record = self.db.get_history_by_id(history_id)
        if not record:
            return False, "History entry not found."

        if record["status"] == "undone":
            return False, "This file movement has already been undone."

        dest_path = Path(record["destination_path"])
        orig_path = Path(record["original_path"])

        if not dest_path.exists():
            return False, "File could not be restored because it no longer exists."

        # Target directory to restore into
        restore_dir = orig_path.parent
        restore_dir.mkdir(parents=True, exist_ok=True)

        # Avoid overwriting if a file with original filename exists
        target_restore_path = get_unique_destination_path(restore_dir, orig_path.name)

        try:
            shutil.move(str(dest_path), str(target_restore_path))
            self.db.update_history_status(history_id, "undone")
            logger.info("Undone move for history #%d: '%s' restored to '%s'", history_id, dest_path, target_restore_path)
            return True, f"Restored {dest_path.name} to {target_restore_path.name}"
        except Exception as exc:
            logger.error("Failed to restore file '%s' -> '%s': %s", dest_path, target_restore_path, exc)
            return False, f"Failed to restore file: {exc}"

    def undo_last_move(self) -> Tuple[bool, str]:
        """Undo the single most recent file movement."""
        recent = self.db.get_history(limit=1, status_filter="success")
        if not recent:
            return False, "No recent file movements to undo."
        return self.undo_move(recent[0]["id"])

    def undo_last_batch(self) -> Tuple[int, str]:
        """
        Revert the most recent batch of file movements.
        Restores files back to their original Downloads location safely.
        """
        from datetime import datetime
        recent = self.db.get_history(limit=500, status_filter="success")
        if not recent:
            return 0, "No recent successful file movements to undo."

        latest_ts = recent[0]["timestamp"]
        try:
            latest_dt = datetime.strptime(latest_ts, "%Y-%m-%d %H:%M:%S")
        except Exception:
            latest_dt = None

        batch_to_undo = []
        for r in recent:
            if latest_dt:
                try:
                    r_dt = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
                    if abs((latest_dt - r_dt).total_seconds()) <= 60:
                        batch_to_undo.append(r)
                        continue
                except Exception:
                    pass
            if r["timestamp"] == latest_ts:
                batch_to_undo.append(r)

        if not batch_to_undo:
            batch_to_undo = [recent[0]]

        restored_count = 0
        for r in batch_to_undo:
            ok, _ = self.undo_move(r["id"])
            if ok:
                restored_count += 1

        if restored_count > 0:
            return restored_count, f"Successfully restored {restored_count} file(s) back to original location."
        else:
            return 0, "No files could be restored (they may have been moved or already undone)."

    def get_recent_activity(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.db.get_recent_activity(limit=limit)

    def get_recent_organized(self, limit: int = 200) -> Dict[str, List[Dict[str, Any]]]:
        return self.db.get_recent_organized(limit=limit)


    def get_all_history(self, limit: int = 200, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.db.get_history(limit=limit, status_filter=status_filter)

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        extension: Optional[str] = None,
        date_str: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return self.db.search_history(
            query=query,
            category=category,
            extension=extension,
            date_str=date_str,
            limit=limit,
        )
