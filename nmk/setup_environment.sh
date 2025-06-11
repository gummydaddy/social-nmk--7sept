#!/bin/bash
# Exit on error
set -e

# Define the virtual environment path
VENV_PATH="/home/ubuntu/social-nmk--7sept/venv"

# Define the path to your requirements.txt file
REQUIREMENTS_FILE="/home/ubuntu/social-nmk--7sept/nmk/requirements.txt"

# Create the virtual environment if it doesn't exist
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment at $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
fi

# Activate the virtual environment
source "$VENV_PATH/bin/activate"

# Upgrade pip and six in the virtual environment
pip install --upgrade pip
pip install --upgrade six

# Install the packages from requirements.txt
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install -r "$REQUIREMENTS_FILE"
else
    echo "requirements.txt not found at $REQUIREMENTS_FILE."
    exit 1
fi

# Export environment variables
export DJANGO_SETTINGS_MODULE="socyfie_application.settings"
export DEBUG=False
#export DEBUG=True
export DATABASE_URL="testadmin://postgres:090399Akash$@15.235.192.133:5432/socyfiedev"
export REDIS_URL="redis://:090399Akash%24@15.235.192.133:6379/0"

#export DATABASE_URL="postgres://postgres:090399Akash$@13.235.125.150:5432/socyfiedev"
#export REDIS_URL="redis://:090399Akash$@13.235.125.150:6379/0"  # Example Redis URL if you use Redis

export CELERY_BROKER_URL="$REDIS_URL"

# (Optional) Adjust PYTHONPATH if needed for additional modules
export PYTHONPATH="$VENV_PATH/lib/$(python -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')/site-packages/"

echo "Packages installed successfully in virtual environment at ${VENV_PATH}"
echo "PYTHONPATH set to: $PYTHONPATH"

# Run Django's SSL server in the background
#python3 manage.py runserver 0.0.0.0:8000 &

gunicorn socyfie_application.asgi:application -k uvicorn.workers.UvicornWorker --bind 127.0.0.1:8000 &

#gunicorn socyfie_application.asgi:application -k uvicorn.workers.UvicornWorker --bind 127.0.0.1:8000 &


# Start Celery worker and beat services in the background
echo "Starting Celery worker and beat services..."
#celery -A socyfie_application worker --loglevel=info -n worker1@%h &

#celery -A socyfie_application worker --pool=gevent --autoscale=100,10 --loglevel=info -E --pidfile=/tmp/celery_worker.pid -n worker1@%h &

#celery -A socyfie_application worker --pool=prefork --loglevel=info --pidfile=/tmp/celery_worker.pid -n worker1@%h &

celery -A socyfie_application worker --pool=prefork --autoscale=6,2 --loglevel=info --pidfile=/tmp/celery_worker.pid -n worker1@%h &

#celery multi start 2 -A socyfie_application --autoscale=6,2 --pool=prefork --loglevel=info --logfile=~/celery_logs/%n%I.log --pidfile=~/celery_pids/%n.pid -n worker1@%h,worker2@%h &

celery -A socyfie_application beat --loglevel=info &

echo "Celery worker and beat are running."

