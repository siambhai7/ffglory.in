#!/usr/bin/env bash
# Render build script
set -o errexit

pip install -r requirements.txt

# Pre-initialize the database so it's ready on first request
python -c "from app import init_db; init_db(); print('Database initialized successfully')"
