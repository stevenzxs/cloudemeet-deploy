"""Approval assertions, never an alternative source of product configuration."""
import json
import os
import ipaddress
from pathlib import Path
import urllib.parse


def parse(text):
    result={}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1);key=key.strip()
        if key in result:raise ValueError('Duplicate client configuration: '+key)
        result[key]=value.strip()
    return result


def validate(config,expected_mode,expected_origin):
    if expected_mode not in ('private-ca','caddy-public-acme') or not expected_origin:
        raise ValueError('Explicit approved TLS mode and user origin required before allocation')
    try:
        parsed=urllib.parse.urlsplit(expected_origin)
        scheme=parsed.scheme.lower()
        host=parsed.hostname
        port=parsed.port or (443 if scheme=='https' else 80)
    except ValueError as exc:
        raise ValueError('Invalid user origin') from exc
    if (scheme not in ('https','http') or not host or parsed.username or parsed.password
            or parsed.path not in ('','/') or parsed.query or parsed.fragment
            or any(c.isspace() for c in expected_origin) or '\\' in expected_origin
            or not 1<=port<=65535):raise ValueError('Invalid user origin')
    authority_host=f'[{host}]' if ':' in host else host
    default_port=443 if scheme=='https' else 80
    origin=f'{scheme}://{authority_host}'+(f':{port}' if parsed.port is not None else '')
    mode=expected_mode
    if 'TLS_MODE' in config and config['TLS_MODE'] not in ('private-ca','caddy-public-acme'):
        raise ValueError('Invalid TLS mode in skill configuration')
    effective=dict(config)
    if mode=='caddy-public-acme':effective.pop('CLIENT_CA_FILE',None)
    elif not effective.get('CLIENT_CA_FILE'):effective['CLIENT_CA_FILE']='client-ca.crt'
    if mode=='caddy-public-acme':
        try:ipaddress.ip_address(host)
        except ValueError:pass
        else:raise ValueError('Public ACME requires DNS hostname')
        if scheme!='https' or port!=443 or '.' not in host or effective.get('CLIENT_CA_FILE'):
            raise ValueError('Public ACME requires DNS HTTPS/443 without private trust')
    elif not effective.get('CLIENT_CA_FILE'):
        raise ValueError('Private mode requires client CA file')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    return {'tls_mode':mode,'origin':origin,'scheme':scheme,'host':host,'port':port,
            'site_domain':host,'site_scheme':scheme,'site_port':str(port),
            'client_ca_file': effective.get('CLIENT_CA_FILE') or None}


def approved_contract():
    root=Path(__file__).resolve().parents[1]
    contract=validate(parse((root/'config/client.env').read_text(encoding='utf-8')),
                      os.environ.get('EXPECTED_TLS_MODE'),os.environ.get('EXPECTED_ORIGIN'))
    encoded=os.environ.get('ORIGIN_CONTRACT_JSON')
    if encoded:
        try:
            supplied=json.loads(encoded)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError('Invalid approved origin contract JSON') from exc
        if supplied.get('origin')!=contract['origin'] or supplied.get('tls_mode')!=contract['tls_mode']:
            raise ValueError('User origin differs from approved origin contract')
    from origin_contract import normalize_origin
    origin=normalize_origin(contract['origin'])
    contract['addresses']=origin['addresses']
    return contract


def require_evidence(contract,mode,origin,ca):
    if mode!=contract['tls_mode'] or origin!=contract['origin']:
        raise ValueError('Final material differs from approved TLS contract')
    if mode=='caddy-public-acme' and ca is not None:
        raise ValueError('Public material contains private CA trust')


if __name__=='__main__':print(json.dumps(approved_contract(),sort_keys=True))
