"""Version identity for the first macOS public preview."""

VERSION = "2.4.1"
BUILD_VERSION = "2.4.1"
CHANNEL = "preview.1"
DISPLAY_VERSION = f"{VERSION}-{CHANNEL}"
RELEASE_TAG = f"macos-v{DISPLAY_VERSION}"
BUNDLE_IDENTIFIER = "io.github.eric10z4.ynu-course-selection-assistant"


def bundle_metadata():
    return {
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": BUILD_VERSION,
        "CFBundleGetInfoString": f"YNU Course Assistant {DISPLAY_VERSION}",
        "YNUReleaseChannel": CHANNEL,
    }
