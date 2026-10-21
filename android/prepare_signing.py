"""Load the owner-authorized preview key on trusted main builds only."""
import base64
import os
from pathlib import Path

if os.environ.get('GITHUB_REF') != 'refs/heads/main' or os.environ.get('GITHUB_EVENT_NAME') == 'pull_request':
    raise RuntimeError('Preview secrets are only used on trusted main builds')
store = Path(os.environ['RUNNER_TEMP']) / 'ynu-preview.p12'
store.write_bytes(base64.b64decode(os.environ['ANDROID_PREVIEW_KEYSTORE_B64'], validate=True))
store.chmod(0o600)
password = os.environ['ANDROID_PREVIEW_STORE_PASSWORD']
if not password or '\n' in password or '\r' in password:
    raise ValueError('Invalid preview signing password')
with Path(os.environ['GITHUB_ENV']).open('a', encoding='utf-8') as output:
    output.write(f'ANDROID_PREVIEW_KEYSTORE_FILE={store}\nANDROID_PREVIEW_STORE_PASSWORD={password}\n')
print('Configured the dedicated preview key; no private key is included in artifacts.')
