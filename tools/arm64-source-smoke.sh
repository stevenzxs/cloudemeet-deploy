#!/usr/bin/env bash
set -euo pipefail
test "$(uname -m)" = aarch64
test "$(docker info --format '{{.Architecture}}')" = aarch64
work=$(mktemp -d)
recipe="$PWD/tools"
trap 'rm -rf -- "$work"' EXIT

checkout() {
    git init -q "$work/source"
    git -C "$work/source" fetch --depth=1 "$1" "$2"
    git -C "$work/source" checkout --detach FETCH_HEAD
    test "$(git -C "$work/source" rev-parse HEAD)" = "$2"
}

case "${1:?service required}" in
prosody)
    checkout https://github.com/stevenzxs/jitsi-meet-prosody.git 72b2dc8fe282cf168ff932016fda68e034860815
    cmp patches/prosody/mod_muc_host_transfer.lua "$work/source/jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua"
    docker build --platform linux/arm64 -t cloudmeet-ci/prosody -f tools/arm64-prosody.Dockerfile "$work/source"
    test "$(docker image inspect cloudmeet-ci/prosody --format '{{.Os}}/{{.Architecture}}')" = linux/arm64
    docker run --rm --network none cloudmeet-ci/prosody
    ;;
jvb)
    checkout https://github.com/stevenzxs/jvb.git bf271b11f795d6546f8d78dee441c67d9ba2bf6b
    cd "$work/source"
    export JAVA_HOME="${JAVA_HOME_17_ARM64:-/usr/lib/jvm/temurin-17-jdk-arm64}"
    test -x "$JAVA_HOME/bin/java"
    export PATH="$JAVA_HOME/bin:$PATH"
    java -version
    mvn -B -ntp verify
    archives=(jvb/target/*-archive.zip)
    test "${#archives[@]}" = 1
    sha256sum "${archives[0]}"
    mkdir "$work/jvb-image"
    unzip -q "${archives[0]}" -d "$work/jvb-image"
    jar=$(find "$work/jvb-image" -name jitsi-videobridge.jar -type f)
    test -s "$jar"
    docker build --platform linux/arm64 -t cloudmeet-ci/jvb \
        -f "$recipe/arm64-jvb.Dockerfile" "$(dirname "$jar")"
    test "$(docker image inspect cloudmeet-ci/jvb --format '{{.Os}}/{{.Architecture}}')" = linux/arm64
    docker run --rm --network none cloudmeet-ci/jvb
    ;;
*) exit 2 ;;
esac
