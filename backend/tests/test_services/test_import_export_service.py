import io
import json
import tarfile
import zipfile

from app.services.import_export_service import ImportExportService


class _UnavailableAIRouter:
    def is_available(self):
        return False


class _StubAIRouter:
    def is_available(self):
        return True

    def chat_json(self, prompt, system_prompt=None, temperature=0.1):
        del system_prompt, temperature
        payload = json.loads(prompt[0]["content"])
        return {
            "results": [
                {
                    "index": payload["notes"][0]["index"],
                    "is_idea": False,
                    "normalized_title": "",
                    "summary": "",
                },
                {
                    "index": payload["notes"][1]["index"],
                    "is_idea": True,
                    "normalized_title": "Dental Operations Platform",
                    "summary": "Software that helps dental clinics manage staffing, scheduling, and patient follow-up.",
                },
            ]
        }


class _FalseNegativeAIRouter:
    def is_available(self):
        return True

    def chat_json(self, prompt, system_prompt=None, temperature=0.1):
        del prompt, system_prompt, temperature
        return {
            "results": [
                {
                    "index": 0,
                    "is_idea": False,
                    "normalized_title": "",
                    "summary": "",
                }
            ]
        }


def _zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _tgz_bytes(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            encoded = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(encoded)
            archive.addfile(info, io.BytesIO(encoded))
    return buffer.getvalue()


def test_prepare_import_keeps_startup_notes_and_skips_personal_notes():
    service = ImportExportService(ai_router=_UnavailableAIRouter())
    archive_bytes = _zip_bytes(
        {
            "Apple Notes/clinic-platform.md": (
                "# Clinic staffing platform\n\n"
                "Build a SaaS product that helps clinics predict no-shows, coordinate staffing, and automate patient outreach."
            ),
            "Apple Notes/groceries.txt": "milk\neggs\nbananas\npaper towels",
        }
    )

    result = service.prepare_import(archive_bytes, "zip", "apple-notes-export.zip")

    assert len(result["ideas"]) == 1
    assert result["ideas"][0]["title"] == "Clinic staffing platform"
    assert "apple-notes" in result["ideas"][0]["tags"]
    assert result["skipped_non_ideas"] == 1


def test_prepare_import_google_keep_archive_preserves_labels_and_filters_notes():
    service = ImportExportService(ai_router=_UnavailableAIRouter())
    archive_bytes = _zip_bytes(
        {
            "Takeout/Keep/Product launch checklist.json": json.dumps(
                {
                    "title": "AI compliance copilot",
                    "textContent": "Startup idea for a product that helps factories automate safety and compliance documentation.",
                    "labels": ["ops", "saas"],
                }
            ),
            "Takeout/Keep/Home errands.json": json.dumps(
                {
                    "title": "Home errands",
                    "textContent": "buy light bulbs, clean garage, schedule plumber",
                }
            ),
        }
    )

    result = service.prepare_import(archive_bytes, "zip", "keep-takeout.zip")

    assert len(result["ideas"]) == 1
    assert result["ideas"][0]["title"] == "AI compliance copilot"
    assert "ops" in result["ideas"][0]["tags"]
    assert "google-keep" in result["ideas"][0]["tags"]
    assert result["skipped_non_ideas"] == 1


def test_prepare_import_supports_google_keep_tgz_exports():
    service = ImportExportService(ai_router=_UnavailableAIRouter())
    archive_bytes = _tgz_bytes(
        {
            "Takeout/Keep/Factory launch plan.json": json.dumps(
                {
                    "title": "Factory launch plan",
                    "textContent": "Business idea for a platform that helps industrial suppliers launch AI copilots for procurement teams.",
                    "labels": ["industrial"],
                }
            ),
            "Takeout/Keep/Weekend chores.json": json.dumps(
                {
                    "title": "Weekend chores",
                    "textContent": "buy detergent and clean the patio",
                }
            ),
        }
    )

    result = service.prepare_import(archive_bytes, "tgz", "keep-takeout.tgz")

    assert len(result["ideas"]) == 1
    assert result["ideas"][0]["title"] == "Factory launch plan"
    assert "industrial" in result["ideas"][0]["tags"]
    assert "google-keep" in result["ideas"][0]["tags"]
    assert result["skipped_non_ideas"] == 1


def test_prepare_import_uses_ai_classifier_when_available():
    service = ImportExportService(ai_router=_StubAIRouter())
    json_bytes = json.dumps(
        [
            {"title": "Weekend chores", "text": "Laundry, groceries, and walk the dog."},
            {
                "title": "Notes from dentist visit",
                "text": "Potential software idea for dental clinics: automate staffing, scheduling, and patient follow-up in one workflow.",
            },
        ]
    ).encode("utf-8")

    result = service.prepare_import(json_bytes, "json", "notes.json")

    assert len(result["ideas"]) == 1
    assert result["ideas"][0]["title"] == "Dental Operations Platform"
    assert "dental clinics" in result["ideas"][0]["summary"].lower()
    assert result["skipped_non_ideas"] == 1


def test_prepare_import_keeps_clear_idea_when_ai_returns_false_negative():
    service = ImportExportService(ai_router=_FalseNegativeAIRouter())
    markdown_bytes = (
        "# Fitness App\n"
        "#Ideas #Software\n\n"
        "I want to build an AI app that tracks nutrition, workouts, sleep, recovery, budgets, and health context in one product."
    ).encode("utf-8")

    result = service.prepare_import(markdown_bytes, "markdown", "Fitness App.md")

    assert len(result["ideas"]) == 1
    assert result["ideas"][0]["title"] == "Fitness App"
    assert result["skipped_non_ideas"] == 0
