FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential lua5.4 liblua5.4-dev libssl-dev libicu-dev \
    lua-socket lua-sec lua-luaossl lua-cjson && rm -rf /var/lib/apt/lists/*
COPY prosody/ /src/prosody/
WORKDIR /src/prosody
RUN sh ./configure --ostype=debian --prefix=/opt/cloudmeet-prosody \
    --sysconfdir=/run/prosody/config --datadir=/var/lib/prosody/data \
    --lua-version=5.4 --lua-suffix=5.4 --idn-library=icu --no-example-certs \
    && make -j2 && make install
COPY tests/host-transfer.lua /smoke/host-transfer.lua
COPY jitsi-plugins/cloudmeet/mod_muc_host_transfer.lua /smoke/mod_muc_host_transfer.lua
USER 1000:1000
CMD ["sh", "-ec", "lua5.4 -e 'require(\"ssl\"); require(\"openssl.hmac\"); require(\"openssl.pkey\"); require(\"cjson.safe\")'; luac5.4 -p /smoke/mod_muc_host_transfer.lua; lua5.4 /smoke/host-transfer.lua /smoke/mod_muc_host_transfer.lua"]
