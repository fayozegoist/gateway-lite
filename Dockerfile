FROM alpine:3.20

# Base OS ringan: Alpine Linux (~5MB)
# Semua kebutuhan di-install dari paket apk yang sangat kecil.

RUN apk add --no-cache \
    dropbear \
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