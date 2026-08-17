#!/usr/bin/env python3
"""
Penyimpanan settings GatewayLite.

Prioritas nilai: settings.json (diubah dari Admin Panel) > env var > default.

Fungsi terapan (apply) langsung menulis ke file / menjalankan subprocess
sehingga perubahan dari Admin Panel aktif secara live tanpa redeploy.
"""

import json
import os
import subprocess

SETTINGS_DIR = "/etc/gateway-lite"
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")
BANNER_FILE = "/etc/dropbear_banner"
RESPONSE_FILE = "/etc/profile.d/99-respon-server.sh"
BASH_RC = "clear\nR='\\e[1;31m'; G='\\e[1;32m'; C='\\e[1;36m'; N='\\e[0m'\n" \
          "alias c='clear'\nalias x='exit'\nalias +x='chmod +x'\nalias cls='clear;ls'\nmenu\n"

DEFAULT_BANNER = """\x1b[1;31m         ⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠛⢉⢉⠉⠉⠻⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;33m         ⣿⣿⣿⣿⣿⣿⣿⠟⠠⡰⣕⣗⣷⣧⣀⣅⠘⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;32m         ⣿⣿⣿⣿⣿⣿⠃⣠⣳⣟⣿⣿⣷⣿⡿⣜⠄⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;36m         ⣿⣿⣿⣿⡿⠁⠄⣳⢷⣿⣿⣿⣿⡿⣝⠖⠄⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;34m         ⣿⣿⣿⣿⠃⠄⢢⡹⣿⢷⣯⢿⢷⡫⣗⠍⢰⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;35m         ⣿⣿⣿⡏⢀⢄⠤⣁⠋⠿⣗⣟⡯⡏⢎⠁⢸⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;31m         ⣿⣿⣿⠄⢔⢕⣯⣿⣿⡲⡤⡄⡤⠄⡀⢠⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;33m         ⣿⣿⠇⠠⡳⣯⣿⣿⣾⢵⣫⢎⢎⠆⢀⣿⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;32m         ⣿⣿⠄⢨⣫⣿⣿⡿⣿⣻⢎⡗⡕⡅⢸⣿⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;36m         ⣿⣿⠄⢜⢾⣾⣿⣿⣟⣗⢯⡪⡳⡀⢸⣿⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;34m         ⣿⣿⠄⢸⢽⣿⣷⣿⣻⡮⡧⡳⡱⡁⢸⣿⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;35m         ⣿⣿⡄⢨⣻⣽⣿⣟⣿⣞⣗⡽⡸⡐⢸⣿⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;31m         ⣿⣿⡇⢀⢗⣿⣿⣿⣿⡿⣞⡵⡣⣊⢸⣿⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;33m         ⣿⣿⣿⡀⡣⣗⣿⣿⣿⣿⣯⡯⡺⣼⠎⣿⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;32m         ⣿⣿⣿⣧⠐⡵⣻⣟⣯⣿⣷⣟⣝⢞⡿⢹⣿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;36m         ⣿⣿⣿⣿⡆⢘⡺⣽⢿⣻⣿⣗⡷⣹⢩⢃⢿⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;34m         ⣿⣿⣿⣿⣷⠄⠪⣯⣟⣿⢯⣿⣻⣜⢎⢆⠜⣿⣿⣿⣿⣿         \x1b[0m
\x1b[1;35m         ⣿⣿⣿⣿⣿⡆⠄⢣⣻⣽⣿⣿⣟⣾⡮⡺⡸⠸⣿⣿⣿⣿         \x1b[0m
\x1b[1;31m         ⣿⣿⡿⠛⠉⠁⠄⢕⡳⣽⡾⣿⢽⣯⡿⣮⢚⣅⠹⣿⣿⣿         \x1b[0m
\x1b[1;33m         ⡿⠋⠄⠄⠄⠄⢀⠒⠝⣞⢿⡿⣿⣽⢿⡽⣧⣳⡅⠌⠻⣿         \x1b[0m
\x1b[1;32m         ⠁⠄⠄⠄⠄⠄⠐⡐⠱⡱⣻⡻⣝⣮⣟⣿⣻⣟⣻⡺⣊          \x1b[0m

\x1b[1;36m========================================\x1b[0m
\x1b[1;32m         Welcome To GatewayLite         \x1b[0m
\x1b[1;36m========================================\x1b[0m
\x1b[1;33m    Join Channel Tele: @MediafairyCH    \x1b[0m
\x1b[1;36m========================================\x1b[0m"""

DEFAULT_RESPONSE = """#!/bin/bash
clear
echo -e "\\e[1;36m=================================================\\e[0m"
echo -e "\\e[1;32m       [✓] BERHASIL TERHUBUNG KE SERVER!         \\e[0m"
echo -e "\\e[1;36m=================================================\\e[0m"
echo -e "\\e[1;37m Username     : \\e[1;33m$USER\\e[0m"
echo -e "\\e[1;37m Waktu Server : \\e[1;33m$(date)\\e[0m"
echo -e "\\e[1;37m OS           : \\e[1;33mAlpine (GatewayLite Mode)\\e[0m"
echo -e "\\e[1;36m=================================================\\e[0m"
echo -e "\\e[1;31m   TETAP PATUHI RULES SERVER AGAR TIDAK BANNED   \\e[0m"
echo -e "\\e[1;36m=================================================\\e[0m"
"""

KEYS = ("uuid", "name", "cfip", "cfport", "argo_domain", "token",
        "ssh_user", "ssh_password", "banner", "response", "quick_tunnel")


def env_defaults():
    return {
        "uuid": os.environ.get("UUID", ""),
        "name": os.environ.get("NAME", "GATEWAYLITE"),
        "cfip": os.environ.get("CFIP", "saas.sin.fan"),
        "cfport": int(os.environ.get("CFPORT", "443") or 443),
        "argo_domain": os.environ.get("ARGO_DOMAIN", ""),
        "token": os.environ.get("TOKEN", ""),
        "ssh_user": os.environ.get("SSH_USER", "jatim"),
        "ssh_password": os.environ.get("SSH_PASSWORD", "jatim"),
        "banner": DEFAULT_BANNER,
        "response": DEFAULT_RESPONSE,
        "quick_tunnel": os.environ.get("QUICK_TUNNEL", "1") == "1",
    }


def load():
    """settings.json > env > default."""
    data = env_defaults()
    try:
        with open(SETTINGS_FILE) as f:
            stored = json.load(f)
        for k in KEYS:
            if k in stored:
                data[k] = stored[k]
    except Exception:
        pass
    data["cfport"] = int(data.get("cfport") or 443)
    data["quick_tunnel"] = bool(data.get("quick_tunnel"))
    return data


def save(data):
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    clean = {k: data.get(k) for k in KEYS}
    with open(SETTINGS_FILE, "w") as f:
        json.dump(clean, f, indent=2)


def public_view(data):
    """Versi aman untuk ditampilkan (token dimasking)."""
    view = dict(data)
    tok = view.get("token") or ""
    if len(tok) > 12:
        view["token"] = tok[:6] + "…" * 8 + tok[-4:]
    elif tok:
        view["token"] = tok[:3] + "…"
    return view


def apply_banner(banner):
    try:
        with open(BANNER_FILE, "w") as f:
            f.write(banner or "")
    except Exception:
        pass


def apply_response(response):
    try:
        with open(RESPONSE_FILE, "w") as f:
            f.write(response or "")
        os.chmod(RESPONSE_FILE, 0o755)
    except Exception:
        pass


def apply_ssh_user(user, password):
    """Buat (jika belum) + set password user utama, plus .bashrc menu."""
    try:
        r = subprocess.run(["id", user], capture_output=True)
        if r.returncode != 0:
            subprocess.run(["useradd", "-m", "-s", "/bin/bash", user], check=True)
            subprocess.run(["groupadd", "-f", "wheel"], check=True)
            subprocess.run(["usermod", "-aG", "wheel", user], check=True)
        proc = subprocess.Popen(["chpasswd"], stdin=subprocess.PIPE)
        proc.communicate(f"{user}:{password}".encode())
        home = f"/home/{user}"
        if os.path.isdir(home):
            with open(os.path.join(home, ".bashrc"), "w") as f:
                f.write(BASH_RC)
    except Exception:
        pass


def apply_all(data):
    apply_banner(data.get("banner"))
    apply_response(data.get("response"))
    apply_ssh_user(data.get("ssh_user"), data.get("ssh_password"))
