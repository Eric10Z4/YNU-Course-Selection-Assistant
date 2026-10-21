import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "macos"))
from app_version import VERSION, BUILD_VERSION, CHANNEL, RELEASE_TAG, BUNDLE_IDENTIFIER
from package_release import file_record
from verify_release import verify_assets, validate_source_run


COMMIT = "a" * 40


class SourceRunTests(unittest.TestCase):
    def setUp(self):
        self.run = {"status": "completed", "conclusion": "success",
                    "path": ".github/workflows/macos.yml", "event": "push",
                    "head_branch": "main", "head_sha": COMMIT,
                    "head_repository": {"full_name": "Eric10Z4/YNU-Course-Selection-Assistant"}}

    def test_successful_main_build_is_accepted(self):
        self.assertEqual(validate_source_run(self.run, RELEASE_TAG), COMMIT)

    def test_pull_request_build_cannot_be_published(self):
        self.run["event"] = "pull_request"
        with self.assertRaisesRegex(ValueError, "main builds"):
            validate_source_run(self.run, RELEASE_TAG)

    def test_failed_or_incomplete_build_cannot_be_published(self):
        self.run["conclusion"] = "failure"
        with self.assertRaisesRegex(ValueError, "successfully"):
            validate_source_run(self.run, RELEASE_TAG)

    def test_other_repository_is_rejected(self):
        self.run["head_repository"]["full_name"] = "someone/other-repo"
        with self.assertRaisesRegex(ValueError, "this repository"):
            validate_source_run(self.run, RELEASE_TAG)


class ReleaseAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for arch in ("arm64", "x86_64"):
            app = self.directory / f"QiangKeWeb-{VERSION}-macos-{arch}.zip"
            with zipfile.ZipFile(app, "w") as archive:
                archive.writestr("QiangKeWeb.app/Contents/Info.plist", plistlib.dumps({
                    "CFBundleIdentifier": BUNDLE_IDENTIFIER, "CFBundleShortVersionString": VERSION,
                    "CFBundleVersion": BUILD_VERSION, "YNUReleaseChannel": CHANNEL,
                }))
                archive.writestr("QiangKeWeb.app/Contents/MacOS/QiangKeWeb", b"fixture executable")
            audit = self.directory / f"verification-{arch}.zip"
            reports = {}
            for mode in ("source-runtime", "bundle-runtime", "bundle-gui"):
                checks = (["native_webview_render", "javascript_to_local_api", "sse_to_native_webview"]
                          if mode == "bundle-gui" else
                          ["resources", "synthetic_ocr_inference", "fallback_config_round_trip", "loopback_http_and_token_check"])
                reports[f"{mode}.json"] = {"status": "passed", "system": "Darwin", "architecture": arch,
                    "version": VERSION, "build_version": BUILD_VERSION, "channel": CHANNEL,
                    "frozen": mode != "source-runtime", "checks": dict.fromkeys(checks, "passed")}
            reports["bundle.json"] = {"architecture": arch, "ad_hoc_signature_verified": True}
            with zipfile.ZipFile(audit, "w") as archive:
                for name, content in reports.items():
                    archive.writestr(name, json.dumps(content))
            self.write_manifest(arch, app, audit)

    def write_manifest(self, arch, app, audit, **changes):
        manifest = {"schema_version": 1, "version": VERSION, "build_version": BUILD_VERSION,
                    "channel": CHANNEL, "release_tag": RELEASE_TAG, "source_commit": COMMIT,
                    "architecture": arch, "signing": "ad-hoc", "notarized": False,
                    "human_acceptance": "pending", "school_operations_tested": False,
                    "files": [file_record(app), file_record(audit)]}
        manifest.update(changes)
        (self.directory / f"manifest-{arch}.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_both_verified_architectures_produce_a_complete_payload(self):
        payload = verify_assets(self.directory, COMMIT, RELEASE_TAG)
        self.assertEqual(len(payload), 6)
        self.assertTrue(all(path.is_file() for path in payload))
        release = json.loads((self.directory / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({entry["architecture"] for entry in release["builds"]}, {"arm64", "x86_64"})
        self.assertFalse(release["notarized"])

    def test_modified_download_is_rejected(self):
        path = self.directory / f"QiangKeWeb-{VERSION}-macos-arm64.zip"
        path.write_bytes(path.read_bytes() + b"unexpected modification")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            verify_assets(self.directory, COMMIT, RELEASE_TAG)

    def test_old_build_cannot_be_relabelled_as_a_new_commit(self):
        with self.assertRaisesRegex(ValueError, "build identity"):
            verify_assets(self.directory, "b" * 40, RELEASE_TAG)

    def test_path_from_manifest_cannot_escape_the_payload_directory(self):
        path = self.directory / "manifest-arm64.json"
        content = json.loads(path.read_text(encoding="utf-8"))
        content["files"][0]["name"] = "../different-file.zip"
        path.write_text(json.dumps(content), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "filename"):
            verify_assets(self.directory, COMMIT, RELEASE_TAG)

    def test_unversioned_application_is_rejected_even_with_updated_hash(self):
        app = self.directory / f"QiangKeWeb-{VERSION}-macos-arm64.zip"
        audit = self.directory / "verification-arm64.zip"
        with zipfile.ZipFile(app, "w") as archive:
            archive.writestr("QiangKeWeb.app/Contents/Info.plist", plistlib.dumps({
                "CFBundleIdentifier": BUNDLE_IDENTIFIER, "CFBundleShortVersionString": "0.0.0",
                "CFBundleVersion": BUILD_VERSION, "YNUReleaseChannel": CHANNEL,
            }))
        self.write_manifest("arm64", app, audit)
        with self.assertRaisesRegex(ValueError, "application metadata"):
            verify_assets(self.directory, COMMIT, RELEASE_TAG)

    def test_failed_native_gui_cannot_be_published_even_with_updated_hash(self):
        app = self.directory / f"QiangKeWeb-{VERSION}-macos-arm64.zip"
        audit = self.directory / "verification-arm64.zip"
        with zipfile.ZipFile(audit) as archive:
            reports = {name: archive.read(name) for name in archive.namelist()}
        gui = json.loads(reports["bundle-gui.json"])
        gui["checks"]["sse_to_native_webview"] = "failed"
        reports["bundle-gui.json"] = json.dumps(gui).encode("utf-8")
        with zipfile.ZipFile(audit, "w") as archive:
            for name, data in reports.items():
                archive.writestr(name, data)
        self.write_manifest("arm64", app, audit)
        with self.assertRaisesRegex(ValueError, "Missing verification"):
            verify_assets(self.directory, COMMIT, RELEASE_TAG)


if __name__ == "__main__":
    unittest.main()
