# GatewayLite — Dropbear SSH + Xray (VLESS/VMESS/Trojan) dalam 1 Container Ringan

Penggabungan dari:
- [Ddfathu/Dropbear](https://github.com/Ddfathu/Dropbear) — SSH via Dropbear + Stunnel + WS + Argo
- [Tamiraa9909/argo-hybrid](https://github.com/Tamiraa9909/argo-hybrid) — Xray Gateway + Dashboard

**Bedanya:** base OS diganti **Alpine Linux** (jauh lebih ringan), **Node.js dihilangkan**
(dashboard & multiplexer ditulis ulang dalam Python murni), binary Xray/cloudflared diunduh
**multi-source dengan auto-fallback**, dan satu env `TOKEN` menggantikan `ARGO_AUTH`/`CF_TUNNEL_TOKEN`
(termasuk dukungan **banyak token** dipisah koma).

## Arsitektur (SATU port publik)

```
                     Railway TCP Proxy / HTTP domain :$PORT
                                    |
                         mux.py (Python asyncio)
   sniff byte pertama + HTTP path:
    0x16 (TLS) ............. -> stunnel :2443 --> Dropbear :22   (SSH-SSL)
    WS /vless-mediafairy    -> Xray :8001   (VLESS WS)
    WS /vmess-mediafairy    -> Xray :8001   (VMESS WS)
    WS /trojan-mediafairy   -> Xray :8001   (TROJAN WS)
    HTTP / , /api/* , /sub.txt -> dashboard :3000 (Python)
    HTTP-WS lainnya / biner -> ws-proxy :8880 --> Dropbear :22  (SSH-WS)
                                    |
          cloudflared (banyak TOKEN atau quick-tunnel) --> localhost:$PORT
```

Semua layanan internal (`22/2443/8880/8001/3000`) **tidak diekspos keluar** — hanya mux
yang terbuka, sehingga aman.

## Environment Variables

| Variable | Default | Wajib | Keterangan |
|---|---|---|---|
| `UUID` | — | **Ya** | UUID klien VPN (VLESS/VMESS/Trojan) |
| `ADMIN_USER` | — | Admin panel | Username login Admin Panel. **Harus di-set** agar `/admin` aktif |
| `ADMIN_PASSWORD` | — | Admin panel | Password login Admin Panel. **Harus di-set** agar `/admin` aktif |
| `TOKEN` | kosong | Opsional | Token Cloudflare Tunnel. **Boleh banyak, dipisah koma** (`t1,t2,t3`). Kosongkan untuk auto quick-tunnel |
| `PORT` | 8080 | — | Port publik (Railway meng-inject otomatis) |
| `SSH_USER` | `jatim` | — | User SSH utama |
| `SSH_PASSWORD` | `jatim` | — | Password SSH utama |
| `NAME` | `GATEWAY-LITE` | — | Alias pada nama config yang di-generate |
| `CFIP` | `saas.sin.fan` | — | Bug IP CDN / SNI |
| `CFPORT` | `443` | — | Port CDN |
| `ARGO_DOMAIN` | kosong | — | Custom domain jika pakai `TOKEN` |
| `QUICK_TUNNEL` | `1` | — | Aktifkan quick-tunnel trycloudflare jika `TOKEN` kosong |

## Admin Panel

Panel admin di **`/admin`** (wajib login dengan `ADMIN_USER`/`ADMIN_PASSWORD`).
Tanpa kedua env itu di-set, admin panel **nonaktif** (halaman `/login` & `/admin` 404).

Fitur admin:
- **Settings** — ubah runtime: `UUID`, `NAME`, `CFIP`, `CFPORT`, `ARGO_DOMAIN`,
  `TOKEN` (multi-token), `SSH_USER`, `SSH_PASSWORD`, `QUICK_TUNNEL`,
  **banner Dropbear** (pesan sebelum login), dan **response setelah login**.
- Perubahan **langsung diterapkan live**: TOKEN → cloudflared di-restart,
  UUID → Xray di-restart, banner/SSH user → ditulis ulang, tanpa redeploy.
- **Tunnels** — status & restart cloudflared, daftar domain trycloudflare.
- **SSH Users** — daftar/hapus akun SSH.
- **Logs** — log tunnel.

Persistensi: perubahan disimpan ke `settings.json` (bertahan selama instance hidup).
Railway **redeploy** mengembalikan ke nilai env.

## Mode User (Publik)

Halaman utama `/` terbuka untuk semua:
- **Generate node** — VLESS/TROJAN (Bug SNI) + VLESS/VMESS/TROJAN (Bug CDN), copy ke clipboard.
- **Create SSH** — username + password + expired (hari), langsung jadi.
- **Subscription** — `/sub.txt` berisi semua link argo yang ter-generate.
- **Telemetry** — CPU/RAM/Download/Upload + grafik traffic 60 detik.

## Deployment di Railway

1. **Fork** repo ini ke GitHub kamu.
2. Buka [Railway](https://railway.app) → **New Project** → **Deploy from GitHub repo** → pilih fork ini → **Deploy Now**.
3. Tambahkan env `UUID` (wajib) dan opsional lainnya (`TOKEN`, `SSH_USER`, dll).
4. Railway otomatis mendeteksi `PORT` → **HTTP domain otomatis aktif tanpa setup manual**
   → buka domain `.up.railway.app` untuk Dashboard.

### Port mana yang otomatis vs manual?

| Jalur | Setup manual |
|---|---|
| Dashboard `/`, `/api/*`, `/sub.txt` | **Otomatis** (via domain HTTP Railway) |
| VLESS/VMESS/Trojan via WS (Argo / domain) | **Otomatis** |
| SSH-WS | **Otomatis** |
| SSH-SSL (stunnel TLS) | **1 TCP Proxy manual** (opsional, karena Railway tidak bisa membuka port TCP otomatis dari dalam container) |

Untuk SSH-SSL: Settings → Networking → **TCP Proxy** → arahkan ke port yang sama dengan `PORT`.

### Cloudflare Tunnel (optional)

1. Cloudflare Zero Trust → **Networks → Tunnels → Create a tunnel (Cloudflared)** → salin token.
2. Isi env `TOKEN` di Railway (boleh `t1,t2,t3` untuk banyak tunnel).
3. Di tab **Public Hostname** tambahkan service:
   - Service type **HTTP**, URL `http://localhost:8080` (atau sesuai `PORT`).
4. Tanpa `TOKEN`, container otomatis membuat **quick tunnel** (`trycloudflare.com`)
   dan domain-nya otomatis di-detect Dashboard → semua link tergenerate di `/api/config` & `/sub.txt`.

### Networking Cloudflare agar WS jalan
- Network → **WebSockets**: ON
- Security → Bots → **Bot Fight Mode**: OFF
- Security → WAF → Settings → **Browser Integrity Check**: OFF

## Manajemen Akun SSH

Login SSH (via WS/SSL), lalu jalankan:

```bash
menu        # menu interaktif
addssh user pass            # buat akun
addssh user pass 30         # buat akun + expired 30 hari
listssh                     # daftar akun
delssh user                 # hapus akun
```

## Kenapa lebih ringan?

- Base **Alpine Linux** (~5MB) menggantikan Ubuntu 22.04.
- **Tanpa Node.js**: dashboard + mux 100% Python (std library only, tidak ada dependency).
- Binary Xray/cloudflared diunduh saat *runtime* dengan **multi-source** (official GitHub
  → mirror `ssss.nyc.mn`) dan auto-fallback, image jadi kecil & multi-arch (amd64/arm64).
- Semua statistik dibaca langsung dari `/proc` (tanpa library).

## Struktur File

```
Dockerfile            Alpine base, minimal
entrypoint.sh         Orchestrate semua layanan
mux.py                Unified mux: TLS/WS/Xray/dashboard
ws-proxy.py           WebSocket <-> SSH proxy
dashboard.py          Dashboard + Admin Panel + pengelola tunnel/Xray
settings.py           Penyimpanan settings + apply runtime
gen-xray-config.py    Generate config.json Xray
download-bin.py       Multi-source download + auto-fallback
web/style.css         Design system monochrome (Vercel x Meta)
web/public.html       UI user: generate node + create SSH
web/login.html        Login admin
web/admin.html        Admin panel
addssh delssh listssh menu   Manajemen akun SSH (versi Alpine)
```