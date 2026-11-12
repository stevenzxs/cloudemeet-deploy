"""Initialize a dedicated IP/private-CA deployment without deleting any files."""
from pathlib import Path
from target import load_target
import secrets
import sys

root = Path(__file__).resolve().parents[1]
load_target(root / 'config/target.env')
env = root / '.env'
if env.exists():
    raise SystemExit('Refusing to overwrite existing .env')
text = ''
for key in ('JWT_APP_SECRET', 'JICOFO_AUTH_PASSWORD', 'JVB_AUTH_PASSWORD'):
    text += f'{key}={secrets.token_hex(32)}\n'
with env.open('x', encoding='utf-8') as stream:
    stream.write(text)
env.chmod(0o600)
for directory in ('data/api', 'data/logos', 'data/jitsi/web/nginx-custom',
                  'data/jitsi/storage/web', 'data/jitsi/storage/transcripts',
                  'data/jitsi/storage/prosody', 'data/jitsi/prosody/config',
                  'data/jitsi/prosody/prosody-plugins-custom',
                  'data/jitsi/jicofo', 'data/jitsi/jvb', 'data/jitsi/tmp/web-load-test'):
    (root / directory).mkdir(parents=True, exist_ok=True)
print('Created fresh configuration; no existing data deleted.')
