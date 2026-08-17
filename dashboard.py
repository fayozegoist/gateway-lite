#!/usr/bin/env python3
"""
GatewayLite Dashboard + Admin Panel.

- Publik (tanpa login): generate node, create SSH, sub.txt, stats.
- Admin (login, hanya aktif bila env ADMIN_USER & ADMIN_PASSWORD di-set):
  ubah settings (TOKEN, banner, dll) dan terapkan live tanpa redeploy.

Dashboard juga yang mengelola proses cloudflared (token / quick-tunnel) dan
Xray, sehingga perubahan TOKEN / UUID langsung diterapkan ke layanan.
"""

import base64
import datetime
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settings as S

WEB_DIR = "/opt/gateway/web"
PUBLIC_PORT = int(os.environ.get("PORT", "8080"))
DASH_PORT = int(os.environ.get("DASH_PORT", "3000"))
XRAY_PORT = int(os.environ.get("XRAY_PORT", "8001"))
XRAY_BIN = "/opt/gateway/bin/xray"
XRAY_CFG = "/opt/gateway/config.json"
CLOUDFLARED = "/usr/local/bin/cloudflared"
BOOT_LOG = "/opt/gateway/logs/boot.log"
SUB_FILE = "/opt/gateway/sub.txt"
USERS_FILE = "/etc/ssh-sni/users.json"

ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_ENABLED = bool(ADMIN_USER and ADMIN_PASSWORD)
SESSION_TTL = 24 * 3600

BOOT_TIME = time.time()
SESSIONS = {}
LOGIN_FAILS = {}

_last_cpu = None
_domains = []
_tunnels = None
_xray_proc = None


# ============================== STATS ==============================

def read_net():
    rx = tx = 0
    try:
        with open("/proc/net/dev") as f:
            for line in f.readlines()[2:]:
                parts = line.split()
                if not parts or "lo:" in line:
                    continue
                rx += int(parts[1])
                tx += int(parts[9])
    except Exception:
        pass
    return rx, tx


def read_cpu():
    global _last_cpu
    try:
        with open("/proc/stat") as f:
            vals = list(map(int, f.readline().split()[1:]))
        idle = vals[3] + vals[4]
        total = sum(vals)
        if _last_cpu:
            idle_d = idle - _last_cpu["idle"]
            total_d = total - _last_cpu["total"]
            pct = 0.0 if total_d == 0 else max(0.0, 100 - 100 * idle_d / total_d)
        else:
            pct = 0.0
        _last_cpu = {"idle": idle, "total": total}
        return round(pct, 1)
    except Exception:
        return 0.0


def read_ram():
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) * 1024
        total = info.get("MemTotal", 1)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        return round(100 - 100 * avail / total, 1)
    except Exception:
        return 0.0


# ============================== LINK GEN ==============================

def gen_vless(host, d):
    return (f"vless://{d['uuid']}@{d['cfip']}:{d['cfport']}?encryption=none&security=tls&sni={host}"
            f"&fp=firefox&type=ws&host={host}&path=%2Fvless-mediafairy#{d['name']}-VLESS")


def gen_vmess(host, d):
    obj = {
        "v": "2", "ps": f"{d['name']}-VMESS", "add": d['cfip'], "port": d['cfport'],
        "id": d['uuid'], "aid": "0", "scy": "auto", "net": "ws", "type": "none",
        "host": host, "path": "/vmess-mediafairy", "tls": "tls", "sni": host,
        "alpn": "", "fp": "firefox",
    }
    return f"vmess://{base64.b64encode(json.dumps(obj).encode()).decode()}"


def gen_trojan(host, d):
    return (f"trojan://{d['uuid']}@{d['cfip']}:{d['cfport']}?security=tls&sni={host}&fp=firefox"
            f"&type=ws&host={host}&path=%2Ftrojan-mediafairy#{d['name']}-TROJAN")


def write_sub():
    try:
        with open(SUB_FILE, "w") as f:
            d = S.load()
            for dom in _domains:
                f.write(gen_vless(dom, d) + "\n")
                f.write(gen_vmess(dom, d) + "\n")
                f.write(gen_trojan(dom, d) + "\n")
    except Exception:
        pass


def config_payload(host):
    d = S.load()
    native = {"vless": gen_vless(host, d), "trojan": gen_trojan(host, d)}
    ds = list(_domains)
    if ds:
        dom = ds[0]
        argo = {"vless": gen_vless(dom, d), "vmess": gen_vmess(dom, d), "trojan": gen_trojan(dom, d)}
    else:
        argo = {"vless": "Menunggu tunnel aktif...",
                "vmess": "Menunggu tunnel aktif...",
                "trojan": "Menunggu tunnel aktif..."}
    return {"native": native, "argo": argo}


# ============================== TUNNEL / XRAY ==============================

class TunnelManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.procs = []
        self.status = "stopped"
        self.detail = "belum disinkronkan"

    def stop(self):
        with self.lock:
            for p in self.procs:
                try:
                    p.terminate()
                except Exception:
                    pass
                try:
                    p.wait(timeout=5)
                except Exception:
                    pass
            self.procs = []

    def sync(self):
        self.stop()
        d = S.load()
        token = d.get("token") or ""
        quick = bool(d.get("quick_tunnel"))
        tokens = [t.strip() for t in token.split(",") if t.strip()]
        procs = []
        detail = ""
        status = "stopped"
        if tokens:
            for t in tokens:
                cmd = [CLOUDFLARED, "--logfile", BOOT_LOG, "--loglevel", "info",
                       "tunnel", "run", "--token", t]
                try:
                    procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                                  stderr=subprocess.DEVNULL))
                except Exception as e:
                    detail = f"error: {e}"
            status = "token" if procs else "error"
            detail = detail or f"{len(procs)} tunnel(s)"
        elif quick:
            cmd = [CLOUDFLARED, "--logfile", BOOT_LOG, "--loglevel", "info",
                   "tunnel", "--edge-ip-version", "auto", "--no-autoupdate",
                   "--protocol", "http2", "--url", f"http://127.0.0.1:{PUBLIC_PORT}"]
            try:
                procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL))
            except Exception as e:
                detail = f"error: {e}"
            status = "quick" if procs else "error"
            detail = detail or "trycloudflare"
        else:
            status = "stopped"
            detail = "tunnel off"
        with self.lock:
            self.procs = procs
        self.status = status
        self.detail = detail
        print(f"[dashboard] tunnel sync: {status} — {detail}", flush=True)


def stop_xray():
    global _xray_proc
    if _xray_proc is not None:
        try:
            _xray_proc.terminate()
        except Exception:
            pass
        _xray_proc = None
    try:
        subprocess.run(["pkill", "-f", XRAY_BIN], capture_output=True)
    except Exception:
        pass


def start_xray(uuid):
    global _xray_proc
    stop_xray()
    try:
        env = dict(os.environ)
        env["UUID"] = uuid
        env["XRAY_PORT"] = str(XRAY_PORT)
        subprocess.run([sys.executable, "/opt/gateway/gen-xray-config.py", XRAY_CFG],
                       env=env, check=True, capture_output=True)
    except Exception as e:
        print(f"[dashboard] xray config error: {e}", flush=True)
    try:
        _xray_proc = subprocess.Popen([XRAY_BIN, "-c", XRAY_CFG],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[dashboard] xray started (uuid {uuid[:8]}...)", flush=True)
    except Exception as e:
        print(f"[dashboard] xray start error: {e}", flush=True)


def xray_running():
    if _xray_proc is not None and _xray_proc.poll() is None:
        return True
    try:
        return subprocess.call(["pgrep", "-x", os.path.basename(XRAY_BIN)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


# ============================== SSH ACCOUNTS ==============================

def load_users():
    try:
        with open(USERS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def create_ssh(username, password, days=None):
    if not re.match(r"^[a-zA-Z0-9_.-]{3,32}$", username):
        raise ValueError("Username tidak valid (3-32 char: a-z 0-9 _ . -)")
    if not password or len(password) < 6:
        raise ValueError("Password minimal 6 karakter")
    if subprocess.call(["id", username], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        raise ValueError(f"User {username} sudah ada")

    subprocess.run(["useradd", "-m", "-s", "/bin/bash", username], check=True)
    subprocess.run(["groupadd", "-f", "wheel"], check=True)
    subprocess.run(["usermod", "-aG", "wheel", username], check=True)
    proc = subprocess.Popen(["chpasswd"], stdin=subprocess.PIPE)
    proc.communicate(f"{username}:{password}".encode())
    if proc.returncode != 0:
        raise RuntimeError("Gagal set password")

    if days:
        exp = (datetime.datetime.now() + datetime.timedelta(days=int(days))).strftime("%Y-%m-%d")
        subprocess.run(["chage", "-E", exp, username], check=True)
    else:
        exp = "never"

    users = load_users()
    users[username] = {
        "password": password,
        "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expired": exp,
    }
    save_users(users)
    return exp


def delete_ssh(username):
    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
    subprocess.run(["userdel", "-r", username], capture_output=True)


# ============================== DOMAIN POLLER ==============================

def domain_poller():
    global _domains
    while True:
        try:
            found = []
            if os.path.exists(BOOT_LOG):
                with open(BOOT_LOG) as f:
                    text = f.read()
                found = list(dict.fromkeys(re.findall(r"https?://([^ \n]*trycloudflare\.com)", text)))
            d = S.load()
            if d.get("argo_domain") and d.get("token"):
                found = [d["argo_domain"]] + found
            if found != _domains:
                _domains = found
                write_sub()
                print(f"[dashboard] domains: {_domains}", flush=True)
        except Exception:
            pass
        time.sleep(5)


def ssh_endpoints(req_host):
    """Endpoint SSH untuk ditampilkan: Domain SSL (Railway) & Domain WS (Cloudflare)."""
    d = S.load()
    req_host = (req_host or "").split(":")[0]
    ssl_host = (os.environ.get("SSL_HOST") or "").strip() or req_host
    ssl_port = (os.environ.get("SSL_PORT") or "").strip() or "443"
    ws_host = (d.get("argo_domain") or "").strip()
    if not ws_host:
        ws_host = next((x for x in _domains if x != req_host), "")
    if not ws_host:
        ws_host = req_host
    return {
        "ssl": {"label": "Domain SSL", "host": ssl_host, "port": ssl_port},
        "ws": {"label": "Domain WS", "host": ws_host, "port": "443"},
    }


# ============================== AUTH ==============================

def login_ok(user, password):
    return ADMIN_ENABLED and user == ADMIN_USER and password == ADMIN_PASSWORD


def check_rate(ip):
    now = time.time()
    fails = [t for t in LOGIN_FAILS.get(ip, []) if now - t < 600]
    LOGIN_FAILS[ip] = fails
    return len(fails) >= 5


def record_fail(ip):
    LOGIN_FAILS.setdefault(ip, []).append(time.time())


# ============================== HTTP ==============================

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # --- helpers ---
    def _send(self, code, ctype, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if ctype.startswith("text/html"):
            self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code=200, extra=None):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(payload).encode(), extra=extra)

    def _file(self, name):
        path = os.path.join(WEB_DIR, name)
        try:
            with open(path, "rb") as f:
                body = f.read()
            ext = os.path.splitext(name)[1]
            self._send(200, MIME.get(ext, "text/plain; charset=utf-8"), body)
        except FileNotFoundError:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def _session_user(self):
        m = re.search(r"gw_session=([^;]+)", self.headers.get("Cookie", "") or "")
        if not m:
            return False
        tok = m.group(1)
        if tok in SESSIONS and SESSIONS[tok] > time.time():
            return True
        SESSIONS.pop(tok, None)
        return False

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _host(self):
        return self.headers.get("Host", "localhost")

    # --- routes ---
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/stats":
            self._json({
                "uptime": int(time.time() - BOOT_TIME),
                "rx": read_net()[0], "tx": read_net()[1],
                "cpu": read_cpu(), "ram": read_ram(),
            })
            return

        if path == "/api/config":
            self._json(config_payload(self._host()))
            return

        if path == "/sub.txt":
            body = b""
            try:
                with open(SUB_FILE, "rb") as f:
                    body = f.read()
            except Exception:
                pass
            self._send(200, "text/plain; charset=utf-8", body)
            return

        if path == "/":
            self._file("public.html")
            return

        if path == "/style.css":
            self._file("style.css")
            return

        if path == "/login":
            if not ADMIN_ENABLED:
                self._send(404, "text/plain; charset=utf-8", b"not found")
                return
            self._file("login.html")
            return

        if path == "/admin":
            if not ADMIN_ENABLED:
                self._send(404, "text/plain; charset=utf-8", b"not found")
                return
            if not self._session_user():
                self._send(302, "text/plain; charset=utf-8", b"", {"Location": "/login"})
                return
            self._file("admin.html")
            return

        if path == "/api/admin/status":
            if not self._session_user():
                self._json({"error": "unauthorized"}, 403)
                return
            self._json({
                "tunnel": {"status": _tunnels.status, "detail": _tunnels.detail},
                "xray": {"running": xray_running()},
                "domains": _domains,
                "admin_enabled": ADMIN_ENABLED,
            })
            return

        if path == "/api/admin/settings":
            if not self._session_user():
                self._json({"error": "unauthorized"}, 403)
                return
            self._json({"settings": S.public_view(S.load())})
            return

        if path == "/api/admin/users":
            if not self._session_user():
                self._json({"error": "unauthorized"}, 403)
                return
            self._json({"users": load_users()})
            return

        if path == "/api/admin/logs":
            if not self._session_user():
                self._json({"error": "unauthorized"}, 403)
                return
            tail = ""
            try:
                with open(BOOT_LOG) as f:
                    tail = "".join(f.readlines()[-120:])
            except Exception:
                pass
            self._json({"logs": tail})
            return

        self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/ssh":
            body = self._read_body()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            try:
                days = int(body.get("days")) if body.get("days") else None
            except (ValueError, TypeError):
                days = None
            try:
                exp = create_ssh(username, password, days)
                ep = ssh_endpoints(self._host())
                self._json({"ok": True, "username": username, "password": password,
                            "expired": exp, "host": ep["ssl"]["host"],
                            "port": ep["ssl"]["port"],
                            "ssl": ep["ssl"], "ws": ep["ws"]})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if path == "/api/login":
            if not ADMIN_ENABLED:
                self._json({"error": "not found"}, 404)
                return
            ip = self.client_address[0]
            if check_rate(ip):
                self._json({"error": "terlalu banyak percobaan, coba lagi nanti"}, 429)
                return
            body = self._read_body()
            if login_ok(str(body.get("username", "")), str(body.get("password", ""))):
                tok = secrets.token_urlsafe(32)
                SESSIONS[tok] = time.time() + SESSION_TTL
                self._json({"ok": True, "redirect": "/admin"},
                           extra={"Set-Cookie": f"gw_session={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}"})
            else:
                record_fail(ip)
                self._json({"ok": False, "error": "username/password salah"}, 401)
            return

        if path == "/api/logout":
            m = re.search(r"gw_session=([^;]+)", self.headers.get("Cookie", "") or "")
            if m:
                SESSIONS.pop(m.group(1), None)
            self._json({"ok": True},
                       extra={"Set-Cookie": "gw_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            return

        if not self._session_user():
            self._json({"error": "unauthorized"}, 403)
            return

        if path == "/api/admin/settings":
            body = self._read_body()
            data = S.load()
            changed_token = False
            changed_uuid = False
            if "token" in body and body["token"] != data.get("token"):
                data["token"] = str(body["token"]).strip()
                changed_token = True
            if "quick_tunnel" in body:
                data["quick_tunnel"] = bool(body["quick_tunnel"])
                changed_token = True
            for k in ("name", "cfip", "argo_domain", "ssh_user", "ssh_password",
                      "banner", "response"):
                if k in body:
                    data[k] = body[k]
            if "cfport" in body:
                try:
                    data["cfport"] = int(body["cfport"])
                except (ValueError, TypeError):
                    pass
            if "uuid" in body and body["uuid"] and body["uuid"] != data.get("uuid"):
                data["uuid"] = str(body["uuid"]).strip()
                changed_uuid = True
            S.save(data)
            S.apply_all(data)
            if changed_token:
                _tunnels.sync()
            if changed_uuid:
                start_xray(data["uuid"])
            self._json({"ok": True, "settings": S.public_view(S.load())})
            return

        if path == "/api/admin/tunnel/restart":
            _tunnels.sync()
            self._json({"ok": True, "tunnel": {"status": _tunnels.status, "detail": _tunnels.detail}})
            return

        if path == "/api/admin/xray/restart":
            start_xray(S.load().get("uuid"))
            self._json({"ok": True})
            return

        if path == "/api/admin/users/delete":
            body = self._read_body()
            username = str(body.get("username", ""))
            delete_ssh(username)
            self._json({"ok": True})
            return

        self._send(404, "text/plain; charset=utf-8", b"not found")


def main():
    global _tunnels
    _tunnels = TunnelManager()

    d = S.load()
    S.apply_all(d)
    _tunnels.sync()

    env_uuid = os.environ.get("UUID", "")
    if d.get("uuid") and d["uuid"] != env_uuid:
        start_xray(d["uuid"])
    else:
        global _xray_proc
        _xray_proc = None

    threading.Thread(target=domain_poller, daemon=True).start()

    server = http.server.ThreadingHTTPServer(("0.0.0.0", DASH_PORT), Handler)
    print(f"[dashboard] GatewayLite aktif di 0.0.0.0:{DASH_PORT} "
          f"(admin={'ON' if ADMIN_ENABLED else 'OFF'})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()