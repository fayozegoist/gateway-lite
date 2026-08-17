#!/usr/bin/env python3
"""
Generate config.json untuk Xray-core.

Inbound publik di XRAY_PORT (VLESS+XTLS Vision over TCP + fallback),
lalu inbound internal WS untuk VLESS/VMESS/TROJAN. Fallback memastikan
koneksi WS dari mux dialihkan ke inbound WS yang sesuai.
"""

import json
import os
import sys

UUID = os.environ.get("UUID", "")
XRAY_PORT = int(os.environ.get("XRAY_PORT", "8001"))

config = {
    "log": {"access": "/dev/null", "error": "/dev/null", "loglevel": "none"},
    "inbounds": [
        {
            "port": XRAY_PORT,
            "protocol": "vless",
            "settings": {
                "clients": [{"id": UUID, "flow": "xtls-rprx-vision"}],
                "decryption": "none",
                "fallbacks": [
                    {"dest": 3001},
                    {"path": "/vless-mediafairy", "dest": 3002},
                    {"path": "/vmess-mediafairy", "dest": 3003},
                    {"path": "/trojan-mediafairy", "dest": 3004},
                ],
            },
            "streamSettings": {"network": "tcp"},
        },
        {
            "port": 3001,
            "listen": "127.0.0.1",
            "protocol": "vless",
            "settings": {"clients": [{"id": UUID}], "decryption": "none"},
            "streamSettings": {"network": "tcp", "security": "none"},
        },
        {
            "port": 3002,
            "listen": "127.0.0.1",
            "protocol": "vless",
            "settings": {"clients": [{"id": UUID, "level": 0}], "decryption": "none"},
            "streamSettings": {"network": "ws", "security": "none",
                               "wsSettings": {"path": "/vless-mediafairy"}},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"],
                         "metadataOnly": False},
        },
        {
            "port": 3003,
            "listen": "127.0.0.1",
            "protocol": "vmess",
            "settings": {"clients": [{"id": UUID, "alterId": 0}]},
            "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess-mediafairy"}},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"],
                         "metadataOnly": False},
        },
        {
            "port": 3004,
            "listen": "127.0.0.1",
            "protocol": "trojan",
            "settings": {"clients": [{"password": UUID}]},
            "streamSettings": {"network": "ws", "security": "none",
                               "wsSettings": {"path": "/trojan-mediafairy"}},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"],
                         "metadataOnly": False},
        },
    ],
    "dns": {"servers": ["https+local://8.8.8.8/dns-query"]},
    "outbounds": [
        {"protocol": "freedom", "tag": "direct"},
        {"protocol": "blackhole", "tag": "block"},
    ],
}

out = sys.argv[1] if len(sys.argv) > 1 else "/opt/gateway/config.json"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump(config, f, indent=2)
print(f"[xray] config ditulis -> {out}")