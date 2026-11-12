#!/usr/bin/env bash
# One build/assembly entry. Docker is used only on the native Actions runner.
set -euo pipefail
tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd "$tools/.." && pwd)
die() { printf '%s\n' "$*" >&2; exit 1; }
case "${1:-}" in
    -h|--help) printf '%s\n' 'Usage: package.sh build SERVICE | assemble' 'Run on native aarch64 GitHub Actions; see build-tools/README.md.'; exit 0 ;;
    build|assemble) ;;
    *) die 'Usage: package.sh build SERVICE | assemble' ;;
esac
: "${VERSION:?Set VERSION}"
: "${BATCH:?Set BATCH to version/run/attempt identity}"
[[ $VERSION =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$ ]] || die 'Invalid version'
[[ $BATCH =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,110}$ ]] || die 'Invalid batch'
[[ $(uname -m) == aarch64 ]] || die 'Native aarch64 runner required'
: "${GITHUB_RUN_ID:?Run through GitHub Actions}"
: "${GITHUB_RUN_ATTEMPT:?Missing workflow attempt}"
: "${GITHUB_SHA:?Missing workflow commit}"
[[ $BATCH == "$VERSION-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT" ]] || die 'Batch identity mismatch'
deployment_commit=$(git -C "$repo" rev-parse HEAD)
[[ $deployment_commit == "$GITHUB_SHA" ]] || die 'Workflow commit mismatch'
(cd "$repo"; sha256sum -c build-tools/inputs.sha256)
export VERSION BATCH DEPLOYMENT_COMMIT="$deployment_commit"

source_field() {
    python3 - "$tools/sources.json" "$1" "$2" <<'PY'
import json, sys
sources = json.load(open(sys.argv[1]))
record = sources['lifecycle'] if sys.argv[2] == 'lifecycle' else sources['services'][sys.argv[2]]
print(record[sys.argv[3]])
PY
}

checkout_source() {
    local service=$1 destination=$2 commit url
    commit=$(source_field "$service" commit)
    url=$(source_field "$service" repository)
    [[ $commit =~ ^[0-9a-f]{40}$ && $url == https://github.com/* ]] || die 'Invalid source lock'
    git init -q "$destination"
    git -C "$destination" fetch --depth=1 "$url" "$commit"
    git -C "$destination" checkout --detach FETCH_HEAD
    [[ $(git -C "$destination" rev-parse HEAD) == "$commit" ]] || die 'Source identity mismatch'
}

build_service() (
    service=${1:?Missing service}
    case "$service" in gateway|app-web|api|web|prosody|jicofo|jvb) ;; *) die 'Unknown service';; esac
    work=$(mktemp -d)
    trap 'rm -rf -- "$work"' EXIT
    mkdir -p "$work/context" "$repo/output"
    mkdir "$repo/output/$service"
    checkout_source "$service" "$work/source"
    SOURCE_COMMIT=$(source_field "$service" commit)
    export SOURCE_COMMIT SERVICE="$service"
    context=$work/context
    source=$work/source
    # Build inputs, source state and resolved bases are retained with the image.
    git -C "$source" status --porcelain > "$work/source-before.txt"
    bases=$work/bases.jsonl
    export BASE_RECORDS="$bases"
    resolve_base() {
        local ref=$1 resolved
        docker pull --platform linux/arm64 "$ref" >&2
        docker image inspect "$ref" | python3 -c '
import json, os, sys
i=json.load(sys.stdin)[0]
assert (i["Os"],i["Architecture"]) == ("linux","arm64"), "Wrong base platform"
with open(os.environ["BASE_RECORDS"],"a") as f:
    f.write(json.dumps({"requested":sys.argv[1],"id":i["Id"],"digests":i["RepoDigests"]})+"\n")
print(i["RepoDigests"][0])' "$ref"
    }
    lifecycle_base=ghcr.io/jitsi/base@sha256:48f5eb97cdb15306f4ae0f1d924f6485f3f514d6781aeb86e36601a67aa73781
    debian_base=debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
    labels=(--label "org.opencontainers.image.version=$VERSION"
        --label "org.opencontainers.image.revision=$SOURCE_COMMIT"
        --label "io.cloudmeet.batch=$BATCH" --label "io.cloudmeet.service=$service"
        --label "io.cloudmeet.deployment=$deployment_commit")
    java17=${JAVA_HOME_17_ARM64:-/usr/lib/jvm/temurin-17-jdk-arm64}
    case "$service" in
        web|app-web)
            builder=$(resolve_base node:24-trixie)
            command='npm ci; npm run build'
            [[ $service != web ]] || command='npm ci; make all'
            build_env=()
            # This approved instance package follows its host origin, never the 118 default.
            [[ $service != app-web ]] || build_env=(-e VITE_JITSI_SERVER=same-origin)
            docker run --rm --platform linux/arm64 --user "$(id -u):$(id -g)" \
                -e HOME=/tmp "${build_env[@]}" -v "$source:/src" -w /src "$builder" bash -euc "$command"
            if [[ $service == app-web ]]; then
                runtime=$(resolve_base nginx:1.30.6-alpine@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311)
                cp -a "$source/dist" "$context/dist"
                grep -rq 'same-origin' "$context/dist" || die 'Missing same-origin application configuration'
                cp "$tools/templates/nginx.conf" "$context/nginx.conf"
            else
                runtime=$(resolve_base "$lifecycle_base")
                checkout_source lifecycle "$work/lifecycle"
                cp -a "$work/lifecycle/web/rootfs" "$context/rootfs"
                mkdir -p "$context/payload/css" "$context/payload/resources"
                cp "$source/"*.html "$source/"*.js "$context/payload/"
                for directory in fonts images libs static sounds lang; do
                    cp -a "$source/$directory" "$context/payload/$directory"
                done
                cp "$source/css/all.css" "$context/payload/css/"
                cp "$source/LICENSE" "$context/payload/"
                cp "$source/resources/"*.txt "$context/payload/resources/"
                printf 'User-agent: *\nDisallow: /\n' > "$context/payload/robots.txt"
            fi
            ;;
        api)
            runtime=$(resolve_base eclipse-temurin:17-jre-jammy)
            (export JAVA_HOME="$java17" PATH="$java17/bin:$PATH"; cd "$source"; mvn -B -ntp -DskipTests package)
            jars=("$source/target/"*.jar)
            [[ ${#jars[@]} == 1 && -s ${jars[0]} ]] || die 'Expected one API jar'
            cp "${jars[0]}" "$context/app.jar"
            ;;
        gateway)
            runtime=$(resolve_base "$debian_base")
            builder=$(resolve_base golang:1.27-trixie)
            docker run --rm --platform linux/arm64 --user "$(id -u):$(id -g)" \
                -e HOME=/tmp -e GOPATH=/tmp/go -e GOCACHE=/tmp/go-cache \
                -v "$source:/src" -w /src "$builder" bash -euc \
                'export GOTOOLCHAIN=local; go mod download; go mod verify; CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -p 2 -trimpath -o caddy-candidate ./cmd/caddy'
            cp "$source/caddy-candidate" "$context/caddy"
            ;;
        prosody)
            resolve_base "$lifecycle_base" > /dev/null
            resolve_base "$debian_base" > /dev/null
            # Intermediate tag is unique to this batch and can never be an older fallback.
            docker build --platform linux/arm64 --progress plain \
                -f "$tools/docker/prosody-core.Dockerfile" -t "cloudmeet-build/prosody-core:$BATCH" "$source"
            mkdir -p "$source/runtime-downloads"
            curl -fLsS --retry 3 https://raw.githubusercontent.com/aiq/basexx/v0.4.1/lib/basexx.lua -o "$source/runtime-downloads/basexx.lua"
            curl -fLsS --retry 3 https://raw.githubusercontent.com/kikito/inspect.lua/v3.1.3/inspect.lua -o "$source/runtime-downloads/inspect.lua"
            (cd "$source/runtime-downloads"; printf '%s\n' \
                '6f8241efd8ea7affafdd00f433c317ed88151d87089b13ae4f94a421d4789445  basexx.lua' \
                '72de901ac081bf927640e367b52146a18ed4f628eab7880dd32f1a6442b9fe6f  inspect.lua' | sha256sum -c -)
            docker build --platform linux/arm64 --progress plain "${labels[@]}" \
                --build-arg "PROSODY_CORE=cloudmeet-build/prosody-core:$BATCH" \
                -f "$tools/docker/prosody-service.Dockerfile" -t "cloudmeet/prosody:$BATCH" "$source"
            ;;
        jicofo|jvb)
            resolve_base "$lifecycle_base" > /dev/null
            checkout_source lifecycle "$work/lifecycle"
            (export JAVA_HOME="$java17" PATH="$java17/bin:$PATH"; cd "$source"; mvn -B -ntp -DskipTests package)
            archives=("$source/$service/target/"*-archive.zip)
            [[ ${#archives[@]} == 1 && -s ${archives[0]} ]] || die 'Expected one distribution archive'
            mkdir "$context/unpack"
            unzip -q "${archives[0]}" -d "$context/unpack"
            jarname=jicofo.jar
            [[ $service != jvb ]] || jarname=jitsi-videobridge.jar
            mapfile -t jars < <(find "$context/unpack" -name "$jarname" -type f)
            [[ ${#jars[@]} == 1 ]] || die 'Expected one application jar'
            mv "$(dirname "${jars[0]}")" "$context/distribution"
            cp -a "$work/lifecycle/$service/rootfs" "$context/rootfs"
            docker build --platform linux/arm64 --progress plain "${labels[@]}" \
                --build-arg "SERVICE=$service" -f "$tools/docker/java-service.Dockerfile" \
                -t "cloudmeet/$service:$BATCH" "$context"
            ;;
    esac
    case "$service" in
        web|app-web|api|gateway)
            docker build --platform linux/arm64 --progress plain "${labels[@]}" \
                --build-arg "RUNTIME_BASE=$runtime" --build-arg "SOURCE_COMMIT=$SOURCE_COMMIT" \
                -f "$tools/docker/$service.Dockerfile" -t "cloudmeet/$service:$BATCH" "$context"
            ;;
    esac
    # Build outputs may be untracked; tracked source/config/lock changes are forbidden.
    git -C "$source" diff --exit-code
    git -C "$source" diff --cached --exit-code
    [[ ! -s $work/source-before.txt ]] || die 'Dirty checkout before build'
    docker image inspect "cloudmeet/$service:$BATCH" > "$work/image.json"
    docker save "cloudmeet/$service:$BATCH" | gzip -1 > "$repo/output/$service/$service.tar.gz"
    python3 - "$work" "$repo/output/$service" "$tools/sources.json" <<'PY'
import hashlib, json, os, pathlib, sys
work, out, sourcefile = map(pathlib.Path, sys.argv[1:])
service = os.environ['SERVICE']
info = json.loads((work/'image.json').read_text())[0]
labels = info['Config']['Labels']
assert (info['Os'], info['Architecture']) == ('linux', 'arm64'), 'Wrong image architecture'
assert labels['io.cloudmeet.batch'] == os.environ['BATCH'], 'Batch identity mismatch'
assert labels['org.opencontainers.image.revision'] == os.environ['SOURCE_COMMIT'], 'Source identity mismatch'
archive = out/(service+'.tar.gz')
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()
sources=json.loads(sourcefile.read_text())
record={'service':service,'version':os.environ['VERSION'],'batch':os.environ['BATCH'],
        'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
         'workflow_commit':os.environ['GITHUB_SHA'],'source_dirty':False,
         'build_overrides':{'VITE_JITSI_SERVER':'same-origin'} if service=='app-web' else {},
        'deployment_commit':os.environ['DEPLOYMENT_COMMIT'],'source':sources['services'][service],
         'lifecycle':sources['lifecycle'] if service in ('web','jicofo','jvb') else None,
         'source_config_sha256':{p:digest(work/'source'/p) for p in
                                  ('package-lock.json','.env','pom.xml','go.mod','go.sum')
                                  if (work/'source'/p).is_file()},
        'tag':'cloudmeet/'+service+':'+os.environ['BATCH'],'image_id':info['Id'],
         'platform':'linux/arm64','archive':archive.name,'bytes':archive.stat().st_size,
         'runtime_user':info['Config'].get('User',''),
        'sha256':digest(archive),'bases':[json.loads(line) for line in (work/'bases.jsonl').read_text().splitlines()],
        'context_sha256':{p.relative_to(work/'context').as_posix():digest(p)
                          for p in (work/'context').rglob('*') if p.is_file()},
        'acceptance':'NOT_RUN_PACKAGING_ONLY'}
(out/(service+'.json')).write_text(json.dumps(record,indent=2)+'\n')
PY
)

assemble_package() {
    target_exports=$(python3 -B "$repo/config/target.py" "$repo/config/target.env")
    eval "$target_exports"
    PUBLIC_ORIGIN=$PUBLIC_URL
    export PUBLIC_ORIGIN HTTP_PORT MEDIA_PORT
    output="$repo/output/cloudmeet-$BATCH-aarch64"
    [[ ! -e $output ]] || die 'Output batch already exists'
    mkdir -p "$output/bin" "$output/images" "$output/provenance"
    # Nothing is uploaded from staging if any later check fails.
    printf '%s\n' '{"status":"ASSEMBLING_NOT_COMPLETE"}' > "$output/candidate.json"
    # Official Compose, version-locked and checked against the official checksum.
    compose_version=v2.39.4
    compose_url="https://github.com/docker/compose/releases/download/$compose_version/docker-compose-linux-aarch64"
    curl -fLsS --retry 3 "$compose_url" -o "$output/bin/docker-compose"
    curl -fLsS --retry 3 "$compose_url.sha256" -o "$output/provenance/compose.sha256"
    expected=$(awk '{print $1}' "$output/provenance/compose.sha256")
    [[ $expected =~ ^[0-9a-f]{64}$ ]] || die 'Invalid Compose checksum'
    printf '%s  %s\n' "$expected" "$output/bin/docker-compose" | sha256sum -c -
    chmod 0755 "$output/bin/docker-compose"
    "$output/bin/docker-compose" version
    cp "$tools/offline-runtime/"*.py "$output/"
    cp -a "$repo/patches" "$output/patches"
    cp "$tools/sources.json" "$output/provenance/sources.json"
    cp "$tools/inputs.sha256" "$output/provenance/deployment-inputs.sha256"
    cp "$repo/incoming/artifacts.json" "$output/provenance/actions-artifacts.json"
    export PACKAGE_DIR="$output" COMPOSE_URL="$compose_url" COMPOSE_VERSION="$compose_version"
    python3 -B - "$repo" <<'PY'
import hashlib, importlib.util, json, os, pathlib, shutil, sys, urllib.parse
sys.dont_write_bytecode=True
repo=pathlib.Path(sys.argv[1]); out=pathlib.Path(os.environ['PACKAGE_DIR'])
spec=importlib.util.spec_from_file_location('verifier',out/'install.py')
verifier=importlib.util.module_from_spec(spec); spec.loader.exec_module(verifier)
services=('gateway','app-web','api','web','prosody','jicofo','jvb')
sources=json.loads((repo/'build-tools/sources.json').read_text())
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
target_spec=importlib.util.spec_from_file_location('target_config',repo/'config/target.py')
target_module=importlib.util.module_from_spec(target_spec); target_spec.loader.exec_module(target_module)
target=target_module.load_target(repo/'config/target.env')
origin=target['PUBLIC_URL']; url=urllib.parse.urlsplit(origin)
if (url.scheme!='https' or not url.hostname or url.username or url.password
        or url.path not in ('','/') or url.query or url.fragment):
    raise ValueError('An HTTPS origin without path or credentials is required')
host=url.hostname
if ':' in host: raise ValueError('This package entry currently supports IPv4/DNS hosts only')
https_port=int(target['HTTPS_PORT']); http_port=int(target['HTTP_PORT']); media_port=int(target['MEDIA_PORT'])
if any(not 1<=p<=65535 for p in (https_port,http_port,media_port)) or https_port==http_port:
    raise ValueError('Invalid port configuration')
records={}
for s in services:
    record=json.loads((repo/'incoming'/s/(s+'.json')).read_text())
    if (record['batch']!=os.environ['BATCH'] or record['version']!=os.environ['VERSION']
            or record['deployment_commit']!=os.environ['DEPLOYMENT_COMMIT'] or record['service']!=s
            or record['run_id']!=os.environ['GITHUB_RUN_ID'] or record['attempt']!=os.environ['GITHUB_RUN_ATTEMPT']):
        raise ValueError('Batch identity mismatch: '+s)
    if record['source']!=sources['services'][s]: raise ValueError('Source identity mismatch: '+s)
    if record['platform']!='linux/arm64' or record['archive']!=s+'.tar.gz': raise ValueError('Wrong platform/archive')
    archive=repo/'incoming'/s/record['archive']
    if archive.stat().st_size!=record['bytes'] or digest(archive)!=record['sha256']:
        raise ValueError('Archive integrity failure: '+s)
    verifier.verify_image_archive(archive, record)
    shutil.copyfile(archive,out/'images'/record['archive'])
    shutil.copyfile(repo/'incoming'/s/(s+'.json'),out/'provenance'/(s+'.json'))
    records[s]=record
common={'PUBLIC_URL':'${PUBLIC_URL:?required}','XMPP_DOMAIN':'meet.jitsi','XMPP_AUTH_DOMAIN':'auth.meet.jitsi',
 'XMPP_MUC_DOMAIN':'muc.meet.jitsi','XMPP_INTERNAL_MUC_DOMAIN':'internal-muc.meet.jitsi',
 'XMPP_SERVER':'xmpp.meet.jitsi','XMPP_PORT':'5222','JVB_BREWERY_MUC':'jvbbrewery',
 'JICOFO_AUTH_USER':'focus','JVB_AUTH_USER':'jvb','JICOFO_AUTH_PASSWORD':'${JICOFO_AUTH_PASSWORD:?required}',
 'JVB_AUTH_PASSWORD':'${JVB_AUTH_PASSWORD:?required}','ENABLE_AUTH':'1','AUTH_TYPE':'jwt',
 'JWT_APP_ID':'zhsz','JWT_APP_SECRET':'${JWT_APP_SECRET:?required}','JWT_ALLOW_EMPTY':'1',
 'ENABLE_AUTO_OWNER':'0','XMPP_MUC_MODULES':'muc_jwt_owner','ENABLE_P2P':'0',
 'ENABLE_XMPP_WEBSOCKET':'1','JICOFO_MAX_MEMORY':'256m','JVB_MAX_MEMORY':'384m',
 'VIDEOBRIDGE_MAX_MEMORY':'384m','JVB_ADVERTISE_IPS':'${JVB_ADVERTISE_IPS:-}',
  'JVB_PORT':'${JVB_PORT:?required}','TZ':'Asia/Shanghai'}
common['BOSH_RELATIVE']='1'
configs={s:{'image':records[s]['tag'],'pull_policy':'never','restart':'unless-stopped',
            'mem_limit':'640m','pids_limit':512,'networks':{'meeting':{}}} for s in services}
public_settings=target_module.read_env(repo/'config/jitsi.env')
# Runtime contracts remain required, but their maintained public values come from jitsi.env.
for key in set(common) & set(public_settings):
    common[key]=public_settings[key]
for key in ('ENABLE_COLIBRI_WEBSOCKET','CODEC_ORDER_JVB','CODEC_ORDER_JVB_MOBILE','JICOFO_REST_PORT','JVB_COLIBRI_PORT'):
    if key in public_settings: common[key]=public_settings[key]
for s in ('web','prosody','jicofo','jvb'):
    configs[s]['environment']=dict(common)
    configs[s]['volumes']=['./data/jitsi/'+s+':/config']
    if s!='prosody': configs[s]['depends_on']=['prosody']
configs['prosody']['networks']['meeting']['aliases']=['xmpp.meet.jitsi']
configs['prosody']['environment']['XMPP_MUC_MODULES']='muc_jwt_owner,muc_host_transfer'
configs['prosody']['environment']['CLOUDMEET_HOST_CONTROL_CA']='/host-control/ca.crt'
configs['prosody']['volumes']=['./data/jitsi/prosody/config:/config',
 './data/jitsi/storage/prosody:/var/lib/prosody',
  './data/jitsi/prosody/prosody-plugins-custom:/prosody-plugins-custom:ro',
  './data/host-control/ca.crt:/host-control/ca.crt:ro']
configs['web']['environment'].update(DISABLE_HTTPS='1',ENABLE_LETSENCRYPT='0',
 ENABLE_HTTP_REDIRECT='0',NGINX_WORKER_PROCESSES='1',XMPP_BOSH_URL_BASE='http://xmpp.meet.jitsi:5280')
configs['jvb']['ports']=['${MEDIA_PORT:?required}:${JVB_PORT:?required}/udp']
configs['api'].update(mem_limit='384m',environment={'JITSI_TOKEN_APP_ID':'zhsz',
 'JITSI_ROLE_CHECK_SECRET':'${JITSI_ROLE_CHECK_SECRET:?required}',
 'JITSI_TOKEN_APP_SECRET':'${JWT_APP_SECRET:?required}','JITSI_TOKEN_DOMAIN':'meet.jitsi',
 'JITSI_MEET_DB_URL':'jdbc:sqlite:/app/data/jitsi-meet-api.sqlite.db','BANNER_LOGO_DIRECTORY':'/data/banner-logos'},
 volumes=['./data/api:/app/data','./data/logos:/data/banner-logos'])
configs['app-web'].update(depends_on=['api'],volumes=['./data/logos:/data/banner-logos:ro'])
configs['gateway'].update(depends_on=['app-web','web'],environment={'SITE_HOST':'${SITE_HOST:?required}',
 'PUBLIC_URL':'${PUBLIC_URL:?required}'},
  ports=['${HTTPS_PORT:?required}:443','${HTTP_PORT:?required}:80'],
  volumes=['./Caddyfile:/etc/caddy/Caddyfile:ro','caddy_data:/data','caddy_config:/config',
           './data/host-control/gateway.crt:/host-control/gateway.crt:ro',
           './data/host-control/gateway.key:/host-control/gateway.key:ro'])
compose={'name':'cloudmeet-'+os.environ['BATCH'].lower().replace('_','-'),
 'services':configs,'networks':{'meeting':{}},'volumes':{'caddy_data':{},'caddy_config':{}}}
(out/'jitsi-base.yaml').write_text(json.dumps(compose,indent=2)+'\n')
for name in ('docker-compose.yml','source-images.yaml'): (out/name).write_text('services: {}\n')
shutil.copyfile(repo/'config/jitsi.env',out/'jitsi.env')
shutil.copyfile(repo/'config/target.env',out/'target.env')
shutil.copyfile(repo/'config/target.py',out/'target.py')
(out/'server.env.example').write_text('# Public target parameters are in target.env; .env contains generated secrets only.\n')
caddy=(repo/'config/Caddyfile').read_text()
(out/'Caddyfile').write_text(caddy)
manifest={'status':'PACKAGED','package_contract':1,'version':os.environ['VERSION'],'batch':os.environ['BATCH'],
 'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
 'workflow_commit':os.environ['GITHUB_SHA'],
 'architecture':'arm64','target_profile':'linux-aarch64-existing-engine','origin':origin.rstrip('/'),
 'entry_mode':'request-origin-local-certificate',
 'prosody_storage_owner':[1000,1000],
 'deployment_commit':os.environ['DEPLOYMENT_COMMIT'],
 'images':{s:[r['tag'],r['image_id']] for s,r in records.items()},
 'image_archives':{s:{'tag':r['tag'],'image_id':r['image_id'],'file':r['archive'],'bytes':r['bytes'],
                     'sha256':r['sha256']} for s,r in records.items()},
 'compose':{'file':'bin/docker-compose','sha256':digest(out/'bin/docker-compose'),
            'url':os.environ['COMPOSE_URL'],'version':os.environ['COMPOSE_VERSION']},
 'patches':{p.relative_to(out).as_posix():digest(p) for p in (out/'patches').rglob('*') if p.is_file()},
 'requires':['Existing Linux aarch64 Docker Engine (27.3.1 baseline; actual host prerequisite not checked)',
             'Python >=3.7, root for installation, working cgroups/storage/network, correct system clock',
             'Free TCP '+str(https_port)+'/'+str(http_port)+' and UDP '+str(media_port),
             '4 GiB RAM recommended; lower-memory host compatibility is not established'],
 'not_tested':['target host compatibility','installation','service runtime','clients/media'],
 'publication':'NOT_PUBLISHED; publish these exact images only after separately approved acceptance'}
(out/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n')
if records['prosody']['runtime_user']!='1000:1000':
    raise ValueError('Prosody storage owner does not match image user')
verifier.require_ready(manifest); verifier.verify_product(out,compose)
for s in services:
    if configs[s]['pull_policy']!='never' or configs[s].get('build'):
        raise ValueError('Offline image configuration required')
if './data/jitsi/web:/config' not in configs['web']['volumes']:
    raise ValueError('Missing external web patch mount')
if './data/jitsi/prosody/prosody-plugins-custom:/prosody-plugins-custom:ro' not in configs['prosody']['volumes']:
    raise ValueError('Missing role plugin mount')
if 'custom.css' not in (out/'patches/web/custom-head.html').read_text():
    raise ValueError('Missing CSS head reference')
if 'custom.css' not in (out/'patches/web/nginx-custom/custom-css.conf').read_text():
    raise ValueError('Missing CSS route reference')
# Host transfer is part of the default product; HTTP downgrade remains optional.
manifest['patch_decisions']={name:('install' if name in verifier.PRODUCT_PATCHES else
 'not installed: documentation or optional Web/HTTP customization') for name in manifest['patches']}
(out/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n')
(out/'INSTALL.md').write_text('''# CloudMeet aarch64 offline package

Batch: '''+os.environ['BATCH']+'\nOrigin: '+origin+'''

This package contains all seven freshly built images, selected product configuration,
public patches, bundled native Compose and shared installation tools. It does NOT
include Docker Engine, a host OS, credentials, databases or CA private keys.
See candidate.json requires for host prerequisites. Do not assume previous server
software remains installed. Provide compatible Docker Engine separately if missing.
Packaging completion is not installation, host-compatibility or media acceptance.

## Manual first installation (operator only)
1. Compare the downloaded archive SHA256 with its separately supplied .sha256 file.
2. Extract into a new dedicated directory, then cd into that directory. Preserve file modes.
3. Check `uname -m` (aarch64), `python3 --version` (>=3.7),
   `docker info` (Linux ARM64 engine), system clock, disk/RAM and port availability.
4. Run `sha256sum -c SHA256SUMS` and `python3 -B install.py --verify-only`.
5. Run `./bin/docker-compose version` (no system plugin installation needed).
6. Review target.env ports and optional MEDIA_HOST. Browser signaling follows the page origin. Caddy uses a local cloudmeet.internal certificate: external IP access may require accepting certificate warnings and is not strict TLS acceptance. MEDIA_HOST empty uses JVB address discovery; NAT media reachability is not guaranteed. Initialization generates secrets only. Preserve CA volumes. Do not modify historical package bytes.
   This batch uses the confirmed origin/ports; do not change immutable package files.
7. Run `sudo python3 -B deploy.py --first-install` explicitly to import the included
   images, generate fresh secrets, install baseline patches and start the services.
   The command refuses existing .env/data, never builds/pulls and does not replace Docker.
   Do not re-run after partial installation by deleting data; inspect the failure first.
8. Keep .env, data and Caddy volumes on the server. Only export the public CA root
   for scoped client trust; never export CA private keys. Do not use global TLS bypasses.

No automatic upload, target installation, registry publication or media test was run.
After initialization the delivery checksum inventory intentionally no longer represents
the mutable instance; do not rerun first-install verification as an upgrade procedure.
Publishing later must load these same archives and tag/push without recompiling.
Registry manifest digest is distinct from Docker image config ID; record both.
''')
for path in out.rglob('*'):
    if path.is_file() and (path.name=='.env' or path.suffix in ('.key','.pfx','.p12')
                           or b'-----BEGIN PRIVATE KEY-----' in (path.read_bytes() if path.stat().st_size<2_000_000 else b'')):
        raise ValueError('Secret material in package: '+str(path))
(out/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.relative_to(out).as_posix()+'\n'
 for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
verifier.verify_checksums(out)
PY
    # Rendering only: no daemon operation or application startup.
    # target.py already exported validated public settings; example files are not inputs.
    JWT_APP_SECRET=RENDER_ONLY JICOFO_AUTH_PASSWORD=RENDER_ONLY JVB_AUTH_PASSWORD=RENDER_ONLY \
    JITSI_ROLE_CHECK_SECRET=RENDER_ONLY \
        "$output/bin/docker-compose" -f "$output/jitsi-base.yaml" config --quiet
    python3 -B "$output/install.py" --verify-only
    tar -czf "$output.tar.gz" -C "$(dirname "$output")" "$(basename "$output")"
    (cd "$(dirname "$output")"; sha256sum "$(basename "$output").tar.gz" > "$(basename "$output").tar.gz.sha256")
    # Re-read the actual final archive, not only the staging directory.
    python3 - "$output.tar.gz" <<'PY'
import hashlib, json, pathlib, sys, tarfile
archive=pathlib.Path(sys.argv[1])
with tarfile.open(archive,'r:gz') as tar:
    files={m.name:m for m in tar.getmembers() if m.isfile()}
    prefix=archive.name[:-7]+'/'
    expected={}
    for line in tar.extractfile(files[prefix+'SHA256SUMS']).read().decode().splitlines():
        digest,name=line.split('  ',1); expected[prefix+name]=digest
    if set(files)!=set(expected)|{prefix+'SHA256SUMS'}: raise ValueError('Archive member mismatch')
    for name,digest in expected.items():
        h=hashlib.sha256()
        with tar.extractfile(files[name]) as stream:
            for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
        if h.hexdigest()!=digest: raise ValueError('Archive integrity failure: '+name)
evidence={'status':'PASS_MATERIALS_ONLY','batch':__import__('os').environ['BATCH'],
 'archive':archive.name,'files':len(expected),'not_run':['installation','services','media','publication']}
(archive.parent/'package-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
PY
}

case "${1:-}" in
    build) build_service "${2:?Missing service}" ;;
    assemble) assemble_package ;;
    *) die 'Usage: package.sh build SERVICE | assemble' ;;
esac
