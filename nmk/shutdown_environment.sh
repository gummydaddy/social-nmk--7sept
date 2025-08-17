#!/bin/bash

echo "Shutting down environment..."

# Kill common process names
sudo pkill -f gunicorn
sudo pkill -f celery
sudo pkill -f 'celery worker'
sudo pkill -f setup_environment.sh
sudo pkill -f python3
sudo pkill -f uvicorn
sudo pkill -f socyfie_application
sudo pkill -f asgi
sudo pkill -f redis

# Kill Celery worker by PID file (if it exists)
if [ -f /tmp/celery_worker.pid ]; then
    kill -9 $(cat /tmp/celery_worker.pid)
    echo "Killed celery worker from PID file."
else
    echo "PID file /tmp/celery_worker.pid not found."
fi

echo "Shutdown complete."
