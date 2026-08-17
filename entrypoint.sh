#!/bin/bash

SSH_USER="${SSH_USER:-hidup}"
SSH_PASS="${SSH_PASSWORD:-jokowi}"

# Port PUBLIK (Railway inject $PORT untuk HTTP domain otomatis)
PUBLIC_PORT="${PORT:-8080}"

# Port INTERNAL
SSL_INTERNAL_PORT="${SSL_INTERNAL_PORT:-2443}"
WS_INTERNAL_PORT="${WS_INTERNAL_PORT:-8880}"
XRAY_PORT="${XRAY_PORT:-8001}"
DASH_PORT="${DASH_PORT:-3000}"

# Cloudflare Tunnel token (boleh banyak, dipisah koma)
TOKEN="${TOKEN:-}"
QUICK_TUNNEL="${QUICK_TUNNEL:-1}"   # quick tunnel trycloudflare bila TOKEN kosong

mkdir -p /opt/gateway/bin /opt/gateway/logs /etc/ssh-sni

echo "[*] Mengonfigurasi Respon Server (pasca-login)..."
cat << 'EOF' > /etc/profile.d/99-respon-server.sh
#!/bin/bash
clear
echo "⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠛⢉⢉⠉⠉⠻⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⣿⣿⣿⣿⠟⠠⡰⣕⣗⣷⣧⣀⣅⠘⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⣿⣿⣿⠃⣠⣳⣟⣿⣿⣷⣿⡿⣜⠄⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⣿⡿⠁⠄⣳⢷⣿⣿⣿⣿⡿⣝⠖⠄⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⣿⠃⠄⢢⡹⣿⢷⣯⢿⢷⡫⣗⠍⢰⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⡏⢀⢄⠤⣁⠋⠿⣗⣟⡯⡏⢎⠁⢸⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⠄⢔⢕⣯⣿⣿⡲⡤⡄⡤⠄⡀⢠⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⠇⠠⡳⣯⣿⣿⣾⢵⣫⢎⢎⠆⢀⣿⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⠄⢨⣫⣿⣿⡿⣿⣻⢎⡗⡕⡅⢸⣿⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⠄⢜⢾⣾⣿⣿⣟⣗⢯⡪⡳⡀⢸⣿⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⠄⢸⢽⣿⣷⣿⣻⡮⡧⡳⡱⡁⢸⣿⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⡄⢨⣻⣽⣿⣟⣿⣞⣗⡽⡸⡐⢸⣿⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⡇⢀⢗⣿⣿⣿⣿⡿⣞⡵⡣⣊⢸⣿⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⡀⡣⣗⣿⣿⣿⣿⣯⡯⡺⣼⠎⣿⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⣧⠐⡵⣻⣟⣯⣿⣷⣟⣝⢞⡿⢹⣿⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⣿⡆⢘⡺⣽⢿⣻⣿⣗⡷⣹⢩⢃⢿⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⣿⣷⠄⠪⣯⣟⣿⢯⣿⣻⣜⢎⢆⠜⣿⣿⣿⣿⣿"
echo "⣿⣿⣿⣿⣿⡆⠄⢣⣻⣽⣿⣿⣟⣾⡮⡺⡸⠸⣿⣿⣿⣿"
echo "⣿⣿⡿⠛⠉⠁⠄⢕⡳⣽⡾⣿⢽⣯⡿⣮⢚⣅⠹⣿⣿⣿"
echo "⡿⠋⠄⠄⠄⠄⢀⠒⠝⣞⢿⡿⣿⣽⢿⡽⣧⣳⡅⠌⠻⣿"
echo "⠁⠄⠄⠄⠄⠄⠐⡐⠱⡱⣻⡻⣝⣮⣟⣿⣻⣟⣻⡺⣊"

EOF
chmod +x /etc/profile.d/99-respon-server.sh

echo "[*] Mengonfigurasi User SSH..."
if [ -n "$SSH_USER" ] && [ -n "$SSH_PASS" ]; then
    if ! id "$SSH_USER" &>/dev/null; then
        useradd -m -s /bin/bash "$SSH_USER"
        groupadd -f wheel
        usermod -aG wheel "$SSH_USER"
    fi
    echo "$SSH_USER:$SSH_PASS" | chpasswd
    cp /root/.bashrc "/home/$SSH_USER/.bashrc" 2>/dev/null
fi

cat >> /root/.bashrc << 'EOF'
clear
R='\e[1;31m'; G='\e[1;32m'; C='\e[1;36m'; N='\e[0m'
alias c='clear'
alias x='exit'
alias +x='chmod +x'
alias cls='clear;ls'
menu
EOF

echo "[*] Memulai Dropbear di 127.0.0.1:22 ..."
/usr/sbin/dropbear -R -p 127.0.0.1:22 -W 65536

echo "[*] Memulai Stunnel (internal, port $SSL_INTERNAL_PORT)..."
cat > /etc/stunnel/stunnel.conf << EOF
pid = /var/run/stunnel.pid
foreground = yes
debug = 4

[ssh-ssl]
accept = 127.0.0.1:$SSL_INTERNAL_PORT
connect = 127.0.0.1:22
cert = /etc/stunnel/stunnel.pem
EOF
stunnel /etc/stunnel/stunnel.conf &

echo "[*] Memulai WebSocket Proxy (internal, port $WS_INTERNAL_PORT)..."
WS_PORT="$WS_INTERNAL_PORT" WS_TARGET_HOST="127.0.0.1" WS_TARGET_PORT="22" \
    python3 /opt/gateway/ws-proxy.py &

echo "[*] Download Xray (multi-source, auto-fallback)..."
python3 /opt/gateway/download-bin.py xray /opt/gateway/bin/xray
chmod +x /opt/gateway/bin/xray 2>/dev/null

echo "[*] Generate config Xray (VLESS/VMESS/TROJAN WS di port $XRAY_PORT)..."
UUID="${UUID:-$(cat /proc/sys/kernel/random/uuid)}" XRAY_PORT="$XRAY_PORT" \
    python3 /opt/gateway/gen-xray-config.py /opt/gateway/config.json
/opt/gateway/bin/xray -c /opt/gateway/config.json &

echo "[*] Download cloudflared (multi-source, auto-fallback)..."
python3 /opt/gateway/download-bin.py cloudflared /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared 2>/dev/null

echo "[*] Memulai Dashboard + pengelola tunnel (internal, port $DASH_PORT)..."
# cloudflared (TOKEN / quick-tunnel) dikelola oleh dashboard: perubahan
# TOKEN dari Admin Panel langsung di-restart tanpa redeploy.
UUID="$UUID" DASH_PORT="$DASH_PORT" TOKEN="$TOKEN" PUBLIC_PORT="$PUBLIC_PORT" \
    ADMIN_USER="${ADMIN_USER:-}" ADMIN_PASSWORD="${ADMIN_PASSWORD:-}" \
    python3 /opt/gateway/dashboard.py &

echo "[*] Memulai Mux di port PUBLIK $PUBLIC_PORT (TLS/WS/HTTP auto-routing)..."
exec env \
    PORT="$PUBLIC_PORT" \
    SSL_TARGET_HOST="127.0.0.1" SSL_TARGET_PORT="$SSL_INTERNAL_PORT" \
    WS_MUX_TARGET_HOST="127.0.0.1" WS_MUX_TARGET_PORT="$WS_INTERNAL_PORT" \
    XRAY_MUX_TARGET_HOST="127.0.0.1" XRAY_MUX_TARGET_PORT="$XRAY_PORT" \
    DASH_MUX_TARGET_HOST="127.0.0.1" DASH_MUX_TARGET_PORT="$DASH_PORT" \
    python3 /opt/gateway/mux.py