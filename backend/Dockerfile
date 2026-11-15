# ARCA · API y trabajador del flujo (la misma imagen, distinto comando).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# OCR local (D-35): Tesseract con español y detección de orientación. Fuentes para los PDF.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tesseract-ocr-osd fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY alembic.ini ./
COPY alembic ./alembic
COPY arca ./arca
COPY scripts ./scripts

RUN useradd --system --uid 10001 --home /app arca && mkdir -p /datos/almacen && chown -R arca /datos
USER arca
ENV ARCA_ALMACEN_DIR=/datos/almacen ARCA_ENTORNO=produccion ARCA_TRABAJOS_EN_PROCESO=false
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/estado', timeout=8).status == 200 else 1)"
CMD ["sh", "-c", "uvicorn arca.main:app --host 0.0.0.0 --port 8000 --workers ${ARCA_WORKERS_API:-2} --proxy-headers --forwarded-allow-ips='*'"]
