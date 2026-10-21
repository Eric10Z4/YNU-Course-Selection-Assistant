"""Check APK ABI coverage and 16 KB ELF alignment, then record its origin."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile


def verify(path, commit, output):
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('An exact source commit is required')
    libraries = []
    abis = set()
    def inspect(archive, prefix=''):
        for name in archive.namelist():
            if name.endswith(('.imy', '.zip')):
                nested = io.BytesIO(archive.read(name))
                if zipfile.is_zipfile(nested):
                    with zipfile.ZipFile(nested) as child:
                        inspect(child, prefix + name + '!/')
            if not name.endswith('.so'):
                continue
            data = archive.read(name)
            if data[:6] != b'\x7fELF\x02\x01':
                raise ValueError(f'Expected little-endian 64-bit ELF: {name}')
            offset = struct.unpack_from('<Q', data, 32)[0]
            size, count = struct.unpack_from('<HH', data, 54)
            for index in range(count):
                start = offset + size * index
                kind = struct.unpack_from('<I', data, start)[0]
                alignment = struct.unpack_from('<Q', data, start + 48)[0]
                if kind == 1 and alignment < 16384:
                    raise ValueError(f'Native library is not 16 KB aligned: {prefix + name}')
            libraries.append(prefix + name)
            if not prefix and name.startswith('lib/'):
                abis.add(name.split('/')[1])
    with zipfile.ZipFile(path) as archive:
        inspect(archive)
        if abis != {'arm64-v8a', 'x86_64'}:
            raise ValueError(f'Unexpected ABI coverage: {abis}')
    tools = Path(os.environ['ANDROID_HOME']) / 'build-tools/35.0.0'
    badging = subprocess.check_output([str(tools / 'aapt'), 'dump', 'badging', str(path)], text=True)
    for required in ("versionCode='1'", "versionName='0.1.0-preview.1'", "sdkVersion:'26'", "targetSdkVersion:'36'"):
        if required not in badging:
            raise ValueError(f'Wrong Android application metadata: {required}')
    if 'application-debuggable' in badging:
        raise ValueError('Public preview must have debugging disabled')
    signing = subprocess.check_output([str(tools / 'apksigner'), 'verify', '--verbose', '--print-certs', str(path)], text=True)
    certificate = re.search(r'certificate SHA-256 digest: ([a-f0-9]+)', signing).group(1)
    stable = bool(os.environ.get('ANDROID_PREVIEW_KEYSTORE_FILE'))
    if stable and certificate != '60136241dddbf677d63bb7d59b1e1c4d2868ea1a69fc598606d58da18eabc561':
        raise ValueError('APK is not signed with the authorized preview key')
    subprocess.run([str(tools / 'zipalign'), '-c', '-P', '16', '4', str(path)], check=True)
    record = {'source_commit': commit, 'version': '0.1.0-preview.1', 'version_code': 1,
              'min_sdk': 26, 'target_sdk': 36, 'abis': sorted(abis), 'elf_16kb_alignment': 'passed',
              'native_libraries': libraries, 'filename': path.name, 'size': path.stat().st_size,
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'school_business_acceptance': 'pending'}
    record.update(debuggable=False, zip_16kb_alignment='passed', certificate_sha256=certificate,
                  signing='dedicated-preview' if stable else 'ephemeral-ci-test')
    output.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(f'Verified native ABI/alignment: {len(libraries)} libraries')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk',type=Path,required=True); parser.add_argument('--commit',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); verify(args.apk,args.commit,args.output)
