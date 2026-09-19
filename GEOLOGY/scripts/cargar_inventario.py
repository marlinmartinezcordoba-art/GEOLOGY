"""
Carga el inventario de origen del contrato, es decir las carpetas que sí pertenecen a la
selección inventariada (regla R3), y las tablas de valoración documental convalidadas.

Uso dentro de Docker:
    docker compose exec servidor python scripts/cargar_inventario.py

Es repetible: si ya está cargado, actualiza en lugar de duplicar.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from geology.nucleo.bd import SesionLocal, crear_tablas
from geology.modelos import Fondo, Periodo, Seccion, Serie, Subserie, UnidadInventario

RAIZ = Path(__file__).resolve().parent.parent
FUID = RAIZ / "datos" / "FUID_ORIGEN_7699_Unidades.xlsx"
TVD = RAIZ / "datos" / "TVD_CONSOLIDADA_SGC733.xlsx"

ROMANOS = ["I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII","XIII","XIV","XV","XVI","XVII"]
MESES = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,
         "septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}


def _entero(valor):
    m = re.search(r"\d+", str(valor or ""))
    return int(m.group(0)) if m else None


def _iso(texto):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(texto or "").strip()[:10])
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _fecha_es(texto: str):
    m = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-zñ]+)\s+(?:de\s+)?(\d{4})", str(texto).lower())
    if m and m.group(2) in MESES:
        try:
            return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    return None


def _rango(texto: str):
    partes = re.split(r"\s*[-–]\s*(?=\d{1,2}\s)|\sal\s|\shasta\s", str(texto), maxsplit=1)
    return (_fecha_es(partes[0]) if partes else None,
            _fecha_es(partes[1]) if len(partes) > 1 else None)


def cargar_tvd(db) -> None:
    if not TVD.exists():
        print("AVISO. No se encontró la tabla de valoración en datos/; se omite.")
        return
    fondo = db.query(Fondo).filter_by(codigo="SGC").first()
    if not fondo:
        fondo = Fondo(codigo="SGC", nombre="Servicio Geológico Colombiano")
        db.add(fondo); db.flush()

    hoja = openpyxl.load_workbook(TVD, read_only=True, data_only=True)["TVD_CONSOLIDADA"]
    filas = hoja.iter_rows(values_only=True)
    next(filas)
    encabezado = [str(c or "").strip().upper() for c in next(filas)]
    col = {n: i for i, n in enumerate(encabezado)}
    nuevas = 0

    for fila in filas:
        if not fila or not fila[col["PERIODO"]]:
            continue
        g = lambda k: (str(fila[col[k]]).strip() if col.get(k) is not None and fila[col[k]] is not None else "")
        romano = g("PERIODO").upper()
        if romano not in ROMANOS:
            continue
        periodo = db.query(Periodo).filter_by(fondo_id=fondo.id, numero_romano=romano).first()
        if not periodo:
            ini, fin = _rango(g("RANGO DEL PERIODO"))
            periodo = Periodo(fondo=fondo, numero_romano=romano, orden=ROMANOS.index(romano) + 1,
                              rango_texto=g("RANGO DEL PERIODO"), fecha_inicio=ini, fecha_fin=fin,
                              entidad_productora=g("ENTIDAD PRODUCTORA"),
                              fecha_convalidacion_tvd=date(2023, 11, 30))
            db.add(periodo); db.flush()
        seccion = db.query(Seccion).filter_by(periodo_id=periodo.id, codigo_dependencia=g("COD DEPENDENCIA"),
                                              oficina_productora=g("OFICINA PRODUCTORA")).first()
        if not seccion:
            seccion = Seccion(periodo=periodo, codigo_dependencia=g("COD DEPENDENCIA"),
                              unidad_administrativa=g("UNIDAD ADMINISTRATIVA"),
                              oficina_productora=g("OFICINA PRODUCTORA"))
            db.add(seccion); db.flush()
        serie = db.query(Serie).filter_by(seccion_id=seccion.id, codigo=g("COD SERIE")).first()
        if not serie:
            serie = Serie(seccion=seccion, codigo=g("COD SERIE"), nombre=g("SERIE"),
                          retencion_central_anios=_entero(g("RETENCION AC")),
                          disposicion_final=g("DISPOSICION FINAL") or None)
            db.add(serie); db.flush()
        if not db.query(Subserie).filter_by(serie_id=serie.id, codigo=g("COD SUBSERIE")).first():
            db.add(Subserie(serie=serie, codigo=g("COD SUBSERIE"), nombre=g("SUBSERIE"),
                            soporte=g("SOPORTE"), retencion_central_anios=_entero(g("RETENCION AC")),
                            disposicion_final=g("DISPOSICION FINAL") or None))
            db.flush(); nuevas += 1
    db.commit()
    print(f"Tablas de valoración: {db.query(Periodo).count()} periodos, "
          f"{db.query(Serie).count()} series, {db.query(Subserie).count()} subseries "
          f"(nuevas en esta corrida: {nuevas}).")


def cargar_inventario(db) -> None:
    if not FUID.exists():
        print(f"ERROR. No se encontró {FUID}. Deje el archivo en la carpeta datos.")
        return
    hoja = openpyxl.load_workbook(FUID, read_only=True, data_only=True)["FUID_ORIGEN"]
    filas = hoja.iter_rows(values_only=True)
    next(filas)
    encabezado = [str(c or "").strip().upper() for c in next(filas)]
    col = {n: i for i, n in enumerate(encabezado)}

    existentes = {u.codigo_carpeta: u for u in db.query(UnidadInventario).all()}
    nuevas = actualizadas = 0

    for fila in filas:
        if not fila or not fila[col["CARPETA"]]:
            continue
        g = lambda k: (str(fila[col[k]]).strip() if col.get(k) is not None and fila[col[k]] is not None else "")
        codigo = g("CARPETA").upper()
        if not re.fullmatch(r"AC-CP-\d{5}", codigo):
            continue
        periodo = g("PERIODO").upper()
        if periodo in ("S/F", "SF", "N/A", "SP"):
            periodo = ""
        datos = dict(periodo=periodo, folios=_entero(g("FOLIOS")),
                     asunto=g("ASUNTO") or None, caja_origen=g("CAJA").upper() or None,
                     cod_serie=g("COD SER")[:60] or None, serie=g("SERIE")[:200] or None,
                     cod_subserie=g("COD SUBS")[:60] or None, subserie=g("SUBSERIE")[:200] or None,
                     fecha_inicial=_iso(g("FECHA INICIAL")), fecha_final=_iso(g("FECHA FINAL")))
        unidad = existentes.get(codigo)
        if unidad:
            for k, v in datos.items():
                setattr(unidad, k, v)
            actualizadas += 1
        else:
            db.add(UnidadInventario(codigo_carpeta=codigo, **datos))
            nuevas += 1
        if (nuevas + actualizadas) % 1000 == 0:
            db.flush()
    db.commit()
    total = db.query(UnidadInventario).count()
    sin_periodo = db.query(UnidadInventario).filter(UnidadInventario.periodo == "").count()
    print(f"Inventario de origen: {total} carpetas ({nuevas} nuevas, {actualizadas} actualizadas). "
          f"Sin periodo en el inventario: {sin_periodo}.")


if __name__ == "__main__":
    crear_tablas()
    db = SesionLocal()
    try:
        cargar_tvd(db)
        cargar_inventario(db)
        print("\nListo. Ya puede cargar cualquier carpeta del inventario del contrato.")
    finally:
        db.close()
