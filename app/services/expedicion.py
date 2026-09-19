"""
Expedir en los formatos oficiales todo lo que ya está hecho.

Los datos de los expedientes viven en la base, no dentro de los archivos de Excel. Por eso
cambiar de formato no obliga a rehacer nada: se vuelven a expedir los instrumentos y salen
en la plantilla del Servicio Geológico con la misma información de siempre.

Este módulo arma el paquete completo —hojas de control, rótulos de caja y de carpeta e
inventario— y lo usan por igual la pantalla de descargas y el programa de mantenimiento que
lo deja escrito en una carpeta del servidor.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Caja, Expediente, Periodo, Seccion, Serie, Subserie, Trazabilidad
from app.services import formatos_sgc as fmt
from app.services import inventario as inv
from app.services.estados import Estado

# Los estados en los que un expediente ya tiene hoja de control que valga la pena expedir.
CON_HOJA = (Estado.HOJA_POR_REVISAR.value, Estado.HOJA_REVISADA.value,
            Estado.DESCRIPCION_POR_VALIDAR.value, Estado.DESCRIPCION_VALIDADA.value,
            Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value)


def completar_revisores(db: Session) -> int:
    """
    Rellena, en las hojas ya revisadas, quién las revisó y cuándo.

    El campo 15 del formato pasó a ser el responsable de la REVISIÓN, y esa columna nació
    vacía para todo lo que se revisó antes del cambio. El dato no se perdió: está en la
    bitácora, en el movimiento «revisar_hoja». Se toma de ahí, que es la fuente de verdad, y
    no se inventa: si un expediente no tiene ese movimiento, el campo se queda en blanco.

    Devuelve cuántos expedientes quedaron completados.
    """
    completados = 0
    pendientes = (db.query(Expediente)
                    .filter(Expediente.reviso_hoja.is_(None))
                    .filter(Expediente.estado.in_(CON_HOJA)).all())
    for exp in pendientes:
        huella = (db.query(Trazabilidad)
                    .filter(Trazabilidad.expediente_id == exp.id,
                            Trazabilidad.accion == "revisar_hoja")
                    .order_by(Trazabilidad.fecha.desc()).first())
        if not huella or not huella.usuario:
            continue
        exp.reviso_hoja = huella.usuario
        exp.fecha_revision = huella.fecha.date() if huella.fecha else None
        completados += 1
    if completados:
        db.commit()
    return completados


def _contexto(db: Session, exp: Expediente) -> dict:
    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    serie = db.get(Serie, sub.serie_id) if sub else None
    seccion = db.get(Seccion, serie.seccion_id) if serie else None
    periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
    return {"sub": sub, "serie": serie, "seccion": seccion, "periodo": periodo}


def datos_de_hoja(db: Session, exp: Expediente) -> dict:
    """Lo que necesita la plantilla F-GDM-007 para quedar llena."""
    c = _contexto(db, exp)
    return {
        "codigo_dependencia": c["seccion"].codigo_dependencia if c["seccion"] else "",
        "dependencia": c["seccion"].oficina_productora if c["seccion"] else "",
        "codigo_serie": c["serie"].codigo if c["serie"] else "",
        "serie": c["serie"].nombre if c["serie"] else "",
        "codigo_subserie": c["sub"].codigo if c["sub"] else "",
        "subserie": c["sub"].nombre if c["sub"] else "",
        # Campo 7 de la hoja: el nombre corto. Si el expediente todavía no lo tiene guardado
        # aparte —los descritos antes de separar las dos columnas— se cae al título, que es
        # lo que había entonces en esa casilla.
        "nombre_expediente": (exp.nombre_expediente or exp.titulo or ""),
        "reviso_hoja": exp.reviso_hoja or "",
        "fecha_revision": exp.fecha_revision,
        "responsable_hoja": exp.responsable_hoja or "",
        "fecha_diligenciamiento": exp.fecha_diligenciamiento,
        "tramites": [{"no_item": t.no_item, "fecha": t.fecha or t.fecha_texto,
                      "tipo_documental": t.tipo_documental, "folio_desde": t.folio_desde,
                      "folio_hasta": t.folio_hasta, "no_radicado": t.no_radicado,
                      "sistema_informacion": t.sistema_informacion,
                      "expediente_sgdea": t.expediente_sgdea,
                      "enlace_acceso": t.enlace_acceso,
                      "observaciones": t.observaciones} for t in exp.tramites],
    }


def _a_calculo(db: Session, exp: Expediente):
    c = _contexto(db, exp)
    return inv.CarpetaParaInventario(
        codigo_carpeta=exp.codigo_carpeta,
        periodo=c["periodo"].numero_romano if c["periodo"] else "",
        serie=c["serie"].nombre if c["serie"] else "",
        subserie=c["sub"].nombre if c["sub"] else "",
        fecha_inicial=exp.fecha_inicial, fecha_final=exp.fecha_final,
        estado=Estado(exp.estado), folios=exp.volumen_folios, titulo=exp.titulo,
        codigo_dependencia=c["seccion"].codigo_dependencia if c["seccion"] else "",
        dependencia=c["seccion"].oficina_productora if c["seccion"] else "",
        codigo_serie=c["serie"].codigo if c["serie"] else "",
        codigo_subserie=c["sub"].codigo if c["sub"] else "",
        consecutivo_en_caja=exp.consecutivo_en_caja)


def hojas_de_control(db: Session, expedientes: list[Expediente]) -> dict[str, bytes]:
    salida = {}
    for exp in expedientes:
        if not exp.tramites:
            continue
        salida[f"hojas_de_control/F-GDM-007_{exp.codigo_carpeta}.xlsx"] = (
            fmt.hoja_de_control(datos_de_hoja(db, exp)))
    return salida


def rotulos(db: Session, expedientes: list[Expediente], por_pagina: int = 4) -> dict[str, bytes]:
    """Los rótulos de cada caja definitiva que aparezca entre estos expedientes."""
    salida: dict[str, bytes] = {}
    cajas: dict[str, list[Expediente]] = {}
    for exp in expedientes:
        if exp.caja_definitiva:
            cajas.setdefault(exp.caja_definitiva, []).append(exp)

    for codigo, dentro in sorted(cajas.items()):
        dentro.sort(key=lambda e: e.consecutivo_en_caja or 0)
        calculos = [_a_calculo(db, e) for e in dentro]
        caja = db.query(Caja).filter(Caja.codigo == codigo).first()
        datos = inv.rotulo_de_caja(codigo, calculos, caja.periodo if caja else "")
        datos["carpetas"] = [
            f"Carpeta {c.consecutivo_en_caja}: {c.titulo or c.codigo_carpeta}"
            f" ({c.folios or '?'} folios)" for c in calculos if c.consecutivo_en_caja]
        iniciales = [c.fecha_inicial for c in calculos if c.fecha_inicial]
        finales = [c.fecha_final for c in calculos if c.fecha_final]
        datos["fecha_inicial_fecha"] = min(iniciales) if iniciales else None
        datos["fecha_final_fecha"] = max(finales) if finales else None
        salida[f"rotulos/{codigo}/F-GDM-008_rotulo_caja_{codigo}.xlsx"] = fmt.rotulo_de_caja(datos)

        de_carpeta = []
        for c, exp in zip(calculos, dentro):
            r = inv.rotulo_de_carpeta(c, codigo, tomo=f"{c.consecutivo_en_caja or 1} de {len(dentro)}")
            r["fecha_inicial_fecha"] = c.fecha_inicial
            r["fecha_final_fecha"] = c.fecha_final
            r["codigo_carpeta"] = exp.codigo_carpeta
            de_carpeta.append(r)
        if len(de_carpeta) == 1:
            nombre = f"F-GDM-006_rotulo_carpeta_{de_carpeta[0]['codigo_carpeta']}.xlsx"
            salida[f"rotulos/{codigo}/{nombre}"] = fmt.rotulo_de_carpeta(de_carpeta[0])
        elif de_carpeta:
            nombre = f"F-GDM-006_rotulos_carpetas_{codigo}_{por_pagina}_por_pagina.xlsx"
            salida[f"rotulos/{codigo}/{nombre}"] = fmt.pliego_de_rotulos_de_carpeta(
                de_carpeta, por_pagina)
    return salida


def inventario(db: Session, expedientes: list[Expediente], objeto: str = "") -> dict[str, bytes]:
    """El inventario de salida F-GDM-003 de los expedientes que ya están en caja definitiva."""
    en_caja = [e for e in expedientes if e.caja_definitiva]
    if not en_caja:
        return {}
    filas = []
    for i, exp in enumerate(en_caja, start=1):
        c = _contexto(db, exp)
        codigo = ".".join(x for x in (
            c["seccion"].codigo_dependencia if c["seccion"] else "",
            c["serie"].codigo if c["serie"] else "",
            c["sub"].codigo if c["sub"] else "") if x)
        filas.append({
            "orden": i, "codigo": codigo,
            "serie_subserie": " / ".join(x for x in (
                c["serie"].nombre if c["serie"] else "",
                c["sub"].nombre if c["sub"] else "") if x),
            "unidad_documental": exp.titulo or "",
            "fecha_inicial": exp.fecha_inicial.isoformat() if exp.fecha_inicial else (exp.fechas_texto or "S/F"),
            "fecha_final": exp.fecha_final.isoformat() if exp.fecha_final else "",
            "soporte_fisico": "X", "caja": exp.caja_definitiva or "",
            "carpeta": exp.consecutivo_en_caja or "", "correlativo": exp.codigo_carpeta,
            "folios": exp.volumen_folios or 0, "publico": "X",
            "notas": " ".join(x for x in (
                f"Código de referencia {exp.codigo_referencia or ''}.",
                f"Caja de origen {exp.caja_origen or '—'}.",
                exp.diferencia_folios or "") if x).strip()})
    primero = _contexto(db, en_caja[0])
    contenido = fmt.fuid(filas, {
        "entidad_remitente": "Hometic SAS",
        "entidad_productora": "Servicio Geológico Colombiano",
        "unidad_administrativa": primero["seccion"].unidad_administrativa if primero["seccion"] else "",
        "oficina_productora": primero["seccion"].oficina_productora if primero["seccion"] else "",
        "objeto": objeto or f"Inventario de salida del contrato 733 de 2026, {date.today().isoformat()}"})
    return {"F-GDM-003_inventario_de_salida.xlsx": contenido}


def armar(db: Session, caja: str | None = None, periodo: str | None = None,
          limite: int | None = None, por_pagina: int = 4,
          incluir: tuple[str, ...] = ("hojas", "rotulos", "inventario")) -> dict[str, bytes]:
    """
    Todo lo que ya está hecho, expedido en los formatos oficiales.

    Se puede acotar por caja o por periodo, y limitar la cantidad: cada hoja de control es un
    archivo completo con su logotipo, así que un paquete de miles pesa y tarda.
    """
    consulta = db.query(Expediente).filter(Expediente.estado.in_(CON_HOJA))
    if caja:
        consulta = consulta.filter(Expediente.caja_definitiva == caja.upper())
    if periodo:
        consulta = consulta.join(Periodo, Expediente.periodo_id == Periodo.id) \
                           .filter(Periodo.numero_romano == periodo.upper())
    consulta = consulta.order_by(Expediente.caja_definitiva, Expediente.consecutivo_en_caja,
                                 Expediente.codigo_carpeta)
    expedientes = consulta.limit(limite).all() if limite else consulta.all()

    archivos: dict[str, bytes] = {}
    if "hojas" in incluir:
        archivos.update(hojas_de_control(db, expedientes))
    if "rotulos" in incluir:
        archivos.update(rotulos(db, expedientes, por_pagina))
    if "inventario" in incluir:
        archivos.update(inventario(db, expedientes))
    return archivos
