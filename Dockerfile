FROM python:3.11-slim

# Dependencias del sistema (sin cargo/Rust)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# --prefer-binary: usa wheels precompilados, evita compilar desde fuente
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY . .

RUN mkdir -p uploads static/img

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
