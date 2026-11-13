ARG PROSODY_CORE
FROM ghcr.io/jitsi/base@sha256:03a73ca2e924e5770b9a0aa3f120c0907eb120142a48ef7f37be9764c6f94575 AS lifecycle
FROM ${PROSODY_CORE}
USER root
COPY --from=lifecycle /command/ /command/
COPY --from=lifecycle /package/ /package/
COPY --from=lifecycle /etc/s6-overlay/ /etc/s6-overlay/
COPY --from=lifecycle /init /init
COPY --from=lifecycle /usr/bin/tpl /usr/bin/tpl
RUN apt-get update && apt-get install -y --no-install-recommends bash curl && rm -rf /var/lib/apt/lists/*
COPY runtime-downloads/ /usr/local/share/lua/5.4/
COPY docker/base/rootfs/usr/bin/check-writable /usr/bin/check-writable
COPY docker/prosody/rootfs/ /
ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2 S6_READ_ONLY_ROOT=1
RUN chmod 0755 /usr/bin/check-writable /etc/s6-overlay/scripts/* && chown 1000:1000 /run/prosody && chmod 0750 /run/prosody && lua5.4 -e 'require("inspect"); require("basexx"); require("openssl.hmac"); require("cjson.safe")'
USER 1000:1000
RUN test -w /var/lib/prosody && test -w /var/lib/prosody/data
ENTRYPOINT ["/init"]
CMD []
