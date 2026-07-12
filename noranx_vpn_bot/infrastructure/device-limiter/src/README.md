# 🛡️ Marzban Device Limiter

> Lightweight proxy server for Marzban to enforce strict device limits per subscription.  
> Stop account sharing. Protect your VPN business from revenue loss.

[![Go Version](https://img.shields.io/badge/go-1.22-blue)](https://go.dev)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## ✨ Features

- **🚀 Zero-CGO & Pure Go**: Compiled binary is only ~15MB
- **💾 Resource-Efficient**: Minimal RAM usage (~20MB). Perfect for cheap 1GB VPS
- **🔒 Smart Tracking**: Identifies devices via `X-HWID` header (priority) or SHA256 fingerprint (`User-Agent` + Token)
- **📊 Autonomous**: Uses embedded SQLite — no external dependencies
- **🔄 Transparent Proxy**: Seamlessly forwards requests to Marzban
- **🛡️ Fail-Safe**: If limiter fails, traffic passes through (configurable)
- **📡 Management API**: REST API for device management and limit configuration

---

## 🚀 Quick Start

### Step 1: Clone and Configure

```bash
git clone https://github.com/kets-kets/marzban-device-limiter.git
cd marzban-device-limiter
cp .env.example .env
```

Edit `.env` and set your Marzban URL:
```bash
# .env
MARZBAN_URL=http://127.0.0.1:8000  # Change to your Marzban instance
PORT=3000
```

### Step 2: Start the Service

```bash
docker compose up -d --build
```

### Step 3: Update Nginx Configuration

Edit your Nginx config on the Marzban server to route `/sub/` requests through the limiter:

```nginx
location /sub/ {
    proxy_pass http://127.0.0.1:3000;  # Route to limiter (not Marzban!)
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header User-Agent $http_user_agent;  # Critical for fingerprinting
}
```

Reload Nginx:
```bash
sudo systemctl reload nginx
```

**Done!** The limiter is now active. Test it by accessing a subscription from 4 different devices.

---

## 🧪 How to Verify It Works

After deployment, try updating the subscription from 4 different devices.  
The 4th device should receive `403 Forbidden`.

| Request       | Result                  |
|---------------|-------------------------|
| Device 1-3    | ✅ Allowed (200 OK)     |
| Device 4      | ❌ Blocked (403)        |

**Test Script** (from your local machine):
```bash
TOKEN="your_subscription_token"
URL="https://your-domain.com/sub/$TOKEN"

for i in 1 2 3 4; do
    echo "Request $i:"
    curl -H "X-HWID: device_$i" -I "$URL"
done
```

---

## 📡 Management API

### Get Devices for User
```bash
GET /api/devices?username=12345_device1

Response:
[
  {
    "id": 1,
    "username": "12345_device1",
    "hwid": "abc123",
    "user_agent": "V2RayTun/1.0",
    "fingerprint": "fp_a1b2c3d4",
    "last_seen": "2026-02-08T12:00:00Z"
  }
]
```

### Delete Device
```bash
DELETE /api/device/delete?username=12345_device1&id=1
```

### Set Custom Limit
```bash
PUT /api/limit
Content-Type: application/json

{
  "username": "12345_device1",
  "device_limit": 5,
  "hwid_enabled": true
}
```

---

## 🛠️ Safe Deployment for Low-RAM Servers (1GB VPS)

If your server crashes during `docker build` (OOM error), use this strategy:

### 1. Build Locally
```bash
# On your dev machine
docker build -f Dockerfile.release -t marzban-limiter:release .
docker save marzban-limiter:release | gzip > limiter.tar.gz
```

### 2. Upload to Server
```bash
scp limiter.tar.gz user@your-server:/root/
```

### 3. Load and Run
```bash
# On server
docker load < limiter.tar.gz
docker compose -f docker-compose.release.yml up -d
```

---

## 🔧 Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MARZBAN_URL` | `http://127.0.0.1:8000` | Marzban instance URL |
| `PORT` | `3000` | Limiter listening port |
| `DATA_DIR` | `/data` | SQLite database directory |

---

## 📂 Project Structure

```
marzban-device-limiter/
├── cmd/device-limit/       # Main entry point
├── internal/
│   ├── api/                # Management API
│   ├── config/             # Configuration loader
│   ├── db/                 # SQLite operations
│   ├── model/              # Data structures
│   └── proxy/              # Proxy middleware & fingerprinting
├── Dockerfile              # Multi-stage build
├── Dockerfile.release      # Lightweight (binary-only)
└── docker-compose.yml      # Quick start example
```

---

## 🔒 How It Works

1. **Client** requests subscription: `GET /sub/TOKEN`
2. **Nginx** forwards to limiter (port 3000)
3. **Limiter** extracts username from JWT token
4. **Fingerprinting**:
   - Priority: `X-HWID` header (if present)
   - Fallback: `SHA256(User-Agent + Token)`
5. **Check Limit**: Query SQLite for device count
6. **Decision**:
   - Count ≤ 3: Forward to Marzban
   - Count > 3: Return `403 Forbidden`

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

This tool is designed for **legitimate VPN service providers** to enforce their terms of service. Use responsibly and in compliance with local laws.

---

<div align="center">

**Built with ❤️ using Go 1.22**

[Report Bug](https://github.com/kets-kets/marzban-device-limiter/issues) · [Request Feature](https://github.com/kets-kets/marzban-device-limiter/issues)

</div>
