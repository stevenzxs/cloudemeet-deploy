"""Initialize a dedicated IP/private-CA deployment without deleting any files."""
from pathlib import Path
import ipaddress
import secrets
import sys

root = Path(__file__).resolve().parent
host = str(ipaddress.ip_address(sys.argv[1]))
env = root / '.env'
if env.exists():
    raise SystemExit('Refusing to overwrite existing .env')
text = f'SITE_HOST={host}\nPUBLIC_URL=https://{host}\nJVB_ADVERTISE_IPS={host}\nJITSI_IMAGE_VERSION=stable-11146-2\n'
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
