#!/usr/bin/env bash
# Builds current pinned application source; no registry writes or target access.
set -euo pipefail
test "$(uname -m)" = aarch64
repo="$PWD"
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir -p arm64-evidence
export JAVA_HOME="${JAVA_HOME_17_ARM64:-/usr/lib/jvm/temurin-17-jdk-arm64}"
test -x "$JAVA_HOME/bin/java"
export PATH="$JAVA_HOME/bin:$PATH"

checkout() {
    git init -q "$2"
    git -C "$2" fetch --depth=1 "$1" "$3"
    git -C "$2" checkout --detach FETCH_HEAD
    test "$(git -C "$2" rev-parse HEAD)" = "$3"
}

checkout https://github.com/jitsi/docker-jitsi-meet.git "$work/docker" 276801c7fd4233f7288ba95bd132c219852c7ac7
checkout https://github.com/stevenzxs/jitsi-meet-prosody.git "$work/prosody" 72b2dc8fe282cf168ff932016fda68e034860815
cmp patches/prosody/mod_muc_host_transfer.lua "$work/prosody/jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua"
docker build --platform linux/arm64 -t cloudmeet-ci/prosody-core \
    -f tools/arm64-prosody-core.Dockerfile "$work/prosody"
mkdir "$work/prosody/runtime-downloads"
curl -fsSL --retry 3 https://raw.githubusercontent.com/aiq/basexx/v0.4.1/lib/basexx.lua -o "$work/prosody/runtime-downloads/basexx.lua"
curl -fsSL --retry 3 https://raw.githubusercontent.com/kikito/inspect.lua/v3.1.3/inspect.lua -o "$work/prosody/runtime-downloads/inspect.lua"
(cd "$work/prosody/runtime-downloads"; printf '%s\n' \
    '6f8241efd8ea7affafdd00f433c317ed88151d87089b13ae4f94a421d4789445  basexx.lua' \
    '72de901ac081bf927640e367b52146a18ed4f628eab7880dd32f1a6442b9fe6f  inspect.lua' | sha256sum -c -)
docker build --platform linux/arm64 -t cloudmeet-ci/prosody \
    -f tools/arm64-prosody-service.Dockerfile "$work/prosody"

for service in jicofo jvb; do
    if test "$service" = jicofo; then
        commit=48874dc526573016ca6512ebbb697911802e4c53
        jarname=jicofo.jar
    else
        commit=bf271b11f795d6546f8d78dee441c67d9ba2bf6b
        jarname=jitsi-videobridge.jar
    fi
    checkout "https://github.com/stevenzxs/$service.git" "$work/$service" "$commit"
    (cd "$work/$service"; mvn -B -ntp verify) 2>&1 | tee "arm64-evidence/$service-verify.log"
    archives=("$work/$service/$service"/target/*-archive.zip)
    test "${#archives[@]}" = 1
    mkdir -p "$work/$service-context/unpack"
    unzip -q "${archives[0]}" -d "$work/$service-context/unpack"
    jar=$(find "$work/$service-context/unpack" -name "$jarname" -type f)
    test -s "$jar"
    mv "$(dirname "$jar")" "$work/$service-context/distribution"
    cp -a "$work/docker/$service/rootfs" "$work/$service-context/rootfs"
    docker build --platform linux/arm64 -t "cloudmeet-ci/$service" \
        --build-arg "SERVICE=$service" -f "$repo/tools/arm64-java-service.Dockerfile" "$work/$service-context"
done
python3 tools/arm64-integration.py
