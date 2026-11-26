#!/usr/bin/env python3
"""Report missing deployment choices after publication; never connects or deploys."""
import argparse
import json
from urllib.parse import urlsplit


def plan(values,client_origin=None):
    values={k:v for k,v in values.items() if v}
    if values.get('mode') not in (None,'first','upgrade'):
        raise ValueError('Choose first or upgrade; reset is not first installation')
    origin=values.get('origin')
    if origin:
        url=urlsplit(origin)
        port=443 if url.port is None else url.port
        if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None
                or url.path or url.query or url.fragment or not 1<=port<=65535
                or any(c.isspace() for c in origin)):
            raise ValueError('Complete HTTPS origin without path required')
        if client_origin and origin!=client_origin:
            raise ValueError('Deployment origin differs from built client origin')
    required=['mode','server','origin']
    if values.get('mode')=='upgrade':required+=['root','project','target_env']
    missing=[k for k in required if not values.get(k)]
    return {'status':'INPUT_REQUIRED' if missing else 'TARGET_PREFLIGHT_REQUIRED',
            'missing':missing,'selection':values,
            'prompts':{'mode':'首次部署(first)还是升级部署(upgrade)？',
                       'server':'部署服务器地址（与访问入口分开）？',
                       'origin':'完整访问入口（协议、主机、端口；须匹配已构建客户端）？'},
            'limitations':'No SSH or apply; inspect target ownership before selecting an executor.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('mode','server','origin','root','project','target-env','client-origin'):
        parser.add_argument('--'+key)
    args=vars(parser.parse_args());client=args.pop('client_origin')
    print(json.dumps(plan(args,client),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
