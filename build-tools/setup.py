#!/usr/bin/env python3
"""Combine a public server archive and private adjacent cert.tar.gz on target only."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile


def extract_server(archive):
    expected=Path(str(archive)+'.sha256').read_text().split()[0]
    digest=hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    if digest.hexdigest()!=expected: raise ValueError('Server archive checksum mismatch')
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers();roots=set();seen=set()
        for member in members:
            parts=PurePosixPath(member.name).parts
            if (not parts or parts[0] in ('.','..','/') or '..' in parts or '\\' in member.name
                    or not (member.isfile() or member.isdir()) or member.name in seen):
                raise ValueError('Unsafe server archive member')
            roots.add(parts[0]);seen.add(member.name)
        if len(roots)!=1: raise ValueError('Expected one server archive root')
        root=archive.parent/next(iter(roots))
        if root.exists() or root.is_symlink(): raise FileExistsError('Refusing existing installation directory')
        root.mkdir(mode=0o700)
        for member in members:
            destination=archive.parent.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir(): destination.mkdir(parents=True,exist_ok=True)
            else:
                destination.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(member) as source,destination.open('xb') as output: shutil.copyfileobj(source,output)
                # Preserve executable intent for extensionless binaries as well as
                # scripts, never archive setuid/setgid/sticky or writable bits.
                destination.chmod(0o755 if member.mode & 0o111 else 0o644)
    return root


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-package',type=Path,required=True)
    parser.add_argument('--verify-origin',required=True)
    args=parser.parse_args()
    if os.geteuid()!=0: raise ValueError('Run setup.py with sudo/root')
    os.umask(0o077)
    archive=args.server_package.resolve();cert=archive.parent/'cert.tar.gz'
    if not cert.is_file() or cert.is_symlink(): raise ValueError('Adjacent cert.tar.gz required')
    root=extract_server(archive)
    # Validate every public package file before importing any extracted Python.
    listed=set()
    for line in (root/'SHA256SUMS').read_text().splitlines():
        wanted,name=line.split('  ',1)
        parts=PurePosixPath(name).parts
        if not parts or parts[0]=='/' or '..' in parts or '\\' in name or name in listed:
            raise ValueError('Unsafe package checksum member')
        listed.add(name);path=root.joinpath(*parts)
        actual=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''): actual.update(chunk)
        if actual.hexdigest()!=wanted: raise ValueError('Package checksum mismatch: '+name)
    if {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}!=listed|{'SHA256SUMS'}:
        raise ValueError('Unlisted public package files')
    spec=importlib.util.spec_from_file_location('certificate',root/'certificate.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    shutil.copyfile(cert,root/'cert.tar.gz');(root/'cert.tar.gz').chmod(0o600)
    module.preflight(root,args.verify_origin)
    module.unpack_certificate(root/'cert.tar.gz',root/'cert')
    subprocess.run([sys.executable,'-B',str(root/'deploy.py'),'--first-install',
                    '--verify-origin',args.verify_origin],check=True,cwd=str(root))


if __name__=='__main__': main()
