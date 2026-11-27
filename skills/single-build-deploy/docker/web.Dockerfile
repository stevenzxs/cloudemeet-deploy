ARG RUNTIME_BASE
FROM ${RUNTIME_BASE}
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.revision=${SOURCE_COMMIT}
USER root
# Distribution nginx, not a published Jitsi application image. Record exact packages.
RUN apt-dpkg-wrap apt-get update && apt-dpkg-wrap apt-get install -y --no-install-recommends nginx curl dnsutils jq socat \
    && mkdir -p /etc/nginx/modules-enabled /storage /usr/share/jitsi-meet \
    && chown s6:s6 /storage && rm -f /etc/nginx/conf.d/default.conf \
    && rm -rf /var/lib/nginx && ln -s /run/web/tmp /var/lib/nginx && apt-cleanup
COPY rootfs/ /
COPY payload/ /usr/share/jitsi-meet/
RUN mv /usr/share/jitsi-meet/interface_config.js /defaults/interface_config.js \
    && ln -s /run/web/.well-known /usr/share/jitsi-meet/.well-known \
    && chmod 0755 /etc/s6-overlay/scripts/* && test -s /usr/share/jitsi-meet/libs/app.bundle.min.js
ENV DISABLE_HTTPS=1 ENABLE_LETSENCRYPT=0
EXPOSE 8000 8443
VOLUME ["/config", "/usr/share/jitsi-meet/transcripts"]
USER s6
