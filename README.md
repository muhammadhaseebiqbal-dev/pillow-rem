# 🖼️ Background Removal API

A high-performance FastAPI backend that removes backgrounds from images using AI with ~99% accuracy. Optimized for concurrent processing.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **AI Background Removal** | Uses U2-Net deep learning model via `rembg` |
| **PDF Generation** | Export images to PDF (simple, masonry, bento layouts) |
| **Concurrent Processing** | ProcessPoolExecutor for parallel image processing |
| **Local Database** | SQLite with SQLAlchemy for metadata storage |
| **Production Ready** | Gunicorn + Docker + Nginx configurations |
| **Modern UI** | Drag-and-drop web interface for testing |

## 🚀 Quick Start

### Local Development (Windows)
```bash
cd d:\WORK\pillow

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run server
python run.py
```

### Production (Linux - see DEPLOYMENT.md for full guide)
```bash
# Option 1: Docker
docker compose up -d --build

# Option 2: Direct
gunicorn app.main:app -c run_production.py
```

Open `http://127.0.0.1:8000` in your browser.

## 📡 API Endpoints

### Image Processing
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/remove-background` | Upload & remove background |
| `GET` | `/api/images` | List all images |
| `GET` | `/api/images/{id}/original` | Get original image |
| `GET` | `/api/images/{id}/processed` | Get processed image |
| `DELETE` | `/api/images/{id}` | Delete image |

### PDF Generation
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/pdf/originals` | PDF of all original images |
| `GET` | `/api/pdf/processed?layout=masonry` | PDF of processed images (layouts: masonry, bento, simple) |
| `GET` | `/api/pdf/all` | Combined PDF with all images |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/stats` | Storage statistics |

## 📁 Project Structure

```
pillow/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app (optimized)
│   ├── database.py          # SQLite config
│   ├── background_remover.py # AI processing
│   └── pdf_generator.py     # PDF layouts
├── static/
│   └── index.html           # Web UI
├── data/                    # Auto-created
│   ├── images.db            # Database
│   ├── uploads/             # Originals
│   ├── processed/           # BG removed
│   └── pdfs/                # Generated PDFs
├── requirements.txt
├── run.py                   # Dev server
├── run_production.py        # Production config
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── DEPLOYMENT.md            # Linux hosting guide
└── README.md
```

## ⚙️ Performance Optimization

Optimized for **4 vCPU, 16GB RAM**:

- **4 Gunicorn workers** (1 per vCPU)
- **ProcessPoolExecutor** for CPU-bound tasks
- **ThreadPoolExecutor** for I/O operations
- **Nginx** for rate limiting & caching
- **Docker** resource limits

## 🐧 Linux Deployment

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for complete guide including:
- Docker deployment
- Systemd service setup
- Nginx reverse proxy
- SSL/HTTPS with Let's Encrypt
- System tuning

## 📝 Example Usage

### Upload Image (curl)
```bash
curl -X POST "http://localhost:8000/api/remove-background" \
  -F "file=@photo.jpg" \
  -o response.json
```

### Download PDF (curl)
```bash
# Processed images in masonry layout
curl "http://localhost:8000/api/pdf/processed?layout=masonry" -o gallery.pdf

# Processed images in bento layout
curl "http://localhost:8000/api/pdf/processed?layout=bento" -o gallery_bento.pdf
```

### Python Client
```python
import requests

# Upload image
with open("photo.jpg", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/remove-background",
        files={"file": f}
    )
result = response.json()
print(result["data"]["processed_url"])

# Download processed image
img = requests.get(f"http://localhost:8000{result['data']['processed_url']}")
with open("processed.png", "wb") as f:
    f.write(img.content)
```

## 📋 Notes

- First run downloads U2-Net model (~170MB)
- Supported formats: PNG, JPG, JPEG, WebP
- Processed images saved as PNG with transparency
- PDF generation supports up to thousands of images

 Made with 💖 by queue agent