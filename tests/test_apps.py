import plistlib

from semsearch import apps


def _app(tmp_path, name, info):
    d = tmp_path / f"{name}.app" / "Contents"
    d.mkdir(parents=True)
    with open(d / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    return str(tmp_path / f"{name}.app")


def test_known_app_gets_curated_description(tmp_path):
    p = _app(tmp_path, "Notes", {"CFBundleIdentifier": "com.apple.Notes"})
    assert "notes" in apps.describe(p)


def test_unknown_app_falls_back_to_category_and_document_types(tmp_path):
    p = _app(tmp_path, "Mystery", {"CFBundleIdentifier": "x.mystery",
                                    "LSApplicationCategoryType": "public.app-category.finance",
                                    "CFBundleDocumentTypes": [{"CFBundleTypeName": "Ledger File"}]})
    d = apps.describe(p)
    assert "finance" in d and "Ledger File" in d


def test_app_without_info_plist_is_skipped(tmp_path):
    (tmp_path / "Broken.app").mkdir()
    assert apps.describe(str(tmp_path / "Broken.app")) == ""
