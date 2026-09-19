# GEOLOGY · Plataforma de organización y descripción documental
# Contrato 733 de 2026 · Servicio Geológico Colombiano · Hometic SAS
#
# La versión de Debian va fijada a propósito: la etiqueta «slim» a secas sigue a la Debian
# del momento y, cuando esa cambia, los nombres de los paquetes del sistema cambian con ella.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Bogota

WORKDIR /srv/geology

# libpq5 es la biblioteca cliente de PostgreSQL que necesita psycopg2-binary.
# El resto es el motor de recepción técnica de lo digitalizado:
#   tesseract-ocr + spa   reconocimiento de texto en español para la copia de consulta
#   ghostscript           conversión a PDF/A (formato de preservación) y copia liviana
#   unpaper               enderezado y recorte de bordes
#   qpdf                  reparación de documentos portátiles
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 curl \
        tesseract-ocr tesseract-ocr-spa \
        ghostscript unpaper qpdf \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY geology ./geology

EXPOSE 8080

CMD ["uvicorn", "geology.main:aplicacion", "--host", "0.0.0.0", "--port", "8080"]
