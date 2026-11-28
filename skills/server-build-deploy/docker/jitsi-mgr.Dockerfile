FROM ghcr.io/jitsi/base@sha256:03a73ca2e924e5770b9a0aa3f120c0907eb120142a48ef7f37be9764c6f94575
ARG SOURCE_COMMIT
ARG VERSION
ARG BATCH
LABEL org.opencontainers.image.version=${VERSION} \
      org.opencontainers.image.revision=${SOURCE_COMMIT} \
      io.cloudmeet.batch=${BATCH} \
      io.cloudmeet.service=jitsi-mgr
USER root
RUN apt-dpkg-wrap apt-get update && apt-dpkg-wrap apt-get install -y --no-install-recommends openjdk-21-jre-headless curl && apt-cleanup
WORKDIR /app
COPY backend/jitsi-mgr.jar /app/jitsi-mgr.jar
RUN mkdir -p /app/data && chown -R s6:s6 /app
USER s6
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65", "-jar", "/app/jitsi-mgr.jar"]
