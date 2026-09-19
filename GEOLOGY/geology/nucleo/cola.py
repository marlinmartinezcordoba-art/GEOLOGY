"""
Procesador de trabajos pesados.

La petición web solo encola y responde de inmediato; el procesador lee el expediente
digitalizado, llama a los lectores (modelos de lenguaje), importa hojas de control por lotes y
genera instrumentos, y reintenta solo cuando algo falla.

Arranque manual:
    celery -A geology.nucleo.cola.celery_app worker --loglevel=info -Q geology
"""
from __future__ import annotations

import os

from celery import Celery

from geology.nucleo.ajustes import configuracion

celery_app = Celery(
    "geology",
    broker=configuracion.CELERY_BROKER_URL,
    backend=configuracion.CELERY_RESULT_BACKEND,
    include=["geology.trabajos"],
)

celery_app.conf.update(
    task_default_queue=configuracion.COLA_PREDETERMINADA,
    task_track_started=True,
    task_acks_late=True,                # si el procesador muere, el trabajo vuelve a la cola
    worker_prefetch_multiplier=1,       # reparto justo entre procesos
    # Un tomo de setecientos folios se lee en varios bloques encadenados y cada bloque puede
    # tardar varios minutos; el techo se fija en minutos por trabajo.
    task_time_limit=int(os.getenv("TECHO_MINUTOS_POR_TAREA", "150")) * 60,
    task_soft_time_limit=int(os.getenv("TECHO_MINUTOS_POR_TAREA", "150")) * 60 - 300,
    result_expires=60 * 60 * 24,
    timezone=configuracion.ZONA_HORARIA,
    enable_utc=True,
)
