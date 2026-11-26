ARG RUNTIME_BASE
FROM ${RUNTIME_BASE}
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.revision=${SOURCE_COMMIT}
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY caddy /usr/bin/caddy
RUN chmod 0755 /usr/bin/caddy && caddy list-modules
ENV XDG_CONFIG_HOME=/config XDG_DATA_HOME=/data
WORKDIR /srv
EXPOSE 80 443 443/udp
ENTRYPOINT ["/usr/bin/caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
