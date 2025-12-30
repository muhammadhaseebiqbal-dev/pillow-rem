# 🚀 Linux Server Deployment Guide

Complete guide to deploy the Background Removal API on your Linux server (4 vCPU, 16GB RAM).

## Option 1: Docker Deployment (Recommended)

### Prerequisites
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### Deploy
```bash
# Clone/upload your project
cd /opt
git clone <your-repo> background-remover
# OR upload via SCP:
# scp -r ./pillow user@server:/opt/background-remover

cd background-remover

# Build and run
docker compose up -d --build

# Check logs
docker compose logs -f

# Check status
docker compose ps
```

### Access
- API: `http://your-server-ip:8000`
- With Nginx: `http://your-server-ip`

---

## Option 2: Direct Python Installation

### Prerequisites
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+ and dependencies
sudo apt install python3.11 python3.11-venv python3-pip -y
sudo apt install libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev -y
```

### Setup
```bash
# Create app directory
sudo mkdir -p /opt/background-remover
sudo chown $USER:$USER /opt/background-remover
cd /opt/background-remover

# Upload your code (via git clone or scp)

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create data directories
mkdir -p data/uploads data/processed data/pdfs
```

### Run with Gunicorn (Production)
```bash
# Test run
gunicorn app.main:app -c run_production.py

# Run in background with nohup
nohup gunicorn app.main:app -c run_production.py > logs/gunicorn.log 2>&1 &
```

---

## Option 3: Systemd Service (Best for Production)

### Create Service File
```bash
sudo nano /etc/systemd/system/background-remover.service
```

Paste this content:
```ini
[Unit]
Description=Background Remover API
After=network.target

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=/opt/background-remover
Environment="PATH=/opt/background-remover/venv/bin"
ExecStart=/opt/background-remover/venv/bin/gunicorn app.main:app -c run_production.py
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=5

# Security
NoNewPrivileges=true
PrivateTmp=true

# Resource limits (adjust based on your needs)
LimitNOFILE=65535
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
```

### Enable and Start
```bash
# Set permissions
sudo chown -R www-data:www-data /opt/background-remover

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable background-remover

# Start the service
sudo systemctl start background-remover

# Check status
sudo systemctl status background-remover

# View logs
sudo journalctl -u background-remover -f
```

---

## Nginx Reverse Proxy Setup

```bash
# Install nginx
sudo apt install nginx -y

# Create site config
sudo nano /etc/nginx/sites-available/background-remover
```

Paste:
```nginx
upstream fastapi {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name your-domain.com;  # Or use _ for any
    client_max_body_size 50M;

    location / {
        proxy_pass http://fastapi;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/background-remover /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## SSL with Let's Encrypt

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is set up automatically
sudo certbot renew --dry-run
```

---

## Performance Tuning for 4 vCPU, 16GB RAM

### System Tuning
```bash
# Add to /etc/sysctl.conf
sudo nano /etc/sysctl.conf
```

Add:
```
# Network optimization
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.ip_local_port_range = 1024 65535

# File descriptors
fs.file-max = 2097152
fs.nr_open = 2097152
```

Apply:
```bash
sudo sysctl -p
```

### User Limits
```bash
sudo nano /etc/security/limits.conf
```

Add:
```
* soft nofile 65535
* hard nofile 65535
* soft nproc 65535
* hard nproc 65535
```

---

## API Endpoints Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Test UI page |
| `/api/remove-background` | POST | Upload & process image |
| `/api/images` | GET | List all images |
| `/api/images/{id}/original` | GET | Get original image |
| `/api/images/{id}/processed` | GET | Get processed image |
| `/api/images/{id}` | DELETE | Delete image |
| `/api/pdf/originals` | GET | PDF of all originals |
| `/api/pdf/processed?layout=masonry` | GET | PDF of processed (masonry/bento/simple) |
| `/api/pdf/all` | GET | Combined PDF |
| `/health` | GET | Health check |
| `/api/stats` | GET | System stats |

---

## Monitoring

### Check resource usage
```bash
htop
docker stats  # If using Docker
```

### View logs
```bash
# Systemd
sudo journalctl -u background-remover -f

# Docker
docker compose logs -f
```

### Disk usage
```bash
du -sh /opt/background-remover/data/*
```

---

## Backup

```bash
# Backup data
tar -czvf backup-$(date +%Y%m%d).tar.gz /opt/background-remover/data

# Restore
tar -xzvf backup-YYYYMMDD.tar.gz -C /
```
