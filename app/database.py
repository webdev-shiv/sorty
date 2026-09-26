"""
Database manager for Download Organizer.
Provides SQLite storage for movement history, custom rules, and categories.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.config import get_db_path

logger = logging.getLogger("DownloadOrganizer.Database")


class Database:
    """
    Thread-safe SQLite database manager.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency and fast writes
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def close(self) -> None:
        """Close / release database resources if needed."""
        pass

    def _init_db(self) -> None:
        """Create database tables and default categories if they do not exist."""
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    # History table
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            filename TEXT NOT NULL,
                            original_path TEXT NOT NULL,
                            destination_path TEXT NOT NULL,
                            category TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            timestamp TEXT NOT NULL,
                            file_size INTEGER NOT NULL,
                            extension TEXT NOT NULL,
                            status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'skipped', 'undone'))
                        )
                        """
                    )
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp DESC)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_filename ON history(filename)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_category ON history(category)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON history(status)")

                    # Rules table
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS rules (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            condition_type TEXT NOT NULL,
                            condition_value TEXT NOT NULL,
                            destination TEXT NOT NULL,
                            enabled INTEGER NOT NULL DEFAULT 1,
                            priority INTEGER NOT NULL DEFAULT 0,
                            logic_operator TEXT NOT NULL DEFAULT 'OR',
                            extra_conditions TEXT NOT NULL DEFAULT '[]'
                        )
                        """
                    )
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_priority ON rules(priority DESC)")

                    # Categories table
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS categories (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT UNIQUE NOT NULL,
                            folder TEXT NOT NULL,
                            icon TEXT NOT NULL DEFAULT '',
                            is_default INTEGER NOT NULL DEFAULT 0,
                            extensions TEXT NOT NULL DEFAULT ''
                        )
                        """
                    )

                self._seed_default_categories(conn)
                self._seed_default_rules(conn)
            except Exception as exc:
                logger.error("Failed to initialize database: %s", exc)
                raise
            finally:
                conn.close()

    def _seed_default_categories(self, conn: sqlite3.Connection) -> None:
        """Populate initial default categories per specification."""
        defaults = [
            ("Documents", "Documents", "📄", 1, ".doc,.docx,.txt,.rtf,.odt"),
            ("Images", "Images", "🖼️", 1, ".jpg,.jpeg,.png,.gif,.webp,.svg,.bmp,.ico,.tiff,.tif"),
            ("Videos", "Videos", "🎬", 1, ".mp4,.mkv,.avi,.mov,.webm,.flv,.m4v,.wmv"),
            ("Audio", "Audio", "🎵", 1, ".mp3,.wav,.flac,.aac,.m4a,.ogg,.wma"),
            ("Archives", "Archives", "📦", 1, ".zip,.rar,.7z,.tar,.gz,.bz2,.xz"),
            ("Installers", "Installers", "⚙️", 1, ".exe,.msi,.msix,.msixbundle"),
            ("Code", "Code", "💻", 1, ".py,.js,.ts,.java,.cpp,.c,.h,.hpp,.html,.css,.json,.xml,.sql,.go,.rs,.php,.rb"),
            ("Spreadsheets", "Spreadsheets", "📊", 1, ".xls,.xlsx,.csv,.ods"),
            ("Presentations", "Presentations", "📽️", 1, ".ppt,.pptx,.odp"),
            ("PDFs", "PDFs", "📕", 1, ".pdf"),
            ("Executables", "Executables", "⚡", 1, ".com,.scr"),
            ("Torrents", "Torrents", "🧲", 1, ".torrent"),
            ("Resume", "Resume", "📑", 1, ""),
            ("College", "College", "🎓", 1, ""),
            ("Invoices", "Invoices", "🧾", 1, ""),
            ("Projects", "Projects", "📁", 1, ""),
            ("WhatsApp Downloads", "WhatsApp Downloads", "💬", 1, ""),
            ("Others", "Others", "📁", 1, ""),
        ]
        with conn:
            for name, folder, icon, is_def, exts in defaults:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO categories (name, folder, icon, is_default, extensions)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, folder, icon, is_def, exts),
                )

    def _seed_default_rules(self, conn: sqlite3.Connection) -> None:
        """Populate starter deterministic rules (Spec #11, #13, #75)."""
        rules = [
            ("WhatsApp Downloads", "filename_contains", "whatsapp", "WhatsApp Downloads", 1, 90),
            ("WhatsApp WA_ Files", "filename_starts_with", "WA_", "WhatsApp Downloads", 1, 90),
            ("Resume Documents", "filename_contains", "resume", "Resume", 1, 50),
            ("Curriculum Vitae", "filename_contains", "cv", "Resume", 1, 50),
            ("College DBMS", "filename_contains", "dbms", "College", 1, 40),
            ("College Assignments", "filename_contains", "assignment", "College", 1, 40),
            ("College Semester", "filename_contains", "semester", "College", 1, 40),
            ("College Exams", "filename_contains", "exam", "College", 1, 40),
            ("Invoices", "filename_contains", "invoice", "Invoices", 1, 40),
            ("Receipts", "filename_contains", "receipt", "Invoices", 1, 40),
            ("Bills", "filename_contains", "bill", "Invoices", 1, 40),
        ]
        with conn:
            for name, c_type, c_val, dest, enabled, prio in rules:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO rules (name, condition_type, condition_value, destination, enabled, priority)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (name, c_type, c_val, dest, enabled, prio),
                )



    # ==========================================
    # History Operations
    # ==========================================

    def insert_history(
        self,
        filename: str,
        original_path: str,
        destination_path: str,
        category: str,
        reason: str,
        file_size: int,
        extension: str,
        status: str = "success",
        timestamp: Optional[str] = None,
    ) -> int:
        """Record a file organization attempt or result."""
        ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO history (
                            filename, original_path, destination_path, category,
                            reason, timestamp, file_size, extension, status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            filename,
                            original_path,
                            destination_path,
                            category,
                            reason,
                            ts,
                            file_size,
                            extension,
                            status,
                        ),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def update_history_status(self, history_id: int, status: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(
                        "UPDATE history SET status = ? WHERE id = ?",
                        (status, history_id),
                    )
                return True
            except Exception as exc:
                logger.error("Failed to update history status %d: %s", history_id, exc)
                return False
            finally:
                conn.close()

    def get_history_by_id(self, history_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute("SELECT * FROM history WHERE id = ?", (history_id,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def get_history(
        self,
        limit: int = 100,
        offset: int = 0,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                if status_filter and status_filter != "all":
                    rows = conn.execute(
                        "SELECT * FROM history WHERE status = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                        (status_filter, limit, offset),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM history ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                        (limit, offset),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_recent_activity(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.get_history(limit=limit, offset=0, status_filter=None)

    def get_recent_organized(self, limit: int = 200) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch files organized Today and Yesterday directly from SQLite history.
        Does NOT touch file system or duplicate any files.
        Returns {'today': [...], 'yesterday': [...]}
        """
        now = datetime.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_yesterday = start_of_today - timedelta(days=1)

        today_str = start_of_today.strftime("%Y-%m-%d %H:%M:%S")
        yesterday_str = start_of_yesterday.strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            conn = self._get_connection()
            try:
                today_rows = conn.execute(
                    """
                    SELECT * FROM history 
                    WHERE timestamp >= ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                    """,
                    (today_str, limit),
                ).fetchall()

                yesterday_rows = conn.execute(
                    """
                    SELECT * FROM history 
                    WHERE timestamp >= ? AND timestamp < ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                    """,
                    (yesterday_str, today_str, limit),
                ).fetchall()

                return {
                    "today": [dict(r) for r in today_rows],
                    "yesterday": [dict(r) for r in yesterday_rows],
                }
            finally:
                conn.close()

    def search_history(
        self,
        query: str = "",
        category: Optional[str] = None,
        extension: Optional[str] = None,
        date_str: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search solely through application SQLite history without touching hard drive."""
        sql = "SELECT * FROM history WHERE 1=1"
        params: List[Any] = []

        if query:
            clean = f"%{query.strip()}%"
            sql += " AND (filename LIKE ? OR category LIKE ? OR reason LIKE ?)"
            params.extend([clean, clean, clean])

        if category and category.lower() != "all":
            sql += " AND category = ?"
            params.append(category)

        if extension:
            ext = extension.strip()
            if not ext.startswith("."):
                ext = f".{ext}"
            sql += " AND LOWER(extension) = LOWER(?)"
            params.append(ext)

        if date_str:
            sql += " AND timestamp LIKE ?"
            params.append(f"{date_str.strip()}%")

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """Fetch summary statistics for the dashboard."""
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            conn = self._get_connection()
            try:
                # Total organized (successful)
                total_row = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM history WHERE status = 'success'"
                ).fetchone()
                total_count = total_row[0] if total_row else 0
                total_bytes = total_row[1] if total_row else 0

                # Today count
                today_row = conn.execute(
                    "SELECT COUNT(*) FROM history WHERE status = 'success' AND timestamp LIKE ?",
                    (f"{today_prefix}%",),
                ).fetchone()
                today_count = today_row[0] if today_row else 0

                return {
                    "total_organized": total_count,
                    "today_organized": today_count,
                    "total_bytes": total_bytes,
                }
            finally:
                conn.close()

    def clean_old_history(self, retention: str) -> int:
        """Purge old history records according to user retention setting."""
        days_map = {
            "30_days": 30,
            "90_days": 90,
            "1_year": 365,
        }
        days = days_map.get(retention)
        if not days:
            return 0  # 'forever'

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.execute("DELETE FROM history WHERE timestamp < ?", (cutoff,))
                    deleted = cur.rowcount
                    if deleted > 0:
                        logger.info("Purged %d history entries older than %s", deleted, cutoff)
                    return deleted
            finally:
                conn.close()

    # ==========================================
    # Rules Operations
    # ==========================================

    def get_rules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                if enabled_only:
                    rows = conn.execute(
                        "SELECT * FROM rules WHERE enabled = 1 ORDER BY priority DESC, id ASC"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM rules ORDER BY priority DESC, id ASC"
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def add_rule(
        self,
        name: str,
        condition_type: str,
        condition_value: str,
        destination: str,
        enabled: bool = True,
        priority: int = 10,
        logic_operator: str = "OR",
        extra_conditions: str = "[]",
    ) -> int:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO rules (
                            name, condition_type, condition_value, destination,
                            enabled, priority, logic_operator, extra_conditions
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            name,
                            condition_type,
                            condition_value,
                            destination,
                            1 if enabled else 0,
                            priority,
                            logic_operator,
                            extra_conditions,
                        ),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def update_rule(
        self,
        rule_id: int,
        name: str,
        condition_type: str,
        condition_value: str,
        destination: str,
        enabled: bool,
        priority: int,
        logic_operator: str = "OR",
        extra_conditions: str = "[]",
    ) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(
                        """
                        UPDATE rules
                        SET name = ?, condition_type = ?, condition_value = ?, destination = ?,
                            enabled = ?, priority = ?, logic_operator = ?, extra_conditions = ?
                        WHERE id = ?
                        """,
                        (
                            name,
                            condition_type,
                            condition_value,
                            destination,
                            1 if enabled else 0,
                            priority,
                            logic_operator,
                            extra_conditions,
                            rule_id,
                        ),
                    )
                return True
            except Exception as exc:
                logger.error("Failed to update rule %d: %s", rule_id, exc)
                return False
            finally:
                conn.close()

    def delete_rule(self, rule_id: int) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
                return True
            except Exception as exc:
                logger.error("Failed to delete rule %d: %s", rule_id, exc)
                return False
            finally:
                conn.close()

    def set_rule_priority(self, rule_id: int, new_priority: int) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("UPDATE rules SET priority = ? WHERE id = ?", (new_priority, rule_id))
                return True
            except Exception as exc:
                logger.error("Failed to update rule priority: %s", exc)
                return False
            finally:
                conn.close()

    # ==========================================
    # Categories Operations
    # ==========================================

    def get_categories(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("SELECT * FROM categories ORDER BY is_default DESC, name ASC").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def add_category(self, name: str, folder: str, icon: str = "📁", extensions: str = "") -> int:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO categories (name, folder, icon, is_default, extensions)
                        VALUES (?, ?, ?, 0, ?)
                        """,
                        (name, folder, icon, extensions),
                    )
                    return int(cur.lastrowid)
            finally:
                conn.close()

    def update_category(self, category_id: int, name: str, folder: str, icon: str, extensions: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(
                        """
                        UPDATE categories
                        SET name = ?, folder = ?, icon = ?, extensions = ?
                        WHERE id = ?
                        """,
                        (name, folder, icon, extensions, category_id),
                    )
                return True
            except Exception as exc:
                logger.error("Failed to update category %d: %s", category_id, exc)
                return False
            finally:
                conn.close()

    def delete_category(self, category_id: int) -> bool:
        """
        Delete a category record from DB.
        NOTE: This NEVER deletes any files or folders from the filesystem!
        """
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("DELETE FROM categories WHERE id = ? AND is_default = 0", (category_id,))
                return True
            except Exception as exc:
                logger.error("Failed to delete category %d: %s", category_id, exc)
                return False
            finally:
                conn.close()
