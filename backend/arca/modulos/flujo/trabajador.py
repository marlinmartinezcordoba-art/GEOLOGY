"""Trabajador de la cola (D-39).

- En local, la aplicación lo arranca en un hilo (`ARCA_TRABAJOS_EN_PROCESO`, encendido por defecto en local).
- En producción se corre aparte, uno o varios:  `python -m arca.modulos.flujo.trabajador`
- El tablero del flujo puede procesar una tanda en el momento (útil sin trabajador, y en las pruebas).
"""

import logging
import threading
import time
import uuid

from arca.modulos.flujo.cola import tomar
from arca.nucleo import bd
from arca.nucleo.config import ajustes

log = logging.getLogger("arca.flujo")


def procesar(fabrica=None, limite: int = 50, proyecto_id: uuid.UUID | None = None) -> int:
    """Procesa hasta `limite` trabajos, cada uno en su propia sesión. Devuelve cuántos procesó."""
    from arca.modulos.flujo.servicios import ejecutar  # noqa: PLC0415

    fabrica = fabrica or bd.FabricaSesiones
    hechos = 0
    while hechos < limite:
        with fabrica() as db:
            t = tomar(db, proyecto_id)
            if t is None:
                break
            ejecutar(db, t)
        hechos += 1
    return hechos


class Hilo:
    def __init__(self) -> None:
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None

    def iniciar(self) -> None:
        self._hilo = threading.Thread(target=self._vuelta, name="arca-flujo", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()
        if self._hilo:
            self._hilo.join(timeout=10)

    def _vuelta(self) -> None:
        espera = ajustes().segundos_entre_revisiones
        while not self._parar.is_set():
            try:
                if procesar(limite=20) == 0:
                    self._parar.wait(espera)
            except Exception:  # noqa: BLE001 — el hilo no se cae: registra y sigue
                log.exception("Error en el trabajador del flujo")
                self._parar.wait(espera)


def encendido() -> bool:
    a = ajustes()
    return a.trabajos_en_proceso if a.trabajos_en_proceso is not None else a.entorno == "local"


def main() -> None:  # pragma: no cover - proceso aparte
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("Trabajador del flujo de ARCA en marcha")
    espera = ajustes().segundos_entre_revisiones
    while True:
        try:
            n = procesar(limite=50)
            if n:
                log.info("%s trabajos procesados", n)
            else:
                time.sleep(espera)
        except KeyboardInterrupt:
            break
        except Exception:  # noqa: BLE001
            log.exception("Error en el trabajador del flujo")
            time.sleep(espera)


if __name__ == "__main__":  # pragma: no cover
    main()
