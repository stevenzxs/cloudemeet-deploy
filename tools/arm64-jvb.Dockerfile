FROM ghcr.io/jitsi/base@sha256:48f5eb97cdb15306f4ae0f1d924f6485f3f514d6781aeb86e36601a67aa73781
USER root
RUN apt-dpkg-wrap apt-get update \
    && apt-dpkg-wrap apt-get install -y --no-install-recommends openjdk-21-jre-headless libpcap0.8 \
    && apt-cleanup
COPY . /usr/share/jitsi-videobridge/
USER 1000:1000
ENTRYPOINT ["java"]
CMD ["-version"]
