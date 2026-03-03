#!/bin/bash
exec gunicorn --bind 0.0.0.0:8009 --workers 2 --threads 8 --timeout 120 app:app
