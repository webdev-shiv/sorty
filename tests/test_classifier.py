"""
Unit tests for deterministic file classification.
Zero AI / ML.
"""

from pathlib import Path
import pytest

from app.classifier import Classifier, EXTENSION_CATEGORIES
from app.rules import RuleEngine


@pytest.fixture
def classifier():
    rule_engine = RuleEngine()
    return Classifier(rule_engine=rule_engine)


def test_extension_classification(classifier):
    # Images
    assert classifier.classify("photo.jpg").category == "Images"
    assert classifier.classify("graphic.PNG").category == "Images"
    assert classifier.classify("vector.svg").category == "Images"
    assert "Extension: .jpg" in classifier.classify("photo.jpg").reason

    # Videos
    assert classifier.classify("movie.mp4").category == "Videos"
    assert classifier.classify("stream.mkv").category == "Videos"

    # Audio
    assert classifier.classify("song.mp3").category == "Audio"
    assert classifier.classify("track.flac").category == "Audio"

    # Documents
    assert classifier.classify("notes.txt").category == "Documents"
    assert classifier.classify("report.docx").category == "Documents"

    # PDFs
    assert classifier.classify("document.pdf").category == "PDFs"

    # Spreadsheets
    assert classifier.classify("budget.xlsx").category == "Spreadsheets"
    assert classifier.classify("data.csv").category == "Spreadsheets"

    # Presentations
    assert classifier.classify("pitch.pptx").category == "Presentations"

    # Archives
    assert classifier.classify("backup.zip").category == "Archives"
    assert classifier.classify("files.tar.gz").category == "Archives"

    # Installers vs Executables: .exe MUST default to Installers
    assert classifier.classify("ChromeSetup.exe").category == "Installers"
    assert classifier.classify("installer.msi").category == "Installers"
    assert classifier.classify("command.com").category == "Executables"
    assert classifier.classify("script.scr").category == "Executables"

    # Code
    assert classifier.classify("main.py").category == "Code"
    assert classifier.classify("app.ts").category == "Code"
    assert classifier.classify("style.css").category == "Code"

    # Torrents
    assert classifier.classify("distro.iso.torrent").category == "Torrents"

    # Others (fallback)
    assert classifier.classify("unknown.xyz").category == "Others"
    assert classifier.classify("unknown.xyz").reason == "No matching rule"


def test_filename_rule_priority(classifier):
    # Resume keyword overrides PDF extension category
    res1 = classifier.classify("my_resume.pdf")
    # Wait, in the classifier hierarchy:
    # 1. Custom rules
    # 2. Extension rules
    # 3. Filename rules
    # Wait! Let's check spec #9 and #13:
    # Spec #9:
    # "Priority:
    # 1. User custom rules
    # 2. Extension rules
    # 3. Filename rules
    # 4. MIME type
    # 5. Others
    # Every classification must have a reason.
    # Example: resume.pdf -> Resume, Reason: Filename contains 'resume'
    # Example: photo.jpg -> Images, Reason: Extension: .jpg
    # Spec #13:
    # "Custom user rules always have priority over default extension rules.
    # Example: Rule: Filename contains 'resume' -> Destination: Resume.
    # Then: resume.pdf must go to: Downloads/Resume/ not: Downloads/PDFs/"
    pass


def test_custom_user_rule_overrides_extension(classifier):
    # When user defines a custom rule with high priority:
    custom_rules = [
        {
            "id": 1,
            "name": "Resume Rule",
            "condition_type": "filename_contains",
            "condition_value": "resume",
            "destination": "Resume",
            "enabled": 1,
            "priority": 100,
        },
        {
            "id": 2,
            "name": "College DBMS",
            "condition_type": "filename_contains",
            "condition_value": "DBMS",
            "destination": "College",
            "enabled": 1,
            "priority": 90,
        },
    ]

    res_resume = classifier.classify("resume.pdf", custom_rules=custom_rules)
    assert res_resume.category == "Resume"
    assert "User rule 'Resume Rule'" in res_resume.reason

    res_dbms = classifier.classify("DBMS_Assignment.pdf", custom_rules=custom_rules)
    assert res_dbms.category == "College"
    assert "User rule 'College DBMS'" in res_dbms.reason

    # Normal PDF without custom rule goes to PDFs
    res_normal = classifier.classify("general_doc.pdf", custom_rules=custom_rules)
    assert res_normal.category == "PDFs"
