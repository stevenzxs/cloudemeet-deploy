#!/usr/bin/env bash
# Minimal CloudMeet service builder for build-server.yml (fresh implementation,
# not shared with the joint toolchain). Builds one service from a pinned source
# checkout into output/<service>/ (image tar.gz + build-evidence.json, or
# jitsi-mgr artifacts). No network audit, no registry absence probing.
set -euo pipefail

service="${1:?service name required}"
: "${VERSION:?}" "${BATCH:?}" "${TARGET_ARCH:?}" "${SOURCE_COMMIT:?}" "${GITHUB_SHA:?}"
: "${SKILL_DIR:?}" "${WORK_DIR:?}" "${SOURCE_DIR:?}"
LIFECYCLE_DIR="${LIFECYCLE_DIR:-}"

lifecycle_base='ghcr.io/jitsi/base@sha256:03a73ca2e924e5770b9a0aa3f120c0907eb120142a48ef7f37be9764c6f94575'
debian_base='debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2'
nginx_base='nginx:1.30.6-alpine@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311'

out="$WORK_DIR/output/$service"
mkdir -p "$out"
context="$WORK_DIR/context/$service"
rm -rf "$context"
mkdir -p "$context"

labels=(--label "org.opencontainers.image.version=$VERSION"
        --label "org.opencontainers.image.revision=$SOURCE_COMMIT"
        --label "io.cloudmeet.batch=$BATCH"
        --label "io.cloudmeet.service=$service"
        --label "io.cloudmeet.deployment=$GITHUB_SHA")

node_build() { # <source-dir> <command> [extra-env...]
  local dir="$1" command="$2"
  shift 2
  docker run --rm --platform "linux/$TARGET_ARCH" --user "$(id -u):$(id -g)" \
    -e HOME=/tmp "$@" -v "$dir:/src" -w /src node:24-trixie bash -euc "$command"
}

mvn_package() { # <source-dir>
  # Central rate-limits CI runners (429); route through the approved Tencent
  # mirror with Central fallback (same policy as the joint maven-route tool).
  local settings="$WORK_DIR/maven-settings.xml"
  if [[ ! -f $settings ]]; then
    cat > "$settings" <<'XML'
<settings>
  <mirrors>
    <mirror>
      <id>cloudmeet-central</id>
      <mirrorOf>central</mirrorOf>
      <url>https://mirrors.cloud.tencent.com/nexus/repository/maven-public/</url>
    </mirror>
  </mirrors>
</settings>
XML
  fi
  (cd "$1" && mvn -s "$settings" -B -ntp -DskipTests package)
}

case "$service" in
  web)
    node_build "$SOURCE_DIR" 'npm ci; make all'
    runtime="$lifecycle_base"
    cp -a "$LIFECYCLE_DIR/web/rootfs" "$context/rootfs"
    mkdir -p "$context/payload/css" "$context/payload/resources"
    cp "$SOURCE_DIR/"*.html "$SOURCE_DIR/"*.js "$context/payload/"
    for directory in fonts images libs static sounds lang; do
      cp -a "$SOURCE_DIR/$directory" "$context/payload/$directory"
    done
    cp "$SOURCE_DIR/css/all.css" "$context/payload/css/"
    cp "$SOURCE_DIR/LICENSE" "$context/payload/"
    cp "$SOURCE_DIR/resources/"*.txt "$context/payload/resources/"
    printf 'User-agent: *\nDisallow: /\n' > "$context/payload/robots.txt"
    ;;
  app-web)
    node_build "$SOURCE_DIR" 'npm ci; npm run build' -e VITE_JITSI_SERVER=same-origin
    runtime="$nginx_base"
    cp -a "$SOURCE_DIR/dist" "$context/dist"
    cp "$SKILL_DIR/templates/nginx.conf" "$context/nginx.conf"
    ;;
  api)
    mvn_package "$SOURCE_DIR"
    jars=("$SOURCE_DIR/target/"*.jar)
    [[ ${#jars[@]} == 1 && -s ${jars[0]} ]] || { echo 'Expected one API jar' >&2; exit 1; }
    cp "${jars[0]}" "$context/app.jar"
    runtime='eclipse-temurin:17-jre-jammy'
    ;;
  gateway)
    docker run --rm --platform "linux/$TARGET_ARCH" --user "$(id -u):$(id -g)" \
      -e HOME=/tmp -e GOPATH=/tmp/go -e GOCACHE=/tmp/go-cache -e GOARCH="$TARGET_ARCH" \
      -v "$SOURCE_DIR:/src" -w /src golang:1.27-trixie bash -euc \
      'export GOTOOLCHAIN=local; go mod download; go mod verify; CGO_ENABLED=0 GOOS=linux go build -p 2 -trimpath -o caddy-candidate ./cmd/caddy'
    cp "$SOURCE_DIR/caddy-candidate" "$context/caddy"
    runtime="$debian_base"
    ;;
  prosody)
    docker build --platform "linux/$TARGET_ARCH" --progress plain \
      -f "$SKILL_DIR/docker/prosody-core.Dockerfile" -t "cloudmeet-build/prosody-core:$BATCH" "$SOURCE_DIR"
    mkdir -p "$SOURCE_DIR/runtime-downloads"
    curl -fLsS --retry 3 https://raw.githubusercontent.com/aiq/basexx/v0.4.1/lib/basexx.lua -o "$SOURCE_DIR/runtime-downloads/basexx.lua"
    curl -fLsS --retry 3 https://raw.githubusercontent.com/kikito/inspect.lua/v3.1.3/inspect.lua -o "$SOURCE_DIR/runtime-downloads/inspect.lua"
    (cd "$SOURCE_DIR/runtime-downloads" && printf '%s\n' \
      '6f8241efd8ea7affafdd00f433c317ed88151d87089b13ae4f94a421d4789445  basexx.lua' \
      '72de901ac081bf927640e367b52146a18ed4f628eab7880dd32f1a6442b9fe6f  inspect.lua' | sha256sum -c -)
    docker build --platform "linux/$TARGET_ARCH" --progress plain "${labels[@]}" \
      --build-arg "PROSODY_CORE=cloudmeet-build/prosody-core:$BATCH" \
      -f "$SKILL_DIR/docker/prosody-service.Dockerfile" -t "cloudmeet/prosody:$BATCH" "$SOURCE_DIR"
    ;;
  jicofo|jvb)
    mvn_package "$SOURCE_DIR"
    archives=("$SOURCE_DIR/$service/target/"*-archive.zip)
    [[ ${#archives[@]} == 1 && -s ${archives[0]} ]] || { echo 'Expected one distribution archive' >&2; exit 1; }
    mkdir "$context/unpack"
    unzip -q "${archives[0]}" -d "$context/unpack"
    jarname=jicofo.jar
    [[ $service != jvb ]] || jarname=jitsi-videobridge.jar
    mapfile -t jars < <(find "$context/unpack" -name "$jarname" -type f)
    [[ ${#jars[@]} == 1 ]] || { echo 'Expected one application jar' >&2; exit 1; }
    mv "$(dirname "${jars[0]}")" "$context/distribution"
    cp -a "$LIFECYCLE_DIR/$service/rootfs" "$context/rootfs"
    docker build --platform "linux/$TARGET_ARCH" --progress plain "${labels[@]}" \
      --build-arg "SERVICE=$service" -f "$SKILL_DIR/docker/java-service.Dockerfile" \
      -t "cloudmeet/$service:$BATCH" "$context"
    ;;
  jitsi-mgr)
    mvn_package "$SOURCE_DIR/jitsi-mgr-app"
    backend_jars=("$SOURCE_DIR/jitsi-mgr-app/target/"jitsi-mgr-*.jar)
    filtered=()
    for jar in "${backend_jars[@]}"; do
      [[ $jar == *-sources.jar || $jar == *-javadoc.jar ]] || filtered+=("$jar")
    done
    [[ ${#filtered[@]} == 1 && -s ${filtered[0]} ]] || { echo 'Expected one jitsi-mgr backend jar' >&2; exit 1; }
    mkdir -p "$context/backend" "$context/frontend" "$out/artifacts"
    cp "${filtered[0]}" "$context/backend/jitsi-mgr.jar"
    printf 'REACT_APP_API_BASE_URL=/api/mgr/v1\nPUBLIC_URL=/api/mgr/ui\n' > "$SOURCE_DIR/jitsi-mgr-frontend/.env.production"
    node_build "$SOURCE_DIR/jitsi-mgr-frontend" 'npm ci; npm run build'
    cp -a "$SOURCE_DIR/jitsi-mgr-frontend/build/." "$context/frontend/"
    cp "$context/backend/jitsi-mgr.jar" "$out/artifacts/jitsi-mgr.jar"
    tar -czf "$out/artifacts/jitsi-mgr-ui.tar.gz" -C "$context/frontend" .
    ;;
  *)
    echo "Unknown service: $service" >&2
    exit 1
    ;;
esac

case "$service" in
  web|app-web|api|gateway)
    docker build --platform "linux/$TARGET_ARCH" --progress plain "${labels[@]}" \
      --build-arg "RUNTIME_BASE=$runtime" --build-arg "SOURCE_COMMIT=$SOURCE_COMMIT" \
      -f "$SKILL_DIR/docker/$service.Dockerfile" -t "cloudmeet/$service:$BATCH" "$context"
    ;;
  jitsi-mgr)
    docker build --platform "linux/$TARGET_ARCH" --progress plain "${labels[@]}" \
      --build-arg "SOURCE_COMMIT=$SOURCE_COMMIT" --build-arg "VERSION=$VERSION" --build-arg "BATCH=$BATCH" \
      -f "$SKILL_DIR/docker/jitsi-mgr.Dockerfile" -t "cloudmeet/$service:$BATCH" "$context"
    ;;
esac
docker save "cloudmeet/$service:$BATCH" | gzip -1 > "$out/$service.tar.gz"

python3 - "$out" <<'PY'
import hashlib, json, os, pathlib, subprocess, sys

out = pathlib.Path(sys.argv[1])
service = os.environ['SERVICE']
def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

record = {'service': service, 'version': os.environ['VERSION'], 'batch': os.environ['BATCH'],
          'source_commit': os.environ['SOURCE_COMMIT'], 'deployment_commit': os.environ['GITHUB_SHA'],
          'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
          'platform': 'linux/' + os.environ['TARGET_ARCH']}
archive = out / (service + '.tar.gz')
if archive.exists():
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', f"cloudmeet/{service}:{os.environ['BATCH']}"], text=True))[0]
    if (image['Os'], image['Architecture']) != ('linux', os.environ['TARGET_ARCH']):
        raise ValueError('Wrong image architecture')
    record.update(image_id=image['Id'], tag=f"cloudmeet/{service}:{os.environ['BATCH']}",
                  archive=archive.name, sha256=digest(archive))
else:
    record['files'] = {p.relative_to(out).as_posix(): digest(p)
                       for p in (out / 'artifacts').rglob('*') if p.is_file()}
(out / 'build-evidence.json').write_text(json.dumps(record, indent=2) + '\n')
PY
