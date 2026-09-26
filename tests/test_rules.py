"""
Unit tests for Custom Rule Engine.
"""

from datetime import datetime, timedelta
import json
import pytest

from app.rules import RuleEngine, RuleCondition, parse_size_string


def test_parse_size_string():
    assert parse_size_string("10B") == 10
    assert parse_size_string("1KB") == 1024
    assert parse_size_string("5MB") == 5 * 1024 * 1024
    assert parse_size_string("2GB") == 2 * 1024 * 1024 * 1024


def test_rule_conditions():
    # Extension condition
    c1 = RuleCondition("extension_is", ".pdf")
    matched, reason = c1.evaluate("doc.pdf", ".pdf", 100)
    assert matched is True
    assert "Extension is '.pdf'" in reason

    # Filename contains
    c2 = RuleCondition("filename_contains", "invoice")
    matched, reason = c2.evaluate("company_invoice_2026.pdf", ".pdf", 100)
    assert matched is True

    # Filename starts with
    c3 = RuleCondition("filename_starts_with", "IMG_")
    matched, _ = c3.evaluate("IMG_20260926.jpg", ".jpg", 100)
    assert matched is True
    matched, _ = c3.evaluate("photo_IMG.jpg", ".jpg", 100)
    assert matched is False

    # Filename ends with
    c4 = RuleCondition("filename_ends_with", "_backup")
    matched, _ = c4.evaluate("database_backup.zip", ".zip", 100)
    assert matched is True

    # File size greater than
    c5 = RuleCondition("filesize_gt", "10MB")
    matched, _ = c5.evaluate("large.zip", ".zip", 15 * 1024 * 1024)
    assert matched is True
    matched, _ = c5.evaluate("small.zip", ".zip", 5 * 1024 * 1024)
    assert matched is False

    # Date condition
    c6 = RuleCondition("date_is", "today")
    now_ts = datetime.now().timestamp()
    matched, _ = c6.evaluate("today.pdf", ".pdf", 100, mtime=now_ts)
    assert matched is True


def test_rule_priority_and_ordering():
    engine = RuleEngine()
    rules = [
        {
            "id": 1,
            "name": "Low Priority Zip",
            "condition_type": "extension_is",
            "condition_value": ".zip",
            "destination": "GeneralArchives",
            "enabled": 1,
            "priority": 10,
        },
        {
            "id": 2,
            "name": "High Priority Project Zip",
            "condition_type": "filename_contains",
            "condition_value": "project",
            "destination": "ProjectArchives",
            "enabled": 1,
            "priority": 50,
        },
    ]

    res = engine.evaluate(
        filename="project_source.zip",
        extension=".zip",
        file_size=1024,
        custom_rules=rules,
    )
    assert res is not None
    assert res.destination == "ProjectArchives"
    assert res.rule_name == "High Priority Project Zip"


def test_disabled_rule_skipped():
    engine = RuleEngine()
    rules = [
        {
            "id": 1,
            "name": "Disabled Rule",
            "condition_type": "filename_contains",
            "condition_value": "test",
            "destination": "Tests",
            "enabled": 0,
            "priority": 100,
        }
    ]

    res = engine.evaluate(
        filename="test_file.txt",
        extension=".txt",
        file_size=10,
        custom_rules=rules,
    )
    assert res is None


def test_compound_and_rule():
    engine = RuleEngine()
    rules = [
        {
            "id": 1,
            "name": "Large PDF Rule",
            "condition_type": "extension_is",
            "condition_value": ".pdf",
            "destination": "LargePDFs",
            "enabled": 1,
            "priority": 20,
            "logic_operator": "AND",
            "extra_conditions": json.dumps([
                {"condition_type": "filesize_gt", "condition_value": "5MB"}
            ]),
        }
    ]

    # Matching: PDF and > 5MB
    res_match = engine.evaluate(
        filename="ebook.pdf",
        extension=".pdf",
        file_size=10 * 1024 * 1024,
        custom_rules=rules,
    )
    assert res_match is not None
    assert res_match.destination == "LargePDFs"

    # Non-matching: PDF but < 5MB
    res_small = engine.evaluate(
        filename="small.pdf",
        extension=".pdf",
        file_size=1024,
        custom_rules=rules,
    )
    assert res_small is None
