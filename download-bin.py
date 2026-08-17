#!/usr/bin/env python3
"""
Download binary dengan MULTI-SOURCE + auto-fallback.

Mendukung:
  - xray        : official GitHub XTLS/Xray-core  -> mirror ssss.nyc.mn
  - cloudflared : official GitHub cloudflare/cloudflared -> mirror ssss.nyc.mn

Arsitektur dideteksi otomatis (amd64 / arm64) sehingga image tunggal
bisa jalan di banyak platform server.
"""

import os
import shutil
import sys
import urllib.request
import zipfile

ARCH = "arm64" if os.uname().machine in ("aarch64", "arm64", "arm") else "amd64"

SOURCES = {
    "xray": [
        f"https://github.com/XTLS/Xray-core/releases/latest/download/"
        f"Xray-linux-{'arm64-v8a' if ARCH == 'arm64' else '64'}.zip",
        f"https://{ARCH}.ssss.nyc.mn/web",
    ],
    "cloudflared": [
        f"https://github.com/cloudflare/cloudflared/releases/latest/download/"
        f"cloudflared-linux-{ARCH}",
        f"https://{ARCH}.ssss.nyc.mn/bot",
    ],
}


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def grab(kind, dest):
    last_err = None
    for src in SOURCES[kind]:
        tmp = f"/tmp/{kind}.bin"
        try:
            print(f"[download] coba {src}", flush=True)
            if src.endswith(".zip"):
                zpath = f"/tmp/{kind}.zip"
                download(src, zpath)
                with zipfile.ZipFile(zpath) as z:
                    names = z.namelist()
                    exe = next((n for n in names if n.endswith("xray")), None) \
                        or next((n for n in names if "xray" in n.lower()), None)
                    if not exe:
                        raise RuntimeError("file xray tidak ditemukan di dalam zip")
                    z.extract(exe, "/tmp/xray-x")
                shutil.move(f"/tmp/xray-x/{exe}", tmp)
            else:
                download(src, tmp)
            os.chmod(tmp, 0o755)
            shutil.move(tmp, dest)
            print(f"[download] OK -> {dest}", flush=True)
            return
        except Exception as e:
            last_err = e
            print(f"[download] gagal {src}: {e}", flush=True)
    raise SystemExit(f"[download] {kind}: semua source gagal -> {last_err}")


if __name__ == "__main__":
    kind = sys.argv[1]
    dest = sys.argv[2] if len(sys.argv) > 2 else f"/opt/gateway/bin/{kind}"
    grab(kind, dest)