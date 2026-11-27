ARG RUNTIME_BASE
FROM ${RUNTIME_BASE}
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.revision=${SOURCE_COMMIT}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV SERVER_PORT=9000 API_CONTEXT_PATH=/mapi JITSI_MEET_DB_URL=jdbc:sqlite:/app/data/jitsi-meet-api.sqlite.db
RUN mkdir -p /app/data
COPY app.jar /app/app.jar
EXPOSE 9000
VOLUME ["/app/data"]
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
