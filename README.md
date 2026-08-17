# GatewayLite — Dropbear SSH + Xray dalam 1 Container Ringan

Satu container **Alpine Linux** yang menyediakan:

- **SSH server (Dropbear)** — bisa diakses lewat **SSL (TLS)** dan **WebSocket (WS)**
- **Xray** — node VPN **VLESS / VMESS / Trojan** (via WebSocket)
- **Admin Panel** — buat akun SSH, generate node VPN, atur tunnel, tanpa login ke server

Hasil akhirnya kamu punya **2 domain SSH** (pola dari [vmesssh](https://github.com/Ddfathu/vmesssh)):

| Domain | Fungsi |
|---|---|
| Domain **Railway** (TCP proxy) | SSH via **SSL** (`SSH over TLS`) |
| Domain **Cloudflare Tunnel** (argo) | SSH via **WebSocket** |

---

## Arsitektur (SATU port publik)

```
        Railway HTTP domain :$PORT        Railway TCP proxy :$PORT
                     |                          |
                     +------------+-------------+
                                  |
                       mux.py (Python asyncio)
      intip byte pertama + path HTTP:
       0x16 (TLS) ................ -> stunnel :2443 --> Dropbear :22   (SSH-SSL)
       WS /vless-mediafairy ...... -> Xray :8001   (VLESS WS)
       WS /vmess-mediafairy ...... -> Xray :8001   (VMESS WS)
       WS /trojan-mediafairy ..... -> Xray :8001   (TROJAN WS)
       HTTP / , /api/* , /sub.txt -> dashboard :3000 (Python)
       HTTP-WS lain / biner ...... -> ws-proxy :8880 --> Dropbear :22 (SSH-WS)
                                  |
        cloudflared (TOKEN) --> localhost:$PORT   <-- domain Cloudflare Tunnel
```

Semua layanan internal (`22/2443/8880/8001/3000`) **tidak diekspos ke luar** — hanya mux yang terbuka, jadi aman.

---

## Cara Deploy di Railway (langkah demi langkah)

### 1. Fork repo

1. Buka [github.com/fayozegoist/gateway-lite](https://github.com/fayozegoist/gateway-lite)
2. Klik **Fork** (kanan atas) → pilih akun kamu → **Create fork**

### 2. Deploy ke Railway

1. Buka [railway.app](https://railway.app) → login (bisa pakai akun GitHub)
2. Klik **New Project** → **Deploy from GitHub repo**
3. Pilih hasil fork kamu → **Deploy Now**
4. Tunggu build selesai (2–3 menit). Railway otomatis mendeteksi port → **HTTP domain aktif otomatis**
5. Buka **Settings → Networking** untuk melihat domain, contoh: `nama-service-production.up.railway.app`

### 3. Set Environment Variables

Di **Variables** (tab service), tambahkan minimal ini:

| Variable | Contoh | Wajib? |
|---|---|---|
| `UUID` | `8c78114c-d737-47ee-a812-93583aea16e6` | **Ya** |
| `ADMIN_USER` | `admin` | Ya (agar panel admin aktif) |
| `ADMIN_PASSWORD` | `rahasia123` | Ya |
| `TOKEN` | token Cloudflare tunnel | Opsional (untuk SSH-WS via Cloudflare) |
| `ARGO_DOMAIN` | `argo.domainkamu.com` | Opsional |

> `UUID` bisa di-generate di [uuidgenerator.net](https://www.uuidgenerator.net).

### 4. (Opsional) Aktifkan SSH-SSL via TCP Proxy

Railway tidak bisa membuka port TCP otomatis dari dalam container, jadi untuk SSH-SSL perlu **TCP Proxy**:

- Buka **Settings → Networking → TCP Proxy → Create TCP Proxy**
- Arahkan ke **App Port = 8080** (sama dengan `$PORT`)
- Catat endpoint-nya, contoh: `nama.proxy.rlwy.net:31111`

---

## Setup Cloudflare Tunnel (untuk domain SSH-WS)

> Tanpa langkah ini, **SSH-SSL (Railway) & SSH-WS (Railway) sudah bisa dipakai**.
> Ini tambahan supaya kamu punya **domain Cloudflare untuk SSH via WebSocket**.

### 1. Buat Tunnel di Zero Trust

1. Buka [dash.cloudflare.com](https://dash.cloudflare.com) → masuk ke akun
2. Kiri bawah: **Zero Trust** → **Networks → Tunnels**
3. Klik **Create a tunnel** → pilih **Cloudflared** → **Next**
4. Beri nama tunnel (misal `gateway`) → **Save tunnel**
5. Halaman **Install and run a connector** → pilih OS apa saja → salin **token** (bagian yang panjang, mulai `eyJh...`)
6. **Skip** langkah "run the connector" (kita jalankan otomatis di container)

### 2. Isi token di Railway

1. Di Railway, buka **Variables**
2. Tambahkan `TOKEN` = token dari langkah di atas (tempel tanpa spasi)
3. Tambahkan `ARGO_DOMAIN` = subdomain yang ingin dipakai, misal `argo.domainkamu.com`
4. Deploy ulang / restart service. Cloudflared otomatis jalan di dalam container.

### 3. Tambahkan Public Hostname

1. Kembali ke **Zero Trust → Networks → Tunnels** → klik tunnel kamu
2. Tab **Public Hostname** → **Add a public hostname**
3. Isi:
   - **Subdomain**: `argo`
   - **Domain**: `domainkamu.com`
   - **Service type**: `HTTP`
   - **URL**: **`http://localhost:8080`**
4. **Save hostname**

> **⚠️ PENTING:** URL harus **`http://localhost:8080`** (port **mux**), **bukan** `8001` (Xray).
> Mux yang memecah lalu lintas: WS path Xray → Xray, WS lain → SSH. Kalau diarahkan ke `8001`,
> SSH-WS akan gagal (502) karena Xray tidak mengerti koneksi SSH.

### 4. Aktifkan WebSocket di Cloudflare

Agar SSH-WS lancar, pastikan pengaturan domain ini ON/OFF:

1. **Websites → pilih domain → Network → WebSockets: ON**
2. **Security → Bots → Bot Fight Mode: OFF**
3. **Security → WAF → Settings → Browser Integrity Check: OFF**

---

## Panduan Koneksi SSH (untuk user)

### SSH-SSL (domain Railway / TCP proxy)

Klien SSH dengan mode **SSL/TLS** (misal HTTP Custom, KPN Tunnel, atau stunnel client):

- **Host**: endpoint TCP proxy kamu, contoh `nama.proxy.rlwy.net`
- **Port**: `31111` (port TCP proxy)
- **Mode**: SSL / TLS
- **Username / Password**: akun SSH yang dibuat di panel

### SSH-WebSocket (domain Cloudflare)

Klien SSH dengan mode **WebSocket**:

- **Host**: domain Cloudflare kamu, contoh `argo.domainkamu.com`
- **Port**: `443`
- **Mode**: WebSocket
- **Username / Password**: akun SSH yang dibuat di panel

> SSH-WS juga bisa lewat domain Railway (`nama-service-production.up.railway.app:443`)
> untuk jalur cadangan.

### SSH-WebSocket (domain Railway, cadangan)

- **Host**: `nama-service-production.up.railway.app`
- **Port**: `443`
- **Mode**: WebSocket

---

## Admin Panel

Panel admin di **`/admin`** pada domain Railway, contoh: `https://nama-service-production.up.railway.app/admin`

Login pakai `ADMIN_USER` / `ADMIN_PASSWORD`.

Fitur:
- **Settings** — ubah `UUID`, `TOKEN`, `ARGO_DOMAIN`, `SSH_USER`, `SSH_PASSWORD`, banner, dll. **Langsung berlaku tanpa redeploy.**

> **Catatan banner Dropbear:** maksimal **2050 byte** (batas internal dropbear). Banner yang
> lebih besar dari itu **tidak ditampilkan** (dropbear hanya menulis warning). Saat mengedit
> banner di Admin Panel, pastikan ukurannya tetap di bawah 2050 byte.
- **Tunnels** — status cloudflared, restart, daftar domain.
- **SSH Users** — lihat/hapus akun SSH.
- **Logs** — log tunnel.

### Halaman publik `/`

Terbuka untuk semua:
- **Generate node** — VLESS / VMESS / Trojan (bug SNI / bug CDN), tinggal copy ke aplikasi.
- **Create SSH** — buat akun SSH + masa aktif (hari).
- **Subscription** — semua link di `/sub.txt`.

---

## Manajemen Akun SSH

Login SSH (via WS/SSL), lalu jalankan:

```bash
menu          # menu interaktif
addssh user pass          # buat akun
addssh user pass 30       # buat akun + expired 30 hari
listssh                   # daftar akun
delssh user               # hapus akun
```

---

## Environment Variables (lengkap)

| Variable | Default | Keterangan |
|---|---|---|
| `UUID` | — | UUID klien VPN (VLESS/VMESS/Trojan). **Wajib.** |
| `ADMIN_USER` | — | Username admin panel. Wajib agar `/admin` aktif |
| `ADMIN_PASSWORD` | — | Password admin panel. Wajib agar `/admin` aktif |
| `TOKEN` | kosong | Token Cloudflare Tunnel. Boleh banyak dipisah koma (`t1,t2`). Kosongkan untuk quick tunnel |
| `ARGO_DOMAIN` | kosong | Custom domain jika pakai `TOKEN` |
| `PORT` | 8080 | Port publik (Railway inject otomatis) |
| `SSH_USER` | `hidup` | User SSH utama |
| `SSH_PASSWORD` | `jokowi` | Password SSH utama |
| `NAME` | `GATEWAY-LITE` | Alias nama config yang di-generate |
| `CFIP` | `saas.sin.fan` | IP CDN / SNI untuk node bug |
| `CFPORT` | `443` | Port CDN |
| `QUICK_TUNNEL` | `1` | Quick tunnel trycloudflare jika `TOKEN` kosong |
| `SSL_HOST` | kosong | Host endpoint **SSH-SSL** (domain Railway TCP proxy, misal `nama.proxy.rlwy.net`). Jika kosong, pakai domain yang mengakses panel |
| `SSL_PORT` | `443` | Port endpoint **SSH-SSL** (port TCP proxy, misal `31111`). Jika kosong, default `443` |

---

## Kenapa lebih ringan?

- Base **Alpine Linux** (~5MB) menggantikan Ubuntu.
- **Tanpa Node.js** — dashboard & mux 100% Python (stdlib, tanpa dependency).
- Binary Xray/cloudflared diunduh saat runtime, **multi-source + auto-fallback** → image kecil & multi-arch (amd64/arm64).
- Semua statistik dibaca langsung dari `/proc`.

---

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
web/style.css         Design system monochrome
web/public.html       UI user: generate node + create SSH
web/login.html        Login admin
web/admin.html        Admin panel
addssh delssh listssh menu   Manajemen akun SSH (versi Alpine)
```