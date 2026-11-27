#!/usr/bin/env bash
# Single-target patch build entry (self-contained copy; no package assembly). Docker is used only on the native Actions runner.
set -euo pipefail
tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd "$tools/.." && pwd)
die() { printf '%s\n' "$*" >&2; exit 1; }
case "${1:-}" in
    -h|--help) printf '%s\n' 'Usage: package.sh build SERVICE' 'Run from skills/single-build-deploy/ on a native Actions runner.'; exit 0 ;;
    build) ;;
    *) die 'Usage: package.sh build SERVICE' ;;
esac
: "${VERSION:?Set VERSION}"
: "${BATCH:?Set BATCH to version/run/attempt identity}"
[[ $VERSION =~ ^[0-9]+(\.[0-9]+){2,3}\+r[1-9][0-9]*$ ]] || die 'Allocated display version required'
[[ $BATCH =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,110}$ ]] || die 'Invalid batch'
TARGET_ARCH=${TARGET_ARCH:-arm64}
case "$TARGET_ARCH" in
    arm64) HOST_ARCH=aarch64; PACKAGE_ARCH=aarch64; COMPOSE_ARCH=aarch64 ;;
    amd64) HOST_ARCH=x86_64; PACKAGE_ARCH=amd64; COMPOSE_ARCH=x86_64 ;;
    *) die 'Unsupported target architecture' ;;
esac
[[ $(uname -m) == "$HOST_ARCH" ]] || die "Native $HOST_ARCH runner required"
export TARGET_ARCH HOST_ARCH PACKAGE_ARCH COMPOSE_ARCH
: "${GITHUB_RUN_ID:?Run through GitHub Actions}"
: "${GITHUB_RUN_ATTEMPT:?Missing workflow attempt}"
: "${GITHUB_SHA:?Missing workflow commit}"
[[ $BATCH == "${VERSION/+/-}-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT" ]] || die 'Batch identity mismatch'
deployment_commit=$(git -C "$repo" rev-parse HEAD)
[[ $deployment_commit == "$GITHUB_SHA" ]] || die 'Workflow commit mismatch'
(cd "$repo/../..")
export VERSION BATCH DEPLOYMENT_COMMIT="$deployment_commit"
: "${VERSION_RECORD:?Bound version allocation record required}"
python3 -B - "$VERSION_RECORD" "$repo/sources.json" <<'PY'
import json,os,sys
r=json.load(open(sys.argv[1])); s=json.load(open(sys.argv[2]))
assert r['versions']['server_version']==os.environ['VERSION'], 'Version assignment mismatch'
for name,item in s['services'].items():
    assert r['request']['sources'].get(name)==item['commit'], 'Source allocation mismatch'
PY


source_field() {
    python3 - "$repo/sources.json" "$1" "$2" <<'PY'
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
    case "$service" in gateway|app-web|api|jitsi-mgr|web|prosody|jicofo|jvb) ;; *) die 'Unknown service';; esac
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
        docker pull --platform "linux/$TARGET_ARCH" "$ref" >&2
        docker image inspect "$ref" | python3 -c '
import json, os, sys
i=json.load(sys.stdin)[0]
assert (i["Os"],i["Architecture"]) == ("linux",os.environ["TARGET_ARCH"]), "Wrong base platform"
with open(os.environ["BASE_RECORDS"],"a") as f:
    f.write(json.dumps({"requested":sys.argv[1],"id":i["Id"],"digests":i["RepoDigests"]})+"\n")
print(i["RepoDigests"][0])' "$ref"
    }
    lifecycle_base=ghcr.io/jitsi/base@sha256:03a73ca2e924e5770b9a0aa3f120c0907eb120142a48ef7f37be9764c6f94575
    debian_base=debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
    labels=(--label "org.opencontainers.image.version=$VERSION"
        --label "org.opencontainers.image.revision=$SOURCE_COMMIT"
        --label "io.cloudmeet.batch=$BATCH" --label "io.cloudmeet.service=$service"
        --label "io.cloudmeet.deployment=$deployment_commit")
    if [[ $TARGET_ARCH == arm64 ]]; then
        java17=${JAVA_HOME_17_ARM64:-/usr/lib/jvm/temurin-17-jdk-arm64}
    else
        java17=${JAVA_HOME_17_X64:-/usr/lib/jvm/temurin-17-jdk-amd64}
    fi
    case "$service" in
        web|app-web)
            builder=$(resolve_base node:24-trixie)
            command='npm ci; npm run build'
            [[ $service != web ]] || command='npm ci; make all'
            build_env=()
            # This approved instance package follows its host origin, never the 118 default.
            [[ $service != app-web ]] || build_env=(-e VITE_JITSI_SERVER=same-origin)
            docker run --rm --platform "linux/$TARGET_ARCH" --user "$(id -u):$(id -g)" \
                -e HOME=/tmp "${build_env[@]}" -v "$source:/src" -w /src "$builder" bash -euc "$command"
            if [[ $service == app-web ]]; then
                runtime=$(resolve_base nginx:1.30.6-alpine@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311)
                cp -a "$source/dist" "$context/dist"
                grep -rq 'same-origin' "$context/dist" || die 'Missing same-origin application configuration'
                cp "$repo/templates/nginx.conf" "$context/nginx.conf"
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
            (export JAVA_HOME="$java17" PATH="$java17/bin:$PATH"; cd "$source"; python3 -B "$repo/tools/maven-route.py" --audit "$repo/output/network-audit-build-$service/maven-route.jsonl" -- -B -ntp -DskipTests package)
            jars=("$source/target/"*.jar)
            [[ ${#jars[@]} == 1 && -s ${jars[0]} ]] || die 'Expected one API jar'
            cp "${jars[0]}" "$context/app.jar"
            ;;
        jitsi-mgr)
            # jitsi-mgr is not a Docker image service - it outputs JAR and frontend static files
            # Backend: Spring Boot JAR
            (export JAVA_HOME="$java17" PATH="$java17/bin:$PATH"; cd "$source/jitsi-mgr-app"; python3 -B "$repo/tools/maven-route.py" --audit "$repo/output/network-audit-build-$service/maven-route.jsonl" -- -B -ntp -DskipTests package)
            backend_jars=("$source/jitsi-mgr-app/target/"jitsi-mgr-*.jar)
            # Exclude -sources.jar and -javadoc.jar
            filtered_jars=()
            for jar in "${backend_jars[@]}"; do
                [[ $jar == *-sources.jar || $jar == *-javadoc.jar ]] || filtered_jars+=("$jar")
            done
            [[ ${#filtered_jars[@]} == 1 && -s ${filtered_jars[0]} ]] || die 'Expected one jitsi-mgr backend jar'
            mkdir -p "$context/backend"
            cp "${filtered_jars[0]}" "$context/backend/jitsi-mgr.jar"
            sha256sum "$context/backend/jitsi-mgr.jar" | tee "$context/backend/jitsi-mgr.jar.sha256"
            # Frontend: React SPA
            builder=$(resolve_base node:24-trixie)
            # Create production env pointing to relative API path
            printf 'REACT_APP_API_BASE_URL=/api/mgr/v1\nPUBLIC_URL=/api/mgr/ui\n' > "$source/jitsi-mgr-frontend/.env.production"
            docker run --rm --platform "linux/$TARGET_ARCH" --user "$(id -u):$(id -g)" \
                -e HOME=/tmp -v "$source/jitsi-mgr-frontend:/src" -w /src "$builder" bash -euc 'npm ci; npm run build'
            mkdir -p "$context/frontend"
            cp -a "$source/jitsi-mgr-frontend/build/." "$context/frontend/"
            # Generate frontend SHA256 manifest
            (cd "$context/frontend" && find . -type f -exec sha256sum {} \;) | sort > "$context/frontend.sha256"
            # jitsi-mgr outputs artifacts directly, no Docker image
            mkdir -p "$repo/output/$service/artifacts"
            cp "$context/backend/jitsi-mgr.jar" "$repo/output/$service/artifacts/"
            cp "$context/backend/jitsi-mgr.jar.sha256" "$repo/output/$service/artifacts/"
            cp -a "$context/frontend" "$repo/output/$service/artifacts/jitsi-mgr-ui"
            cp "$context/frontend.sha256" "$repo/output/$service/artifacts/jitsi-mgr-ui.sha256"
            # Record build evidence
            cat > "$repo/output/$service/build-evidence.json" <<BUILD_EOF
{
  "service": "jitsi-mgr",
  "version": "$VERSION",
  "batch": "$BATCH",
  "source_commit": "$SOURCE_COMMIT",
  "deployment_commit": "$deployment_commit",
  "backend_jar": "jitsi-mgr.jar",
  "frontend_dir": "jitsi-mgr-ui",
  "architecture": "$TARGET_ARCH"
}
BUILD_EOF
            python3 -B - "$repo/output/$service" <<'PY'
import hashlib,json,os,pathlib
out=pathlib.Path(__import__('sys').argv[1])
record=json.loads((out/'build-evidence.json').read_text())
record.update(run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
    version_assignment=json.loads(pathlib.Path(os.environ['VERSION_RECORD']).read_text()),
    files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in (out/'artifacts').rglob('*') if p.is_file()})
(out/'build-evidence.json').write_text(json.dumps(record,indent=2)+'\n')
PY
            # Skip Docker image creation for jitsi-mgr
            return 0
            ;;
        gateway)
            runtime=$(resolve_base "$debian_base")
            builder=$(resolve_base golang:1.27-trixie)
            docker run --rm --platform "linux/$TARGET_ARCH" --user "$(id -u):$(id -g)" \
                -e HOME=/tmp -e GOPATH=/tmp/go -e GOCACHE=/tmp/go-cache -e GOARCH="$TARGET_ARCH" \
                -v "$source:/src" -w /src "$builder" bash -euc \
                'export GOTOOLCHAIN=local; go mod download; go mod verify; CGO_ENABLED=0 GOOS=linux go build -p 2 -trimpath -o caddy-candidate ./cmd/caddy'
            cp "$source/caddy-candidate" "$context/caddy"
            ;;
        prosody)
            resolve_base "$lifecycle_base" > /dev/null
            resolve_base "$debian_base" > /dev/null
            # Intermediate tag is unique to this batch and can never be an older fallback.
            docker build --platform "linux/$TARGET_ARCH" --progress plain \
                -f "$repo/docker/prosody-core.Dockerfile" -t "cloudmeet-build/prosody-core:$BATCH" "$source"
            mkdir -p "$source/runtime-downloads"
            curl -fLsS --retry 3 https://raw.githubusercontent.com/aiq/basexx/v0.4.1/lib/basexx.lua -o "$source/runtime-downloads/basexx.lua"
            curl -fLsS --retry 3 https://raw.githubusercontent.com/kikito/inspect.lua/v3.1.3/inspect.lua -o "$source/runtime-downloads/inspect.lua"
            (cd "$source/runtime-downloads"; printf '%s\n' \
                '6f8241efd8ea7affafdd00f433c317ed88151d87089b13ae4f94a421d4789445  basexx.lua' \
                '72de901ac081bf927640e367b52146a18ed4f628eab7880dd32f1a6442b9fe6f  inspect.lua' | sha256sum -c -)
            docker build --platform "linux/$TARGET_ARCH" --progress plain "${labels[@]}" \
                --build-arg "PROSODY_CORE=cloudmeet-build/prosody-core:$BATCH" \
                -f "$repo/docker/prosody-service.Dockerfile" -t "cloudmeet/prosody:$BATCH" "$source"
            ;;
        jicofo|jvb)
            resolve_base "$lifecycle_base" > /dev/null
            checkout_source lifecycle "$work/lifecycle"
            (export JAVA_HOME="$java17" PATH="$java17/bin:$PATH"; cd "$source"; python3 -B "$repo/tools/maven-route.py" --audit "$repo/output/network-audit-build-$service/maven-route.jsonl" -- -B -ntp -DskipTests package)
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
            docker build --platform "linux/$TARGET_ARCH" --progress plain "${labels[@]}" \
                --build-arg "SERVICE=$service" -f "$repo/docker/java-service.Dockerfile" \
                -t "cloudmeet/$service:$BATCH" "$context"
            ;;
    esac
    case "$service" in
        web|app-web|api|gateway)
            docker build --platform "linux/$TARGET_ARCH" --progress plain "${labels[@]}" \
                --build-arg "RUNTIME_BASE=$runtime" --build-arg "SOURCE_COMMIT=$SOURCE_COMMIT" \
                -f "$repo/docker/$service.Dockerfile" -t "cloudmeet/$service:$BATCH" "$context"
            ;;
    esac
    # Build outputs may be untracked; tracked source/config/lock changes are forbidden.
    git -C "$source" diff --exit-code
    git -C "$source" diff --cached --exit-code
    [[ ! -s $work/source-before.txt ]] || die 'Dirty checkout before build'
    docker image inspect "cloudmeet/$service:$BATCH" > "$work/image.json"
    docker save "cloudmeet/$service:$BATCH" | gzip -1 > "$repo/output/$service/$service.tar.gz"
    python3 - "$work" "$repo/output/$service" "$repo/sources.json" <<'PY'
import hashlib, json, os, pathlib, sys
work, out, sourcefile = map(pathlib.Path, sys.argv[1:])
service = os.environ['SERVICE']
info = json.loads((work/'image.json').read_text())[0]
labels = info['Config']['Labels']
assert (info['Os'], info['Architecture']) == ('linux', os.environ['TARGET_ARCH']), 'Wrong image architecture'
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
         'version_assignment':json.loads(pathlib.Path(os.environ['VERSION_RECORD']).read_text()),
        'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
         'workflow_commit':os.environ['GITHUB_SHA'],'source_dirty':False,
         'build_overrides':{'VITE_JITSI_SERVER':'same-origin'} if service=='app-web' else {},
        'deployment_commit':os.environ['DEPLOYMENT_COMMIT'],'source':sources['services'][service],
         'lifecycle':sources['lifecycle'] if service in ('web','jicofo','jvb') else None,
         'source_config_sha256':{p:digest(work/'source'/p) for p in
                                  ('package-lock.json','.env','pom.xml','go.mod','go.sum')
                                  if (work/'source'/p).is_file()},
        'tag':'cloudmeet/'+service+':'+os.environ['BATCH'],'image_id':info['Id'],
          'platform':'linux/'+os.environ['TARGET_ARCH'],'archive':archive.name,'bytes':archive.stat().st_size,
         'runtime_user':info['Config'].get('User',''),
        'sha256':digest(archive),'bases':[json.loads(line) for line in (work/'bases.jsonl').read_text().splitlines()],
        'context_sha256':{p.relative_to(work/'context').as_posix():digest(p)
                          for p in (work/'context').rglob('*') if p.is_file()},
        'acceptance':'NOT_RUN_PACKAGING_ONLY'}
(out/(service+'.json')).write_text(json.dumps(record,indent=2)+'\n')
PY
)

case "${1:-}" in
    build) build_service "${2:?Missing service}" ;;
    *) die 'Usage: package.sh build SERVICE' ;;
esac
