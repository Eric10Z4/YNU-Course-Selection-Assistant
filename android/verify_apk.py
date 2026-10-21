"""Check APK ABI coverage and 16 KB ELF alignment, then record its origin."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def verify(path, commit, output):
    libraries = []
    with zipfile.ZipFile(path) as archive:
        abis = set()
        for name in archive.namelist():
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
                    raise ValueError(f'Native library is not 16 KB aligned: {name}')
            libraries.append(name)
            if name.startswith('lib/'):
                abis.add(name.split('/')[1])
        if abis != {'arm64-v8a', 'x86_64'}:
            raise ValueError(f'Unexpected ABI coverage: {abis}')
    record = {'source_commit': commit, 'version': '0.1.0-preview.1', 'version_code': 1,
              'min_sdk': 26, 'target_sdk': 36, 'abis': sorted(abis), 'elf_16kb_alignment': 'passed',
              'native_libraries': libraries, 'filename': path.name, 'size': path.stat().st_size,
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'school_business_acceptance': 'pending'}
    output.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(f'Verified native ABI/alignment: {len(libraries)} libraries')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk',type=Path,required=True); parser.add_argument('--commit',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); verify(args.apk,args.commit,args.output)
