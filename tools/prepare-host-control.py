#!/usr/bin/env python3
"""Prepare an opt-in host-control overlay; never restarts or deploys services.

Run on the approved Linux target as root after backup. Existing output refuses
overwrite. No secrets leave the target. Actual Compose activation is separate.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess


def prepare(root, prosody_container):
    root = Path(root).resolve()
    out = root / 'host-control'
    if out.exists():
        raise RuntimeError('host-control already exists; inspect rather than overwrite')
    if not (root / '.env').is_file():
        raise RuntimeError('existing instance .env required')
    # Inspect the exact deployed generator, never invent a new global config.
    template = subprocess.check_output(['docker', 'exec', prosody_container,
                                        'cat', '/defaults/prosody.cfg.lua'], text=True)
    if 'Include' not in template:
        raise RuntimeError('unsupported Prosody configuration template')
    out.mkdir(mode=0o750)
    # Precreate persistent bind parent; Docker-created root-owned directories
    # cannot be copied/managed by the uid1000 Prosody startup process.
    conf = root/'data/jitsi/prosody/config/conf.d'
    conf.mkdir(parents=True, exist_ok=True)
    os.chown(conf, 1000, 1000)
    secret = secrets.token_urlsafe(48)
    private = out / 'private'
    private.mkdir(mode=0o700)
    def openssl(*args):
        subprocess.run(['openssl', *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    openssl('req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '3650',
            '-subj', '/CN=CloudMeet Internal Host Control CA', '-keyout', str(private/'ca.key'), '-out', str(out/'ca.crt'))
    openssl('req', '-newkey', 'rsa:3072', '-nodes', '-subj', '/CN=gateway',
            '-keyout', str(private/'gateway.key'), '-out', str(private/'gateway.csr'))
    (private/'cert.ext').write_text('subjectAltName=DNS:gateway\nextendedKeyUsage=serverAuth\n')
    openssl('x509', '-req', '-in', str(private/'gateway.csr'), '-CA', str(out/'ca.crt'),
            '-CAkey', str(private/'ca.key'), '-CAcreateserial', '-days', '365',
            '-extfile', str(private/'cert.ext'), '-out', str(out/'gateway.crt'))
    for path in private.iterdir():
        path.chmod(0o600)
    (out/'api.env').write_text('JITSI_ROLE_CHECK_SECRET='+secret+'\n')
    (out/'api.env').chmod(0o600)
    # Set global trust before the generated template enters any VirtualHost.
    (out/'prosody.cfg.lua').write_text('client_https_ssl = { cafile = "/host-control/ca.crt", verify = "peer" };\n'+template)
    endpoints = {'host_role_check_url':'check', 'host_transfer_url':'rotate',
                 'host_transfer_complete_url':'complete', 'host_transfer_status_url':'status',
                 'host_transfer_rebind_url':'rebind', 'host_transfer_claim_url':'claim', 'host_reclaim_url':'reclaim'}
    config = 'Component "muc.meet.jitsi" "muc"\n'
    config += 'host_role_check_secret = '+json.dumps(secret)+';\n'
    config += 'host_transfer_participant_domain = "meet.jitsi";\n'
    config += 'host_transfer_enabled = false;\nhost_reclaim_enabled = false;\nhost_transfer_admin_recovery_enabled = false;\n'
    for name, endpoint in endpoints.items():
        config += name+' = "https://gateway:9443/internal/host-role/v1/'+endpoint+'";\n'
    # Module list is configured through XMPP_MUC_MODULES, not overwritten here.
    cfg = out/'zz-cloudmeet-host-control.cfg.lua'
    cfg.write_text(config)
    os.chown(out, 1000, 1000)
    os.chown(cfg, 1000, 1000)
    cfg.chmod(0o600)
    overlay = {'services': {
        'api': {'env_file':['./host-control/api.env']},
        'prosody': {'environment': {'XMPP_MUC_MODULES':'muc_jwt_owner,muc_host_transfer'}, 'volumes': [
            './host-control/ca.crt:/host-control/ca.crt:ro',
            './host-control/prosody.cfg.lua:/defaults/prosody.cfg.lua:ro',
            './host-control/zz-cloudmeet-host-control.cfg.lua:/config/conf.d/zz-cloudmeet-host-control.cfg.lua:ro']},
        'gateway': {'volumes': [
            './host-control/gateway.crt:/host-control/gateway.crt:ro',
            './host-control/private/gateway.key:/host-control/gateway.key:ro']}
    }}
    (out/'compose.json').write_text(json.dumps(overlay, indent=2)+'\n')
    (out/'gateway-internal.caddy').write_text('''https://gateway:9443 {
    tls /host-control/gateway.crt /host-control/gateway.key
    @allowed {
        method POST
        path /internal/host-role/v1/check /internal/host-role/v1/rotate /internal/host-role/v1/complete /internal/host-role/v1/status /internal/host-role/v1/rebind /internal/host-role/v1/claim /internal/host-role/v1/reclaim
    }
    handle @allowed {
        rewrite * /mapi{uri}
        reverse_proxy api:9000
    }
    handle {
        respond 404
    }
}
''')
    print('Prepared disabled host-control overlay; no services changed. Review, validate, then activate explicitly.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--prosody-container', required=True)
    args = parser.parse_args()
    prepare(args.root, args.prosody_container)
