#!/bin/bash

# Define variables
PYTHON_PATH="/Users/vaibhav/python310"  # Set your custom Python path
REQUIREMENTS_FILE="/Users/vaibhav/Desktop/social-nmk--7sept/nmk/requirements.txt"  # Path to your requirements.txt file

# Create the custom Python directory if it doesn't exist
mkdir -p $PYTHON_PATH

# Set the environment variables to point to the custom Python path
export PYTHONUSERBASE=$PYTHON_PATH
export PATH="$PYTHON_PATH/bin:$PATH"

# Upgrade pip in the custom Python path
pip3 install --upgrade pip --user

# Install the packages from requirements.txt to the custom Python path
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip3 install --prefix=$PYTHON_PATH -r $REQUIREMENTS_FILE
else
    echo "requirements.txt not found."
    exit 1
fi

# Print a message indicating completion
echo "Packages installed successfully in ${PYTHON_PATH}"

# Export environment variables
export DJANGO_SETTINGS_MODULE="socyfie_application.settings"
# export SECRET_KEY="your-secret-key"
export DEBUG=True  # Set to False in production
# export DATABASE_URL="sqlite:///db.sqlite3"  # Update this with your database URL
export DATABASE_URL="database_setup/db.sqlite3"  # Update this with your database URL
export REDIS_URL="redis://localhost:6379/1"  # Example Redis URL if you use Redis

# Add any other environment variables your application needs
# export ANOTHER_VAR="value"

# Print a message indicating the environment variables are set
export PYTHONPATH="$PYTHON_PATH/bin:$PATH:/Users/vaibhav/python310/lib/python3.9/site-packages/"
echo $PYTHONPATH
echo "Environment variables set successfully."

# Optional: install dependencies if needed
# pip3 install -r /Users/vaibhav/Desktop/social-nmk--7sept/nmk/requirements.txt