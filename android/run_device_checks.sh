#!/usr/bin/env bash
set -euo pipefail
api="$1"
report="reports/android-$api"
mkdir -p "$report"
collect() {
    timeout 20s adb pull /sdcard/Android/data/io.github.eric10z4.ynu.android/files/ "$report/device" || true
    timeout 20s adb logcat -d > "$report/emulator.log" || true
}
trap collect EXIT
adb shell wm size 720x1280
adb shell wm density 320
android/gradlew -p android connectedDebugAndroidTest
# Preserve reports before the fresh preview installation clears the test data.
timeout 20s adb pull /sdcard/Android/data/io.github.eric10z4.ynu.android/files/ "$report/device" || true
python android/preview_smoke.py --apk android/app/build/outputs/apk/preview/app-preview.apk --output "$report/preview"
