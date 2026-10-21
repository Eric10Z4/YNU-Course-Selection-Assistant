"""Install the non-debuggable preview afresh; do not provide school credentials."""
import argparse
import json
from pathlib import Path
import subprocess
import time

PACKAGE='io.github.eric10z4.ynu.android'


def adb(*args, check=True):
    return subprocess.run(['adb', *args], check=check, capture_output=True, timeout=45)


def main(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    adb('uninstall', PACKAGE, check=False)
    adb('install', str(apk))
    adb('shell', 'am', 'start', '-W', '-n', PACKAGE+'/.MainActivity')
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        adb('shell', 'uiautomator', 'dump', '/sdcard/ynu-preview-ui.xml')
        xml=adb('exec-out', 'cat', '/sdcard/ynu-preview-ui.xml').stdout.decode('utf-8')
        if '找到目标课程' in xml and '尚未开始' in xml:
            (output/'preview-ui.xml').write_text(xml, encoding='utf-8')
            (output/'preview.png').write_bytes(adb('exec-out', 'screencap', '-p').stdout)
            (output/'preview-smoke.json').write_text(json.dumps({'passed':True,'scope':'fresh preview install and WebView-to-Python idle state; no credentials or school operations'}),encoding='utf-8')
            print('Fresh non-debuggable preview installed and its native bridge reached idle state')
            return
        time.sleep(1)
    raise RuntimeError('Fresh preview failed to render the initialized app')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apk',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.apk,args.output)
