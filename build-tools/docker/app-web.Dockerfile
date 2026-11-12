ARG RUNTIME_BASE
FROM ${RUNTIME_BASE}
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.revision=${SOURCE_COMMIT}
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist/ /usr/share/nginx/html/cm/
RUN find /usr/share/nginx/html/cm -type d -exec chmod 0755 {} + && find /usr/share/nginx/html/cm -type f -exec chmod 0644 {} +
