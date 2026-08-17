# ============================================================
# Stage 1: build dropbear 2019.78 dari source (musl/Alpine 3.20)
# ============================================================
FROM alpine:3.20 AS dropbear-builder

RUN apk add --no-cache \
    curl \
    tar \
    bzip2 \
    make \
    gcc \
    musl-dev \
    linux-headers \
    binutils \
    && rm -rf /var/cache/apk/*

RUN set -eux; \
    cd /tmp; \
    curl -fsSL -o dropbear-2019.78.tar.bz2 \
      "https://matt.ucc.asn.au/dropbear/releases/dropbear-2019.78.tar.bz2"; \
    tar xjf dropbear-2019.78.tar.bz2; \
    cd dropbear-2019.78; \
    ./configure --prefix=/opt/dropbear \
      --disable-zlib \
      --disable-pam \
      --disable-lastlog \
      --disable-utmp \
      --disable-wtmp \
      --disable-utmpx \
      --disable-wtmpx \
      --disable-syslog; \
    make -j"$(nproc)"; \
    make install; \
    strip /opt/dropbear/sbin/dropbear

# ============================================================
# Stage 2: image final
# ============================================================
FROM alpine:3.20

# Base OS ringan: Alpine Linux (~5MB)
# Semua kebutuhan di-install dari paket apk yang sangat kecil.

RUN apk add --no-cache \
    stunnel \
    openssl \
    python3 \
    bash \
    sudo \
    shadow \
    curl \
    ca-certificates \
    procps \
    tzdata \
    && rm -rf /var/cache/apk/*

# dropbear versi 2019.78 (build dari source, menggantikan paket apk)
COPY --from=dropbear-builder /opt/dropbear/sbin/dropbear /usr/sbin/dropbear

# Direktori run + data
RUN mkdir -p /var/run/dropbear /var/run/stunnel /etc/dropbear /etc/stunnel \
    /etc/ssh-sni /etc/gateway-lite /opt/gateway/bin /opt/gateway/logs

# Satu sertifikat self-signed untuk Stunnel
RUN openssl req -new -newkey rsa:2048 -days 365 -nodes -x509 \
    -subj "/C=ID/ST=Jakarta/L=Jakarta/O=GatewayLite/CN=localhost" \
    -keyout /etc/stunnel/stunnel.pem -out /etc/stunnel/stunnel.pem

# Sudoers: grup wheel (Alpine memakai wheel, bukan sudo)
RUN echo "%wheel ALL=(ALL) ALL" > /etc/sudoers.d/wheel \
    && chmod 440 /etc/sudoers.d/wheel

# Entry point + script Python inti
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY mux.py ws-proxy.py dashboard.py gen-xray-config.py download-bin.py settings.py /opt/gateway/
RUN chmod +x /opt/gateway/*.py

# UI (monochrome) + template dashboard/admin
COPY web/ /opt/gateway/web/

# Manajemen akun SSH (versi Alpine)
COPY addssh delssh listssh menu /usr/local/bin/
RUN chmod +x /usr/local/bin/addssh /usr/local/bin/delssh /usr/local/bin/listssh /usr/local/bin/menu

# Satu port publik: mux.py menangani TLS/WS/HTTP secara otomatis
# Railway meng-inject $PORT -> HTTP domain otomatis aktif tanpa setup manual
EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]