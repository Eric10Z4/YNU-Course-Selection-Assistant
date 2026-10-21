"""Verify an exact successful main build before preparing/publishing a preview."""

import argparse
import json
from pathlib import Path
import plistlib
import re
import subprocess
import zipfile

from app_version import VERSION, BUILD_VERSION, CHANNEL, RELEASE_TAG, BUNDLE_IDENTIFIER
from package_release import file_record, validate_reports


ARCHITECTURES = ("arm64", "x86_64")
REPOSITORY = "Eric10Z4/YNU-Course-Selection-Assistant"


def validate_source_run(run, tag):
    if tag != RELEASE_TAG:
        raise ValueError(f"Expected release tag {RELEASE_TAG}")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError("The source workflow must have completed successfully")
    if run.get("path") != ".github/workflows/macos.yml":
        raise ValueError("The source must be the macOS verification workflow")
    if run.get("event") not in ("push", "workflow_dispatch") or run.get("head_branch") != "main":
        raise ValueError("Only verified main builds can be published")
    if run.get("head_repository", {}).get("full_name") != REPOSITORY:
        raise ValueError("The source build must belong to this repository")
    commit = run.get("head_sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit")
    return commit


def verify_file(directory, record, expected_name):
    if record.get("name") != expected_name:
        raise ValueError(f"Unexpected asset filename: {record.get('name')}")
    path = directory / expected_name
    if file_record(path) != record:
        raise ValueError(f"Asset size or SHA-256 mismatch: {expected_name}")
    return path


def verify_assets(directory, commit, tag):
    if tag != RELEASE_TAG or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Wrong release tag or source commit")
    manifests, payloads = [], []
    for arch in ARCHITECTURES:
        manifest = json.loads((directory / f"manifest-{arch}.json").read_text(encoding="utf-8"))
        expected = {"schema_version": 1, "version": VERSION, "build_version": BUILD_VERSION,
                    "channel": CHANNEL, "release_tag": tag, "source_commit": commit,
                    "architecture": arch, "signing": "ad-hoc", "notarized": False,
                    "human_acceptance": "pending", "school_operations_tested": False}
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Wrong build identity or validation scope: {arch}")
        records = manifest.get("files", [])
        if len(records) != 2:
            raise ValueError(f"Expected app and verification archive for {arch}")
        app_zip = verify_file(directory, records[0], f"QiangKeWeb-{VERSION}-macos-{arch}.zip")
        audit_zip = verify_file(directory, records[1], f"verification-{arch}.zip")
        with zipfile.ZipFile(app_zip) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"Damaged application archive: {arch}")
            info = plistlib.loads(archive.read("QiangKeWeb.app/Contents/Info.plist"))
            for key, value in {"CFBundleIdentifier": BUNDLE_IDENTIFIER,
                               "CFBundleShortVersionString": VERSION, "CFBundleVersion": BUILD_VERSION,
                               "YNUReleaseChannel": CHANNEL}.items():
                if info.get(key) != value:
                    raise ValueError(f"Wrong application metadata: {arch}/{key}")
            archive.getinfo("QiangKeWeb.app/Contents/MacOS/QiangKeWeb")
        # Read only known report names. Never extract paths supplied by an archive.
        with zipfile.ZipFile(audit_zip) as audit:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="ynu release reports ") as temporary:
                report_dir = Path(temporary)
                for name in ("source-runtime.json", "bundle-runtime.json", "bundle-gui.json", "bundle.json"):
                    (report_dir / name).write_bytes(audit.read(name))
                validate_reports(report_dir, arch)
        manifests.append(manifest)
        payloads.extend((app_zip, audit_zip))
    release = {"schema_version": 1, "release_tag": tag, "source_commit": commit,
               "version": VERSION, "channel": CHANNEL, "signing": "ad-hoc", "notarized": False,
               "human_acceptance": "pending", "school_operations_tested": False, "builds": manifests}
    manifest_path = directory / "release-manifest.json"
    manifest_path.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payloads.append(manifest_path)
    sums = directory / "SHA256SUMS.txt"
    sums.write_text("".join(f"{file_record(path)['sha256']}  {path.name}\n" for path in payloads), encoding="utf-8")
    payloads.append(sums)
    return payloads


def release_notes(commit, run_id):
    return f"""macOS {VERSION} Preview 1：首个可下载的 Mac 预发布版。

## 下载

- Apple Silicon（M 系列）：`QiangKeWeb-{VERSION}-macos-arm64.zip`
- Intel：`QiangKeWeb-{VERSION}-macos-x86_64.zip`

解压后得到 QiangKeWeb.app，无需安装 Python。请完整保留应用包内容。

## 已验证

两种架构均在 macOS 15 的 GitHub 原生环境完成构建，并检查版本元数据、ad-hoc 签名、复制到其它目录后的资源/OCR/配置、本机 HTTP、原生 WebView、页面 API 及 SSE。

- 源码提交：`{commit}`
- [原生构建与验证](https://github.com/{REPOSITORY}/actions/runs/{run_id})
- SHA256SUMS.txt 提供下载校验；release-manifest.json 和 verification 压缩包提供构建来源、依赖及实际检查结果。

## 发布范围

这是 **ad-hoc 签名、未公证** 的预发布版，尚未完成 Developer ID 签名、公证和人工业务验收。下载后 macOS 可能阻止打开；请保留系统提示用于反馈，不需要关闭 Gatekeeper。

真实账号登录/选课/退选、文件对话框、休眠唤醒和下载后的安装体验仍待人工验收。仅在 macOS 15 的构建环境验证，不承诺更早系统版本兼容。安卓/iOS 本次不提供安装包。
"""


def publish_preview(directory, payloads, commit, tag, run_id):
    def releases():
        pages = json.loads(subprocess.check_output(
            ["gh", "api", f"repos/{REPOSITORY}/releases", "--paginate", "--slurp"], text=True))
        return [release for page in pages for release in page]

    # List with push credentials so that unpublished drafts are included too.
    if any(release["tag_name"] == tag for release in releases()):
        raise RuntimeError("Release already exists; do not overwrite published assets")
    existing_tag = subprocess.run(["gh", "api", f"repos/{REPOSITORY}/git/ref/tags/{tag}"], capture_output=True, text=True)
    if existing_tag.returncode == 0:
        raise RuntimeError("Tag already exists; do not attach a new build to an old tag")
    if "HTTP 404" not in existing_tag.stderr:
        raise RuntimeError("Could not establish that the release tag is unused")
    notes = directory / "release-notes.md"
    notes.write_text(release_notes(commit, run_id), encoding="utf-8")
    subprocess.run(["gh", "release", "create", tag, *map(str, payloads), "--repo", REPOSITORY,
                    "--target", commit, "--draft", "--prerelease", "--latest=false",
                    "--title", f"YNU选课助手 macOS {VERSION} Preview 1", "--notes-file", str(notes)], check=True)
    matches = [release for release in releases() if release["tag_name"] == tag]
    if len(matches) != 1:
        raise RuntimeError("Could not identify the uploaded draft")
    uploaded = matches[0]
    if not uploaded["draft"] or not uploaded["prerelease"] or uploaded["target_commitish"] != commit:
        raise RuntimeError("Uploaded draft has the wrong source or release status")
    actual = {asset["name"]: asset for asset in uploaded["assets"]}
    if set(actual) != {path.name for path in payloads}:
        raise RuntimeError("Uploaded draft assets do not match the verified payloads")
    for path in payloads:
        record = file_record(path)
        asset = actual[path.name]
        if asset["size"] != record["size_bytes"]:
            raise RuntimeError(f"Uploaded size mismatch: {path.name}")
        if asset.get("digest") and asset["digest"] != f"sha256:{record['sha256']}":
            raise RuntimeError(f"Uploaded digest mismatch: {path.name}")
    subprocess.run(["gh", "release", "edit", tag, "--repo", REPOSITORY,
                    "--draft=false", "--prerelease", "--latest=false"], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-run", type=Path)
    mode.add_argument("--assets", type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.check_run:
        commit = validate_source_run(json.loads(args.check_run.read_text(encoding="utf-8")), args.tag)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as output:
                output.write(f"source_sha={commit}\n")
        print(f"Verified successful main build: {commit}")
    else:
        payloads = verify_assets(args.assets, args.expected_commit or "", args.tag)
        if args.publish:
            if not args.run_id or not re.fullmatch(r"[0-9]+", args.run_id):
                parser.error("Publishing requires a numeric source workflow run ID")
            publish_preview(args.assets, payloads, args.expected_commit, args.tag, args.run_id)
        print(f"Verified preview assets: {len(payloads)} files")


if __name__ == "__main__":
    main()
