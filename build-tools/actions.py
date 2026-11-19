#!/usr/bin/env python3
"""Bounded Actions dispatch/status interface; token file stays outside repositories."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import urllib.request

REPOSITORY='stevenzxs/cloudemeet-deploy'


def api(token,path,data=None):
    request=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
                 'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.urlopen(request,timeout=45) as response:
        payload=response.read()
        return json.loads(payload) if payload else {'http_status':response.status}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-file',type=Path,required=True)
    parser.add_argument('--record',type=Path,required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    dispatch=sub.add_parser('dispatch')
    dispatch.add_argument('--commit',required=True)
    dispatch.add_argument('--scope',choices=['server','joint'],default='server')
    dispatch.add_argument('--publish',action='store_true')
    status=sub.add_parser('status');status.add_argument('--run-id',type=int,required=True)
    args=parser.parse_args();os.umask(0o077)
    if args.token_file.is_symlink() or not args.token_file.is_file():raise ValueError('Invalid token file')
    if os.name=='posix' and args.token_file.stat().st_mode & 0o077:raise ValueError('Token file too open')
    token=args.token_file.read_text().strip()
    if not token:raise ValueError('Empty token')
    if args.command=='dispatch':
        if not re.fullmatch('[0-9a-f]{40}',args.commit):raise ValueError('Full reviewed commit required')
        if args.record.exists():raise ValueError('Existing task record; inspect status instead of redispatch')
        ref=api(token,'/git/ref/heads/main')
        if ref['object']['sha']!=args.commit:raise ValueError('Reviewed main moved; dispatch refused')
        record={'repository':REPOSITORY,'configuration_commit':args.commit,'scope':args.scope,
                'requested_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'status':'DISPATCH_REQUEST_PENDING','architecture':'amd64','publish':args.publish}
        # Persist intent before request: ambiguous network failure must not auto-redispatch.
        with args.record.open('x') as out:json.dump(record,out,indent=2)
        workflow='build-joint.yml' if args.scope=='joint' else 'build-package.yml'
        response=api(token,'/actions/workflows/'+workflow+'/dispatches',{
            'ref':'main','inputs':{'material_commit':args.commit,
                                'architecture':'amd64','publish_images':args.publish}})
        record.update(status='DISPATCH_ACCEPTED_RUN_NOT_YET_IDENTIFIED',response=response)
    else:
        run=api(token,'/actions/runs/'+str(args.run_id))
        record=json.loads(args.record.read_text())
        if run['head_sha']!=record['configuration_commit'] or run['event']!='workflow_dispatch':
            raise ValueError('Run source/event mismatch')
        record.update(run_id=run['id'],url=run['html_url'],run_status=run['status'],
                      conclusion=run['conclusion'],attempt=run['run_attempt'])
        if run['status']=='completed':
            record['artifacts']=api(token,'/actions/runs/'+str(args.run_id)+'/artifacts?per_page=100')['artifacts']
            record['status']='RUN_COMPLETED_ARTIFACT_VERIFICATION_PENDING'
    args.record.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()
