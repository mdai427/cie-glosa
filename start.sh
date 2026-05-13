#!/bin/sh
PORT_NUM=${PORT:-8000}
echo "Starting on port $PORT_NUM"
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT_NUM
