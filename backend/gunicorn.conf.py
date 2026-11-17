"""Gunicorn config for the Ubuntu VPS (see docs/DEPLOYMENT.md).

Workers are kept low so the API fits comfortably alongside PostgreSQL and Redis on an
8 GB machine. The WebSocket endpoint is served by the Uvicorn worker class.
"""

import multiprocessing
import os

bind = os.getenv("TRADEMIND_BIND", "127.0.0.1:8000")  # only Nginx should reach the app
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("TRADEMIND_WORKERS", min(2, multiprocessing.cpu_count())))
timeout = 120
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("TRADEMIND_LOG_LEVEL", "info")
forwarded_allow_ips = "127.0.0.1"
# Not needed in production, and the systemd sandbox makes $HOME read-only.
control_socket_disable = True
