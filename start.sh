#!/bin/sh
echo "Starting on port: $PORT"
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
