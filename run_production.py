"""
Production entry point with optimized settings.
Configured for 4 vCPU, 16GB RAM server.
"""
import multiprocessing
import os

# Production configuration
workers = 4  # Match vCPU count
worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:8000"
timeout = 300  # 5 minutes for long image processing
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
graceful_timeout = 30
preload_app = True

# Memory optimization
worker_tmp_dir = "/dev/shm"  # Use shared memory for worker temp files

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

if __name__ == "__main__":
    import uvicorn
    
    # For direct Python execution (development/testing)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        workers=workers,
        timeout_keep_alive=keepalive,
        access_log=True
    )
