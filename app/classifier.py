"""
Deterministic file classifier for Download Organizer.
ZERO AI or machine learning.
Priority:
1. User custom rules
2. Extension rules
3. Filename rules
4. MIME type
5. Others
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from app.rules import RuleEngine, RuleMatchResult

logger = logging.getLogger("DownloadOrganizer.Classifier")

# Default Extension Mappings (Deterministic per specification)
EXTENSION_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "Images": (
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff", ".tif"
    ),
    "Videos": (
        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv"
    ),
    "Audio": (
        ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma", ".opus"
    ),
    "PDFs": (
        ".pdf",
    ),
    "Documents": (
        ".doc", ".docx", ".txt", ".rtf", ".odt"
    ),
    "Spreadsheets": (
        ".xls", ".xlsx", ".csv", ".ods"
    ),
    "Presentations": (
        ".ppt", ".pptx", ".odp"
    ),
    "Archives": (
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"
    ),
    "Installers": (
        # Note: .exe defaults to Installers
        ".exe", ".msi", ".msix", ".msixbundle"
    ),
    "Code": (
        ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".hpp",
        ".html", ".css", ".json", ".xml", ".sql", ".go", ".rs", ".php", ".rb"
    ),
    "Torrents": (
        ".torrent",
    ),
    "Executables": (
        ".com", ".scr"
    ),
}

# Reverse lookup map: extension -> category
EXT_TO_CATEGORY: Dict[str, str] = {}
for cat, exts in EXTENSION_CATEGORIES.items():
    for ext in exts:
        EXT_TO_CATEGORY[ext.lower()] = cat

# WhatsApp Filename Regexes (Spec: IMG/VID/AUD/DOC/PTT-YYYYMMDD-WA#### and general IMG-*_WA*)
WHATSAPP_PATTERNS = [
    re.compile(r"^(IMG|VID|AUD|DOC|PTT)-\d{8}-WA\d+", re.IGNORECASE),
    re.compile(r"^(IMG|VID|AUD|DOC|PTT)-.*[-_]WA", re.IGNORECASE),
    re.compile(r"^(IMG|VID|AUD|DOC|PTT)-.*WA", re.IGNORECASE),
]

# Default User Filename Rules (Deterministic keyword matching)
DEFAULT_FILENAME_RULES: List[Tuple[Tuple[str, ...], str]] = [
    (("resume", "cv"), "Resume"),
    (("college", "assignment", "dbms", "btech", "aktu", "semester", "exam"), "College"),
    (("invoice", "bill", "receipt"), "Invoices"),
    (("project", "source-code", "source"), "Projects"),
]


@dataclass
class ClassificationResult:
    category: str
    destination_folder: str
    reason: str
    rule_id: Optional[int] = None


class Classifier:
    """
    Deterministic file classifier.
    Produces predictable, explainable destination and reason for any file.
    STRICT PRIORITY:
    1. WhatsApp filename pattern (priority over extension)
    2. User filename rules
    3. Extension
    4. Others
    """

    def __init__(self, rule_engine: Optional[RuleEngine] = None, db_instance=None):
        self.rule_engine = rule_engine or RuleEngine(db_instance=db_instance)
        self.db = db_instance

    def is_whatsapp_file(self, filename: str) -> bool:
        """Check if filename matches WhatsApp download conventions."""
        stem = Path(filename).stem
        for pat in WHATSAPP_PATTERNS:
            if pat.search(filename) or pat.search(stem):
                return True
        name_lower = filename.lower()
        if "whatsapp" in name_lower or name_lower.startswith("wa_"):
            return True
        return False

    def classify(
        self,
        file_path: str | Path,
        file_size: int = 0,
        mtime: Optional[float] = None,
        custom_rules: Optional[List[Dict[str, Any]]] = None,
    ) -> ClassificationResult:
        """
        Classifies a file following the strict 4-tier priority hierarchy:
        1. WhatsApp filename pattern
        2. User filename rules
        3. Extension
        4. Others
        """
        path = Path(file_path)
        filename = path.name
        ext = path.suffix.lower()
        name_lower = filename.lower()

        # -------------------------------------------------------------
        # Tier 1: WhatsApp Filename Pattern (Priority over extension!)
        # -------------------------------------------------------------
        if self.is_whatsapp_file(filename):
            return ClassificationResult(
                category="WhatsApp Downloads",
                destination_folder="WhatsApp Downloads",
                reason="WhatsApp filename pattern",
            )

        # -------------------------------------------------------------
        # Tier 2: User Rules (Custom DB Rules + Default Filename Rules)
        # -------------------------------------------------------------
        if self.rule_engine:
            match = self.rule_engine.evaluate(
                filename=filename,
                extension=ext,
                file_size=file_size,
                mtime=mtime,
                custom_rules=custom_rules,
            )
            if match:
                return ClassificationResult(
                    category=match.destination,
                    destination_folder=match.destination,
                    reason=match.reason,
                    rule_id=match.rule_id,
                )

        for keywords, target_cat in DEFAULT_FILENAME_RULES:
            for kw in keywords:
                if kw in name_lower:
                    return ClassificationResult(
                        category=target_cat,
                        destination_folder=target_cat,
                        reason=f"Filename contains '{kw}'",
                    )

        # -------------------------------------------------------------
        # Tier 3: Extension Rules
        # -------------------------------------------------------------
        # First check if database has custom category extensions
        db_category = self._check_db_category_extensions(ext)
        if db_category:
            return ClassificationResult(
                category=db_category,
                destination_folder=db_category,
                reason=f"Extension: {ext}",
            )

        if ext in EXT_TO_CATEGORY:
            category = EXT_TO_CATEGORY[ext]
            return ClassificationResult(
                category=category,
                destination_folder=category,
                reason=f"Extension: {ext}",
            )

        # -------------------------------------------------------------
        # Tier 4: Others (Fallback)
        # -------------------------------------------------------------
        return ClassificationResult(
            category="Others",
            destination_folder="Others",
            reason="No matching rule",
        )

    def _check_db_category_extensions(self, ext: str) -> Optional[str]:
        """Check if any category in the database explicitly maps this extension."""
        if not self.db:
            return None
        try:
            categories = self.db.get_categories()
            for cat in categories:
                ext_str = cat.get("extensions", "")
                if ext_str:
                    allowed = [e.strip().lower() for e in ext_str.split(",") if e.strip()]
                    if ext in allowed:
                        return cat.get("name")
        except Exception as exc:
            logger.debug("Error checking DB category extensions: %s", exc)
        return None

