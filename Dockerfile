FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    poppler-utils \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY . .

RUN mkdir -p uploads static/img
RUN chmod +x start.sh

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "start.sh"]
