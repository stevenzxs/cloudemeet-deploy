FROM ghcr.io/jitsi/base@sha256:03a73ca2e924e5770b9a0aa3f120c0907eb120142a48ef7f37be9764c6f94575
ARG SERVICE
USER root
RUN apt-dpkg-wrap apt-get update && apt-dpkg-wrap apt-get install -y --no-install-recommends openjdk-21-jre-headless curl dnsutils iproute2 jq libpcap0.8 && apt-cleanup
COPY distribution/ /usr/share/${SERVICE}/
# JVB distribution has historically lived under /usr/share/jitsi-videobridge.
RUN if [ "$SERVICE" = jvb ]; then mv /usr/share/jvb /usr/share/jitsi-videobridge; fi
COPY rootfs/ /
RUN chmod 0755 /etc/s6-overlay/scripts/* && if [ "$SERVICE" = jvb ]; then chmod 0755 /usr/share/jitsi-videobridge/*.sh; else chmod 0755 /usr/share/jicofo/*.sh; fi
USER s6
ENTRYPOINT ["/init"]
CMD []
