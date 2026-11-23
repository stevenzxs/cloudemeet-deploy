#!/usr/bin/env python3
"""Explicit extra node: pull published digests, export offline first/upgrade material."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def require_clean_configuration():
    repo=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip():
        raise ValueError('Offline export requires clean reviewed configuration checkout')
    return subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()


def export(source,record,destination):
    export_commit=require_clean_configuration()
    material=load('public_material',Path(__file__).with_name('online-material.py'))
    material.require_public_source(source)
    verifier=load('export_verifier',source/'install.py')
    transport=load('export_transport',Path(__file__).parent/'offline-runtime/image_transport.py')
    verifier.verify_checksums(source)
    manifest=json.loads((source/'candidate.json').read_text())
    transport.require_material(record,manifest)
    if destination.exists():raise FileExistsError('Refusing existing offline batch')
    archive=destination.with_name(destination.name+'.tar.gz')
    setup=destination.parent/'setup.py'
    for path in (archive,Path(str(archive)+'.sha256'),setup,Path(str(setup)+'.sha256')):
        if path.exists():raise FileExistsError('Refusing existing offline delivery file: '+str(path))
    # A real matching Linux engine and pull permission are required; no rebuild fallback.
    transport.pull_images(record)
    transport.bind_local_tags(record,manifest)
    shutil.copytree(source,destination,ignore=shutil.ignore_patterns('SHA256SUMS','images'))
    (destination/'images').mkdir()
    archives={}
    for service,item in record['images'].items():
        path=destination/'images'/(service+'.tar.gz')
        raw=path.with_suffix('.raw')
        subprocess.run(['docker','save','--output',str(raw),manifest['images'][service][0]],check=True,timeout=600)
        with raw.open('rb') as stream,gzip.open(path,'wb') as compressed:shutil.copyfileobj(stream,compressed)
        raw.unlink()  # Only this script's temporary, successful export.
        provenance_path=destination/'provenance'/(service+'.json')
        provenance=json.loads(provenance_path.read_text())
        provenance.update(archive=path.name,bytes=path.stat().st_size,sha256=verifier.sha256_file(path))
        verifier.verify_image_archive(path,provenance)
        provenance_path.write_text(json.dumps(provenance,indent=2)+'\n')
        archives[service]={'tag':provenance['tag'],'image_id':item['image_id'],
                          'file':path.name,'bytes':provenance['bytes'],'sha256':provenance['sha256']}
    manifest.update(image_transport='archive',image_archives=archives,
                    offline_export_configuration_commit=export_commit)
    (destination/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (destination/'registry.json').write_text(json.dumps(record,indent=2)+'\n')
    (destination/'INSTALL.md').write_text('''# Explicit offline first installation / image-only upgrade

No target pull or build. Existing matching Linux Docker Engine is required;
Docker Engine/host OS installation is NOT included. Native Compose is included.
Verify external archive SHA256 and all internal SHA256SUMS before execution.
First installation: setup.py --server-package <offline archive> --verify-origin
<matching client origin> --target-env <absolute external target.env>, with the
private target leaf certificate bundle supplied separately as adjacent cert.tar.gz.
Existing instances must NOT use first-install or delete secrets/data to retry.
Upgrade: online_update.py --offline-package <extracted directory> --candidate
<directory/candidate.json> --registry <directory/registry.json> --registry-sha256
<trusted hash> --root <actual existing instance> --project <actual project>
--target-env <external target.env> --verify-origin <origin> --ca <public root>.
Read-only unless separately authorized --apply. Requires identical external
patches, exact ownership, idle meetings, consistent backup and image-ID rollback.
Configuration/schema migration is not automatically supported. Never overwrite
data, secrets, certificate/CA volumes or unrelated services. Installation, client
and non-P2P JVB media acceptance remain separate from package integrity.
''')
    sums=destination/'SHA256SUMS'
    sums.write_text(''.join(verifier.sha256_file(p)+'  '+p.relative_to(destination).as_posix()+'\n'
                           for p in sorted(destination.rglob('*')) if p.is_file() and p!=sums))
    verifier.verify_checksums(destination);verifier.require_ready(manifest)
    archive=destination.with_name(destination.name+'.tar.gz')
    if archive.exists():raise FileExistsError('Refusing existing offline archive')
    with tarfile.open(archive,'w:gz') as tar:tar.add(destination,arcname=destination.name)
    load('export_archive_check',Path(__file__).with_name('online-material.py')).verify_archive(archive)
    Path(str(archive)+'.sha256').write_text(verifier.sha256_file(archive)+'  '+archive.name+'\n')
    shutil.copyfile(Path(__file__).with_name('setup.py'),setup)
    Path(str(setup)+'.sha256').write_text(verifier.sha256_file(setup)+'  setup.py\n')
    return archive


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='Verified extracted online public material')
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--registry-sha256',required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    if hashlib.sha256(args.registry.read_bytes()).hexdigest()!=args.registry_sha256:
        raise ValueError('Untrusted registry record')
    print(export(args.source,json.loads(args.registry.read_text()),args.destination))
