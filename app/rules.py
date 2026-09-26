"""
Custom rule evaluation engine for Download Organizer.
Provides condition evaluation, priority ordering, and deterministic rule matching.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DownloadOrganizer.Rules")


@dataclass
class RuleCondition:
    condition_type: str  # 'extension_is', 'filename_contains', 'filename_starts_with', 'filename_ends_with', 'filesize_gt', 'filesize_lt', 'date_is'
    condition_value: str

    def evaluate(self, filename: str, extension: str, file_size: int, mtime: Optional[float] = None) -> Tuple[bool, str]:
        c_type = self.condition_type.strip().lower()
        val = self.condition_value.strip()

        if c_type in ("extension_is", "extension"):
            expected = val.lower()
            if not expected.startswith("."):
                expected = f".{expected}"
            matches = extension.lower() == expected
            return matches, f"Extension is '{expected}'"

        elif c_type in ("filename_contains", "contains"):
            matches = val.lower() in filename.lower()
            return matches, f"Filename contains '{val}'"

        elif c_type in ("filename_starts_with", "starts_with"):
            matches = filename.lower().startswith(val.lower())
            return matches, f"Filename starts with '{val}'"

        elif c_type in ("filename_ends_with", "ends_with"):
            # Check without extension or with extension
            stem = Path(filename).stem
            matches = filename.lower().endswith(val.lower()) or stem.lower().endswith(val.lower())
            return matches, f"Filename ends with '{val}'"

        elif c_type in ("filesize_gt", "size_greater_than"):
            try:
                # Value can be formatted like "5MB", "10KB", or bytes
                limit_bytes = parse_size_string(val)
                matches = file_size > limit_bytes
                return matches, f"File size > {val}"
            except Exception:
                return False, f"Invalid size value '{val}'"

        elif c_type in ("filesize_lt", "size_less_than"):
            try:
                limit_bytes = parse_size_string(val)
                matches = file_size < limit_bytes
                return matches, f"File size < {val}"
            except Exception:
                return False, f"Invalid size value '{val}'"

        elif c_type in ("date_is", "date"):
            # Supports 'today', 'yesterday', 'last_7_days'
            if mtime is None:
                return False, "File timestamp unavailable"
            file_date = datetime.fromtimestamp(mtime).date()
            today = datetime.now().date()
            if val.lower() == "today":
                matches = (file_date == today)
                return matches, "Date is Today"
            elif val.lower() == "yesterday":
                matches = (file_date == today - timedelta(days=1))
                return matches, "Date is Yesterday"
            elif val.lower() in ("last_7_days", "last 7 days"):
                matches = (today - timedelta(days=7) <= file_date <= today)
                return matches, "Date in Last 7 days"
            else:
                matches = str(file_date) == val
                return matches, f"Date is {val}"

        return False, f"Unknown condition '{c_type}'"


def parse_size_string(val: str) -> int:
    """Parse string representations of size like '10MB', '500KB', '1GB' into bytes."""
    v = val.strip().upper()
    multiplier = 1
    if v.endswith("GB") or v.endswith("G"):
        multiplier = 1024 * 1024 * 1024
        num_part = v.rstrip("GB").strip()
    elif v.endswith("MB") or v.endswith("M"):
        multiplier = 1024 * 1024
        num_part = v.rstrip("MB").strip()
    elif v.endswith("KB") or v.endswith("K"):
        multiplier = 1024
        num_part = v.rstrip("KB").strip()
    elif v.endswith("B"):
        multiplier = 1
        num_part = v.rstrip("B").strip()
    else:
        num_part = v

    return int(float(num_part) * multiplier)


@dataclass
class RuleMatchResult:
    rule_id: int
    rule_name: str
    destination: str
    reason: str


class RuleEngine:
    """
    Evaluates file attributes against custom user-defined rules.
    """

    def __init__(self, db_instance=None):
        self.db = db_instance

    def evaluate(
        self,
        filename: str,
        extension: str,
        file_size: int,
        mtime: Optional[float] = None,
        custom_rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[RuleMatchResult]:
        """
        Evaluate rules in priority order.
        Returns RuleMatchResult if a rule matches, or None.
        """
        rules = custom_rules
        if rules is None and self.db is not None:
            rules = self.db.get_rules(enabled_only=True)

        if not rules:
            return None

        # Sort by priority descending
        sorted_rules = sorted(rules, key=lambda r: int(r.get("priority", 0)), reverse=True)

        for rule in sorted_rules:
            if not rule.get("enabled", 1):
                continue

            primary_type = rule.get("condition_type", "")
            primary_val = rule.get("condition_value", "")
            conditions = [RuleCondition(primary_type, primary_val)]

            # Parse extra conditions if compound
            extra_json = rule.get("extra_conditions", "[]")
            if extra_json:
                try:
                    extras = json.loads(extra_json)
                    for item in extras:
                        if isinstance(item, dict) and "condition_type" in item and "condition_value" in item:
                            conditions.append(RuleCondition(item["condition_type"], item["condition_value"]))
                except Exception:
                    pass

            logic_op = str(rule.get("logic_operator", "OR")).strip().upper()

            matches = []
            explanations = []
            for cond in conditions:
                m, expl = cond.evaluate(filename, extension, file_size, mtime)
                matches.append(m)
                explanations.append(expl)

            rule_matched = False
            if logic_op == "AND":
                rule_matched = all(matches)
            else:  # Default to OR
                rule_matched = any(matches)

            if rule_matched:
                matched_reasons = [explanations[i] for i, m in enumerate(matches) if m]
                full_reason = f"User rule '{rule.get('name')}': {'; '.join(matched_reasons)}"
                return RuleMatchResult(
                    rule_id=int(rule.get("id", 0)),
                    rule_name=str(rule.get("name", "")),
                    destination=str(rule.get("destination", "")),
                    reason=full_reason,
                )

        return None
