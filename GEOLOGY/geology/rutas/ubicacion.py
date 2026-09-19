"""
Reubicación en cajas definitivas, rótulos e inventario de salida.

El orden es el que definió la dirección del proyecto: cuando un expediente ya tiene hoja de
control y descripción aprobada, una persona lo asigna a una caja definitiva. El sistema le
pone el número de carpeta, arma los dos rótulos y, al cerrar la caja, deja el inventario en
firme.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from geology.nucleo.bd import obtener_sesion
from geology.modelos import Caja, Expediente, Periodo, Seccion, Serie, Subserie, Trazabilidad
from geology.rutas.cuentas import usuario_actual
from geology.dominio import cajas as inv
from geology.dominio.estados import Estado, Usuario

router = APIRouter(prefix="/ubicacion", tags=["Reubicación"])


class AsignacionEntrada(BaseModel):
    caja: str = Field(pattern=r"^AH-CJ-\d{1,5}$", examples=["AH-CJ-00001"])
    carpetas: list[str] = Field(min_length=1, description="Códigos de carpeta a asignar")


def _a_calculo(db: Session, exp: Expediente) -> inv.CarpetaParaInventario:
    periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    serie = db.get(Serie, sub.serie_id) if sub else None
    seccion = db.get(Seccion, serie.seccion_id) if serie else None
    return inv.CarpetaParaInventario(
        codigo_carpeta=exp.codigo_carpeta, periodo=periodo.numero_romano if periodo else "",
        serie=serie.nombre if serie else "", subserie=sub.nombre if sub else "",
        fecha_inicial=exp.fecha_inicial, fecha_final=exp.fecha_final,
        estado=Estado(exp.estado), folios=exp.volumen_folios, titulo=exp.titulo,
        codigo_dependencia=seccion.codigo_dependencia if seccion else "",
        dependencia=seccion.oficina_productora if seccion else "",
        codigo_serie=serie.codigo if serie else "",
        codigo_subserie=sub.codigo if sub else "",
        consecutivo_en_caja=exp.consecutivo_en_caja)


def _normalizar_caja(codigo: str) -> str:
    from geology.dominio.codigos import normalizar_codigo_caja
    normalizado = normalizar_codigo_caja(codigo)
    if not normalizado or not normalizado.startswith("AH-CJ"):
        raise HTTPException(422, f"«{codigo}» no es una caja definitiva. Use la forma AH-CJ-00001.")
    return normalizado


@router.get("/pendientes", summary="Descripciones aprobadas que esperan caja definitiva")
def pendientes(db: Session = Depends(obtener_sesion),
               quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    salida = []
    for exp in (db.query(Expediente).filter(Expediente.estado == Estado.ARCHIVADO.value)
                  .order_by(Expediente.codigo_carpeta).all()):
        c = _a_calculo(db, exp)
        salida.append({"codigo_carpeta": c.codigo_carpeta, "periodo": c.periodo,
                       "serie": c.serie, "subserie": c.subserie, "folios": c.folios,
                       "titulo": c.titulo, "fechas": exp.fechas_texto})
    return salida


@router.get("/cajas", summary="Cajas definitivas y su estado")
def cajas(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    return [{"codigo": c.codigo, "periodo": c.periodo, "total_carpetas": c.total_carpetas,
             "cerrada": c.cerrada, "cerrada_por": c.cerrada_por,
             "cerrada_en": c.cerrada_en.isoformat(timespec="minutes") if c.cerrada_en else None}
            for c in db.query(Caja).order_by(Caja.codigo).all()]


@router.post("/asignar", summary="Asignar carpetas a una caja definitiva")
def asignar(datos: AsignacionEntrada, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    La persona elige la caja y cuántas carpetas entran, una o las que quepan. El sistema
    genera el número de carpeta y bloquea la mezcla de periodos.
    """
    if not quien.aprueba_descripcion:
        raise HTTPException(403, "La reubicación en cajas definitivas la hace la dirección del "
                                 "proyecto o la líder.")
    codigo_caja = _normalizar_caja(datos.caja)

    caja = db.query(Caja).filter(Caja.codigo == codigo_caja).first()
    if caja and caja.cerrada:
        raise HTTPException(409, f"La caja {codigo_caja} está cerrada y su inventario quedó en "
                                 "firme. Reábrala de manera explícita si de verdad hay que cambiarla.")

    ya_en_la_caja = db.query(Expediente).filter(Expediente.caja_definitiva == codigo_caja).all()
    series_previas = [_a_calculo(db, e).serie for e in ya_en_la_caja]
    siguiente = max([e.consecutivo_en_caja or 0 for e in ya_en_la_caja], default=0) + 1

    expedientes = {}
    calculos = []
    for codigo in datos.carpetas:
        from geology.dominio.codigos import normalizar_codigo_carpeta
        carpeta = normalizar_codigo_carpeta(codigo) or codigo.upper()
        exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()
        if not exp:
            raise HTTPException(404, f"La carpeta {carpeta} no está en GEOLOGY.")
        expedientes[carpeta] = exp
        calculos.append(_a_calculo(db, exp))

    try:
        r = inv.asignar_a_caja(calculos, codigo_caja, caja.periodo if caja else "",
                               series_previas, siguiente, cerrada=bool(caja and caja.cerrada))
    except inv.CajaCerrada as e:
        raise HTTPException(409, str(e))
    except inv.MezclaDePeriodos as e:
        raise HTTPException(409, str(e))

    if not caja:
        caja = Caja(codigo=codigo_caja, periodo=r.periodo_de_la_caja)
        db.add(caja)
        db.flush()

    for c in r.asignadas:
        exp = expedientes[c.codigo_carpeta]
        exp.caja_definitiva = codigo_caja
        exp.consecutivo_en_caja = c.consecutivo_en_caja
        db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                            estado_nuevo=Estado.EN_INVENTARIO.value, accion="asignar_caja",
                            usuario=quien.nombre,
                            motivo=f"Caja {codigo_caja}, carpeta {c.consecutivo_en_caja}"))
        exp.estado = Estado.EN_INVENTARIO.value

    caja.total_carpetas = db.query(Expediente).filter(
        Expediente.caja_definitiva == codigo_caja).count() + len(r.asignadas)
    db.commit()
    caja.total_carpetas = db.query(Expediente).filter(Expediente.caja_definitiva == codigo_caja).count()
    db.commit()

    return {
        "caja": codigo_caja, "periodo_de_la_caja": r.periodo_de_la_caja,
        "asignadas": [{"carpeta": c.codigo_carpeta, "no_carpeta": c.consecutivo_en_caja,
                       "serie": c.serie, "folios": c.folios} for c in r.asignadas],
        "rechazadas": [{"carpeta": k, "motivo": v} for k, v in r.rechazadas],
        "avisos": r.avisos,
        "total_en_la_caja": caja.total_carpetas,
        "mensaje": (f"{len(r.asignadas)} carpeta(s) asignadas a la caja {codigo_caja}. "
                    "Imprima los rótulos y cierre la caja cuando ya no le quepan más."),
    }


@router.get("/caja/{codigo_caja}/rotulos", summary="Rótulos de la caja y de sus carpetas")
def rotulos(codigo_caja: str, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    codigo = _normalizar_caja(codigo_caja)
    caja = db.query(Caja).filter(Caja.codigo == codigo).first()
    if not caja:
        raise HTTPException(404, f"La caja {codigo} no existe todavía.")
    expedientes = (db.query(Expediente).filter(Expediente.caja_definitiva == codigo)
                     .order_by(Expediente.consecutivo_en_caja).all())
    calculos = [_a_calculo(db, e) for e in expedientes]
    total = len(calculos)
    return {
        "caja": inv.rotulo_de_caja(codigo, calculos, caja.periodo),
        "carpetas": [inv.rotulo_de_carpeta(c, codigo, tomo=f"1 de {total}") for c in calculos],
        "cerrada": caja.cerrada,
    }


@router.get("/caja/{codigo_caja}/rotulos.xlsx",
            summary="Rótulos de la caja y de sus carpetas en los formatos oficiales")
def rotulos_en_excel(codigo_caja: str,
                     por_pagina: int = Query(4, description="Rótulos de carpeta por hoja oficio: 1, 2 o 4"),
                     db: Session = Depends(obtener_sesion),
                     quien: Usuario = Depends(usuario_actual)):
    """
    El rótulo de la caja F-GDM-008 y los de sus carpetas F-GDM-006, en las plantillas del
    Servicio Geológico y listos para imprimir.

    El de la caja sale a 10,4 por 25 centímetros, que es la cara frontal de la X-100. Los de
    carpeta salen juntos en hojas oficio: cuatro por página, que es como caben, a 15,4 por
    9,7 centímetros cada uno. Con «por_pagina=2» o «por_pagina=1» salen a tamaño completo,
    17 por 13, a costa de gastar más papel.
    """
    from datetime import date as _fecha

    from fastapi.responses import Response

    from geology.dominio import formatos_sgc as fmt

    codigo = _normalizar_caja(codigo_caja)
    caja = db.query(Caja).filter(Caja.codigo == codigo).first()
    if not caja:
        raise HTTPException(404, f"La caja {codigo} no existe todavía.")
    expedientes = (db.query(Expediente).filter(Expediente.caja_definitiva == codigo)
                     .order_by(Expediente.consecutivo_en_caja).all())
    if not expedientes:
        raise HTTPException(404, f"La caja {codigo} todavía no tiene carpetas asignadas.")
    calculos = [_a_calculo(db, e) for e in expedientes]
    total = len(calculos)

    datos_caja = inv.rotulo_de_caja(codigo, calculos, caja.periodo)
    datos_caja["carpetas"] = [
        f"Carpeta {c.consecutivo_en_caja}: {c.titulo or c.codigo_carpeta}"
        f" ({c.folios or '?'} folios)" for c in calculos if c.consecutivo_en_caja]
    iniciales = [c.fecha_inicial for c in calculos if c.fecha_inicial]
    finales = [c.fecha_final for c in calculos if c.fecha_final]
    datos_caja["fecha_inicial_fecha"] = min(iniciales) if iniciales else None
    datos_caja["fecha_final_fecha"] = max(finales) if finales else None

    archivos = {f"F-GDM-008_rotulo_caja_{codigo}.xlsx": fmt.rotulo_de_caja(datos_caja)}

    # Los rótulos de carpeta de una misma caja salen juntos, repartidos en hojas oficio. Con
    # una sola carpeta se entrega el rótulo solo, a tamaño completo; con varias se imprimen
    # cuatro por página para no gastar una hoja por etiqueta.
    rotulos_de_carpeta = []
    for c, exp in zip(calculos, expedientes):
        r = inv.rotulo_de_carpeta(c, codigo, tomo=f"{c.consecutivo_en_caja or 1} de {total}")
        r["fecha_inicial_fecha"] = c.fecha_inicial
        r["fecha_final_fecha"] = c.fecha_final
        r["codigo_carpeta"] = exp.codigo_carpeta
        rotulos_de_carpeta.append(r)

    if len(rotulos_de_carpeta) == 1:
        nombre = f"F-GDM-006_rotulo_carpeta_{rotulos_de_carpeta[0]['codigo_carpeta']}.xlsx"
        archivos[nombre] = fmt.rotulo_de_carpeta(rotulos_de_carpeta[0])
    else:
        archivos[f"F-GDM-006_rotulos_carpetas_{codigo}_{por_pagina}_por_pagina.xlsx"] = (
            fmt.pliego_de_rotulos_de_carpeta(rotulos_de_carpeta, por_pagina))

    return Response(fmt.paquete(archivos), media_type="application/zip", headers={
        "Content-Disposition":
            f'attachment; filename="ROTULOS_{codigo}_{_fecha.today().isoformat()}.zip"'})


@router.post("/caja/{codigo_caja}/cerrar", summary="Cerrar la caja y dejar el inventario en firme")
def cerrar(codigo_caja: str, db: Session = Depends(obtener_sesion),
           quien: Usuario = Depends(usuario_actual)) -> dict:
    if not quien.aprueba_descripcion:
        raise HTTPException(403, "Cerrar una caja lo hace la dirección del proyecto o la líder.")
    codigo = _normalizar_caja(codigo_caja)
    caja = db.query(Caja).filter(Caja.codigo == codigo).first()
    if not caja:
        raise HTTPException(404, f"La caja {codigo} no existe.")
    if caja.cerrada:
        raise HTTPException(409, f"La caja {codigo} ya estaba cerrada desde el "
                                 f"{caja.cerrada_en:%Y-%m-%d} por {caja.cerrada_por}.")
    if not caja.total_carpetas:
        raise HTTPException(409, f"La caja {codigo} no tiene carpetas. No tiene sentido cerrarla.")
    caja.cerrada = True
    caja.cerrada_en = datetime.now()
    caja.cerrada_por = quien.nombre
    db.commit()
    return {"caja": codigo, "cerrada": True, "total_carpetas": caja.total_carpetas,
            "mensaje": (f"Caja {codigo} cerrada con {caja.total_carpetas} carpeta(s). Su "
                        "inventario de salida queda en firme y ya no se modifica.")}


@router.post("/caja/{codigo_caja}/reabrir", summary="Reabrir una caja cerrada")
def reabrir(codigo_caja: str, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    """Acto excepcional y explícito. Queda registrado quién la reabrió y cuándo."""
    if quien.rol.value != "administradora":
        raise HTTPException(403, "Reabrir una caja cerrada solo lo hace la dirección del proyecto.")
    codigo = _normalizar_caja(codigo_caja)
    caja = db.query(Caja).filter(Caja.codigo == codigo).first()
    if not caja or not caja.cerrada:
        raise HTTPException(409, f"La caja {codigo} no está cerrada.")
    caja.observaciones = ((caja.observaciones or "") +
                          f"\nReabierta por {quien.nombre} el {datetime.now():%Y-%m-%d %H:%M}.").strip()
    caja.cerrada = False
    caja.cerrada_en = None
    caja.cerrada_por = None
    db.commit()
    return {"caja": codigo, "cerrada": False,
            "mensaje": f"Caja {codigo} reabierta. Quedó constancia en sus observaciones."}
