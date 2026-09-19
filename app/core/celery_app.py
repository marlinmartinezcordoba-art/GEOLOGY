"""
Trabajador de tareas pesadas.

Todo lo que antes chocaba contra el límite de ejecución de la plataforma anterior
vivirá aquí: lectura de documentos en formato portátil, llamados a modelos de
lenguaje, importación de hojas de control por lotes y generación de inventarios.
La petición web solo encola y responde de inmediato; el trabajador hace el
esfuerzo y reintenta solo cuando algo falla.

Arranque manual:
    celery -A app.core.celery_app.celery_app worker --loglevel=info -Q kustos
"""
from __future__ import annotations

import os

from celery import Celery

from app.core.config import configuracion

celery_app = Celery(
    "kustos",
    broker=configuracion.CELERY_BROKER_URL,
    backend=configuracion.CELERY_RESULT_BACKEND,
    include=["app.tasks", "app.tasks.nocturno"],
)

celery_app.conf.update(
    task_default_queue=configuracion.COLA_PREDETERMINADA,
    task_track_started=True,
    task_acks_late=True,                # si el trabajador muere, la tarea vuelve a la cola
    worker_prefetch_multiplier=1,       # reparto justo entre trabajadores
    # Un tomo de setecientos folios se lee en ocho bloques encadenados y cada bloque puede
    # tardar varios minutos. Media hora no alcanzaba y la tarea moría a mitad del tomo, que
    # es justo el caso que hay que sostener: lo grueso del fondo son libros empastados.
    task_time_limit=int(os.getenv("TECHO_MINUTOS_POR_TAREA", "150")) * 60,
    task_soft_time_limit=int(os.getenv("TECHO_MINUTOS_POR_TAREA", "150")) * 60 - 300,
    result_expires=60 * 60 * 24,
    timezone=configuracion.ZONA_HORARIA,
    enable_utc=True,
)

# ---------------------------------------------------------------------------
# El turno de noche
# ---------------------------------------------------------------------------
# Se despierta cada hora dentro de la ventana y la tarea decide si le toca o no. Se hace así,
# y no con una sola cita a las diez de la noche, porque si el computador estaba apagado o
# dormido a esa hora exacta, la noche entera se perdería sin que nadie se enterara. Despertar
# cada hora significa que el turno arranca en cuanto la máquina esté disponible.
#
# El horario se cambia con NOCTURNO_DESDE y NOCTURNO_HASTA en el archivo .env; para apagarlo
# del todo, NOCTURNO_ACTIVO=0.
from celery.schedules import crontab                                    # noqa: E402

_DESDE = int(os.getenv("NOCTURNO_DESDE", "22"))
_HASTA = int(os.getenv("NOCTURNO_HASTA", "6"))
_HORAS = ([h for h in range(_DESDE, 24)] + [h for h in range(0, _HASTA)]
          if _DESDE > _HASTA else list(range(_DESDE, _HASTA)))

celery_app.conf.beat_schedule = {
    "turno-de-noche": {
        "task": "kustos.turno_de_noche",
        "schedule": crontab(minute=5, hour=",".join(str(h) for h in _HORAS) or "22"),
    },
}

