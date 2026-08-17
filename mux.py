#!/usr/bin/env python3
"""
Unified TCP Multiplexer (alih-alih sslh) untuk GatewayLite.

Mendengarkan di SATU port publik dan mengintip byte pertama / header
untuk menentukan tujuan:

  - Byte pertama 0x16 (TLS handshake)              -> Stunnel (SSH-SSL)
  - HTTP + Upgrade: websocket + path Xray          -> Xray (VLESS/VMESS/TROJAN WS)
  - HTTP + Upgrade: websocket + path lain          -> ws-proxy (SSH-WS)
  - HTTP biasa (GET /, /api/*, /sub.txt)           -> Dashboard (Python)
  - Selain itu (biner/raw)                         -> ws-proxy (SSH-WS)

Dengan satu port ini, Railway hanya butuh 0 setup untuk HTTP/WS (via $PORT
domain + Argo) dan paling banyak 1 TCP Proxy manual untuk jalur SSL.
"""

import asyncio
import logging
import os
import re
import signal
import sys

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("PORT", "8080"))

SSL_TARGET_HOST = os.environ.get("SSL_TARGET_HOST", "127.0.0.1")
SSL_TARGET_PORT = int(os.environ.get("SSL_TARGET_PORT", "2443"))

WS_TARGET_HOST = os.environ.get("WS_MUX_TARGET_HOST", "127.0.0.1")
WS_TARGET_PORT = int(os.environ.get("WS_MUX_TARGET_PORT", "8880"))

XRAY_TARGET_HOST = os.environ.get("XRAY_MUX_TARGET_HOST", "127.0.0.1")
XRAY_TARGET_PORT = int(os.environ.get("XRAY_MUX_TARGET_PORT", "8001"))

DASH_TARGET_HOST = os.environ.get("DASH_MUX_TARGET_HOST", "127.0.0.1")
DASH_TARGET_PORT = int(os.environ.get("DASH_MUX_TARGET_PORT", "3000"))

TLS_HANDSHAKE_BYTE = 0x16
XRAY_PATHS = ("/vless-mediafairy", "/vmess-mediafairy", "/trojan-mediafairy")
HTTP_METHODS = ("get ", "post ", "put ", "head ", "patch ", "options ", "delete ")
DASH_PATHS = ("/", "/login", "/admin", "/sub.txt", "/style.css")

logging.basicConfig(
    level=logging.INFO,
    format="[mux] %(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("mux")


async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter):
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    except Exception as e:
        log.debug("pipe error: %s", e)
    finally:
        try:
            dst.close()
        except Exception:
            pass


def is_dashboard_path(text):
    m = re.match(r"[a-z]+ (/[^ ]*)", text)
    if not m:
        return False
    p = m.group(1)
    return p in DASH_PATHS or p.startswith("/api/")


def classify(data: bytes):
    if not data:
        return None
    if data[0] == TLS_HANDSHAKE_BYTE:
        return (SSL_TARGET_HOST, SSL_TARGET_PORT, "SSL/stunnel")

    text = data.decode(errors="ignore").lower()
    is_http = text.startswith(HTTP_METHODS)
    is_ws = "upgrade: websocket" in text

    if is_http:
        if is_ws:
            if any(p in text for p in XRAY_PATHS):
                return (XRAY_TARGET_HOST, XRAY_TARGET_PORT, "Xray/WS")
            return (WS_TARGET_HOST, WS_TARGET_PORT, "ws-ssh")
        if is_dashboard_path(text):
            return (DASH_TARGET_HOST, DASH_TARGET_PORT, "dashboard")
        return (WS_TARGET_HOST, WS_TARGET_PORT, "ws-ssh")

    return (WS_TARGET_HOST, WS_TARGET_PORT, "ws-ssh")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    try:
        data = await reader.read(4096)
        if not data:
            writer.close()
            return

        target = classify(data)
        if target is None:
            writer.close()
            return
        host, port, label = target

        log.info("Koneksi %s dikenali sebagai %s -> %s:%s", peer, label, host, port)

        try:
            target_reader, target_writer = await asyncio.open_connection(host, port)
        except Exception as e:
            log.error("Gagal konek ke backend %s:%s : %s", host, port, e)
            writer.close()
            return

        # Kirim data yang sudah kita intip, lalu relay dua arah
        target_writer.write(data)
        await target_writer.drain()

        await asyncio.gather(
            pipe(reader, target_writer),
            pipe(target_reader, writer),
        )
    except Exception as e:
        log.error("Error menangani klien %s: %s", peer, e)
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    log.info(
        "Mux jalan di %s:%s -> SSL:%s:%s | WS:%s:%s | Xray:%s:%s | Dash:%s:%s",
        LISTEN_HOST, LISTEN_PORT,
        SSL_TARGET_HOST, SSL_TARGET_PORT,
        WS_TARGET_HOST, WS_TARGET_PORT,
        XRAY_TARGET_HOST, XRAY_TARGET_PORT,
        DASH_TARGET_HOST, DASH_TARGET_PORT,
    )
    async with server:
        await server.serve_forever()


def handle_sigterm(*_):
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass