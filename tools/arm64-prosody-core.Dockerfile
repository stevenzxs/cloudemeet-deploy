FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS compiler
RUN apt-get update && apt-get install -y --no-install-recommends build-essential lua5.4 liblua5.4-dev libssl-dev libicu-dev && rm -rf /var/lib/apt/lists/*
COPY prosody/ /src/prosody/
WORKDIR /src/prosody
RUN sh ./configure --ostype=debian --prefix=/opt/cloudmeet-prosody --sysconfdir=/run/prosody/config --datadir=/var/lib/prosody/data --lua-version=5.4 --lua-suffix=5.4 --idn-library=icu --no-example-certs && make -j2 && make install DESTDIR=/stage
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates openssl lua5.4 libssl3t64 libicu76 lua-expat lua-filesystem lua-socket lua-sec lua-unbound lua-luaossl lua-bitop lua-cjson && groupadd --gid 1000 cloudmeet && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /var/lib/prosody cloudmeet && install -d -o 1000 -g 1000 /var/lib/prosody /var/lib/prosody/data /run/prosody/config /config /prosody-plugins-custom && rm -rf /var/lib/apt/lists/*
COPY --from=compiler /stage/opt/cloudmeet-prosody/ /opt/cloudmeet-prosody/
COPY jitsi-plugins/upstream/ /prosody-plugins/
COPY docker/prosody/rootfs/prosody-plugins/ /prosody-plugins/
COPY jitsi-plugins/cloudmeet/ /prosody-plugins-custom/
ENV PATH="/opt/cloudmeet-prosody/bin:${PATH}"
USER 1000:1000
