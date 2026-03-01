# =============================================================================
# Gunicorn Configuration — auto-loaded when gunicorn starts
# =============================================================================
# This file is auto-detected by gunicorn (no CLI flag needed).
# It sets defaults; CLI flags (like --bind 0.0.0.0:$PORT) override these.

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1                      # Free tier: 1 worker to save memory
threads = 2                      # Handle concurrent requests within the worker
timeout = 120                    # Give worker 2 min (default 30s kills it)
accesslog = "-"                  # Log requests to stdout
errorlog = "-"                   # Log errors to stdout
