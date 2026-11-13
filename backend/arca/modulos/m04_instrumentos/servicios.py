"""M04 Instrumentos archivísticos: importar → validar → revisar → aprobar con acto administrativo → vigencia.

Reglas (Instrucciones M04 y Documento Maestro ARC-05):
- No se inventan códigos, tiempos de retención ni disposiciones: lo que falta es error y bloquea la aprobación.
- Se conserva la fuente (el archivo, con su huella), el acto administrativo, quién importó, quién aprobó y la vigencia.
- Quien importa una versión no la aprueba (segregación de funciones).
- Aprobar con vigencia desde ahora reemplaza a la vigente, que queda como evidencia; con fecha futura queda
  programada. La vigencia no puede ser pasada: lo ya clasificado conserva el instrumento con que se hizo.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from arca.modelos import ElementoInstrumento, EstadoProyecto, Instrumento, Proyecto, VersionInstrumento
from arca.modelos.base import ahora_utc, en_utc
from arca.modulos.m04_instrumentos import lector
from arca.modulos.m08_inventarios.servicios import guardar_archivo
from arca.nucleo.errores import AccesoDenegado, Conflicto, DatosInvalidos, NoEncontrado, TransicionInvalida

TIPOS = {"TRD": "Tabla de Retención Documental", "TVD": "Tabla de Valoración Documental", "CCD": "Cuadro de Clasificación Documental"}
CAMPOS_COMPARABLES = ("nombre", "padre", "tipos_documentales", "retencion_gestion", "retencion_central", "disposicion", "soporte", "procedimiento", "acceso")


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def listar(ctx, proyecto: Proyecto) -> list[Instrumento]:
    return list(ctx.db.scalars(select(Instrumento).where(Instrumento.proyecto_id == proyecto.id).order_by(Instrumento.tipo, Instrumento.nombre)))


def obtener(ctx, proyecto: Proyecto, instrumento_id: uuid.UUID) -> Instrumento:
    i = ctx.db.get(Instrumento, instrumento_id)
    if i is None or i.proyecto_id != proyecto.id:
        raise NoEncontrado("El instrumento no existe")
    return i


def crear(ctx, proyecto: Proyecto, tipo: str, nombre: str, descripcion: str, periodo_desde: date | None, periodo_hasta: date | None) -> Instrumento:
    _abierto(proyecto)
    if tipo not in TIPOS:
        raise DatosInvalidos(f"Tipo de instrumento desconocido. Use {', '.join(TIPOS)}")
    if periodo_desde and periodo_hasta and periodo_hasta < periodo_desde:
        raise DatosInvalidos("El periodo termina antes de empezar")
    if ctx.db.scalar(select(Instrumento).where(Instrumento.proyecto_id == proyecto.id, Instrumento.tipo == tipo, Instrumento.nombre == nombre.strip())):
        raise Conflicto("Ya existe un instrumento de ese tipo con ese nombre en el proyecto")
    i = Instrumento(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, tipo=tipo, nombre=nombre.strip(), descripcion=descripcion.strip(),
                    periodo_desde=periodo_desde, periodo_hasta=periodo_hasta, creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(i)
    ctx.db.flush()
    ctx.auditar(accion="CREAR_INSTRUMENTO", objeto="Instrumento", objeto_id=i.id, detalle=f"{proyecto.codigo} · {tipo} · {i.nombre}")
    ctx.db.commit()
    return i


def _actualizar_estados(ctx, instrumento: Instrumento) -> None:
    """Entre las aprobadas, la vigente es la de vigencia más reciente ya alcanzada."""
    ahora = ahora_utc()
    aprobadas = [v for v in ctx.db.scalars(select(VersionInstrumento).where(VersionInstrumento.instrumento_id == instrumento.id)) if v.vigente_desde]
    alcanzadas = sorted((v for v in aprobadas if en_utc(v.vigente_desde) <= ahora), key=lambda v: (en_utc(v.vigente_desde), v.version))
    vigente = alcanzadas[-1] if alcanzadas else None
    for v in aprobadas:
        v.estado = "vigente" if v is vigente else ("programada" if en_utc(v.vigente_desde) > ahora else "reemplazada")


def versiones(ctx, instrumento: Instrumento) -> list[VersionInstrumento]:
    _actualizar_estados(ctx, instrumento)
    return list(ctx.db.scalars(select(VersionInstrumento).where(VersionInstrumento.instrumento_id == instrumento.id).order_by(VersionInstrumento.version)))


def obtener_version(ctx, instrumento: Instrumento, version_id: uuid.UUID) -> VersionInstrumento:
    v = ctx.db.get(VersionInstrumento, version_id)
    if v is None or v.instrumento_id != instrumento.id:
        raise NoEncontrado("La versión no existe")
    return v


def importar(ctx, proyecto: Proyecto, instrumento: Instrumento, contenido: bytes, nombre_archivo: str, motivo: str) -> VersionInstrumento:
    _abierto(proyecto)
    if ctx.db.scalar(select(VersionInstrumento).where(VersionInstrumento.instrumento_id == instrumento.id, VersionInstrumento.estado == "borrador")):
        raise Conflicto("Ya hay una versión en borrador: apruébela o descártela antes de importar otra")
    r = lector.leer(contenido, nombre_archivo, instrumento.tipo.lower())
    archivo = guardar_archivo(ctx, proyecto, contenido, nombre_archivo, {"XLSX", "CSV"})
    ultima = ctx.db.scalar(select(func.max(VersionInstrumento.version)).where(VersionInstrumento.instrumento_id == instrumento.id)) or 0
    deps: dict[str, str] = {}
    for f in r.filas:
        deps.setdefault(f.codigo_dependencia, f.dependencia or f.codigo_dependencia)
    totales = {"dependencias": len(deps), "series": sum(1 for f in r.filas if f.nivel == "serie"), "subseries": sum(1 for f in r.filas if f.nivel == "subserie"),
               "tipos_documentales": sum(len(f.tipos) for f in r.filas)}
    v = VersionInstrumento(tenant_id=ctx.tenant_id, instrumento_id=instrumento.id, version=ultima + 1, estado="borrador", archivo_id=archivo.id, totales=totales,
                           errores=r.errores[:500], avisos=r.avisos[:500], correcciones=r.correcciones[:500], motivo=motivo, creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(v)
    ctx.db.flush()
    for codigo, nombre in deps.items():
        ctx.db.add(ElementoInstrumento(tenant_id=ctx.tenant_id, version_id=v.id, nivel="dependencia", codigo=codigo[:60], nombre=nombre[:300], codigo_dependencia=codigo[:40]))
    vistos: set[tuple[str, str]] = set()
    for f in r.filas:
        if (f.nivel, f.codigo) in vistos:  # el código repetido ya es un error de la validación
            continue
        vistos.add((f.nivel, f.codigo))
        ctx.db.add(ElementoInstrumento(
            tenant_id=ctx.tenant_id, version_id=v.id, nivel=f.nivel, codigo=f.codigo[:60], nombre=f.nombre[:300], codigo_dependencia=f.codigo_dependencia[:40], padre=f.padre,
            tipos_documentales=f.tipos, retencion_gestion=f.ag, retencion_central=f.ac, disposicion=f.disposicion, soporte=f.soporte, procedimiento=f.procedimiento,
            acceso=f.acceso, hoja=f.hoja[:100], fila=f.fila,
        ))
    ctx.auditar(accion="IMPORTAR_INSTRUMENTO", objeto="VersionInstrumento", objeto_id=v.id, motivo=motivo,
                detalle=f"{proyecto.codigo} · {instrumento.tipo} {instrumento.nombre} v{v.version} · {totales['series']} series, {totales['subseries']} subseries · "
                        f"{len(r.errores)} errores, {len(r.avisos)} avisos · SHA-256 {archivo.sha256[:16]}…")
    ctx.db.commit()
    return v


def aprobar(ctx, proyecto: Proyecto, instrumento: Instrumento, v: VersionInstrumento, acto: str, fecha_acto: date, convalidacion: str, vigente_desde: datetime | None, motivo: str) -> VersionInstrumento:
    _abierto(proyecto)
    if v.estado != "borrador":
        raise TransicionInvalida("Solo se aprueba una versión en borrador")
    if v.errores:
        raise TransicionInvalida(f"La versión tiene {len(v.errores)} errores: corrija el archivo e impórtelo de nuevo")
    if v.creado_por == ctx.usuario.id:
        raise AccesoDenegado("Quien importó la versión no puede aprobarla (segregación de funciones)")
    if fecha_acto > date.today():
        raise DatosInvalidos("La fecha del acto administrativo no puede ser futura")
    ahora = ahora_utc()
    vigencia = en_utc(vigente_desde) if vigente_desde else ahora
    if vigencia < ahora - timedelta(minutes=2):
        raise DatosInvalidos("La vigencia no puede ser pasada: lo ya clasificado conserva el instrumento con que se hizo")
    v.acto_administrativo, v.fecha_acto, v.convalidacion = acto.strip(), fecha_acto, convalidacion.strip() or None
    v.vigente_desde, v.aprobado_en, v.aprobado_por = max(vigencia, ahora), ahora, ctx.usuario.id
    v.estado = "programada"
    ctx.db.flush()
    _actualizar_estados(ctx, instrumento)
    ctx.auditar(accion="APROBAR_INSTRUMENTO", objeto="VersionInstrumento", objeto_id=v.id, motivo=motivo,
                detalle=f"{instrumento.tipo} {instrumento.nombre} v{v.version} · {acto} del {fecha_acto.isoformat()} · vigente desde {v.vigente_desde.isoformat()}")
    ctx.db.commit()
    return v


def descartar(ctx, instrumento: Instrumento, v: VersionInstrumento, motivo: str) -> VersionInstrumento:
    if v.estado != "borrador":
        raise TransicionInvalida("Solo se descarta un borrador; una versión aprobada se reemplaza con otra")
    v.estado = "descartada"
    ctx.auditar(accion="DESCARTAR_INSTRUMENTO", objeto="VersionInstrumento", objeto_id=v.id, motivo=motivo, detalle=f"{instrumento.tipo} {instrumento.nombre} v{v.version}")
    ctx.db.commit()
    return v


def elementos(ctx, v: VersionInstrumento) -> list[ElementoInstrumento]:
    orden = {"dependencia": 0, "serie": 1, "subserie": 2}
    return sorted(ctx.db.scalars(select(ElementoInstrumento).where(ElementoInstrumento.version_id == v.id)), key=lambda e: (e.codigo_dependencia, orden[e.nivel] > 0, e.codigo))


def comparar(ctx, instrumento: Instrumento, desde: VersionInstrumento, hasta: VersionInstrumento) -> dict[str, Any]:
    """Qué cambió entre dos versiones: series y subseries nuevas, retiradas y modificadas campo por campo."""
    a = {(e.nivel, e.codigo): e for e in elementos(ctx, desde) if e.nivel != "dependencia"}
    b = {(e.nivel, e.codigo): e for e in elementos(ctx, hasta) if e.nivel != "dependencia"}
    cambios = []
    for clave in sorted(set(a) & set(b), key=lambda k: k[1]):
        diferencias = {c: [getattr(a[clave], c), getattr(b[clave], c)] for c in CAMPOS_COMPARABLES if getattr(a[clave], c) != getattr(b[clave], c)}
        if diferencias:
            cambios.append({"nivel": clave[0], "codigo": clave[1], "nombre": b[clave].nombre, "cambios": diferencias})
    resumen = lambda e: {"nivel": e.nivel, "codigo": e.codigo, "nombre": e.nombre, "disposicion": e.disposicion}  # noqa: E731
    return {"desde": desde.version, "hasta": hasta.version, "nuevas": [resumen(b[k]) for k in sorted(set(b) - set(a), key=lambda k: k[1])],
            "retiradas": [resumen(a[k]) for k in sorted(set(a) - set(b), key=lambda k: k[1])], "modificadas": cambios}


def codigos_vigentes(ctx, proyecto_id: uuid.UUID) -> set[str] | None:
    """Códigos de serie y subserie vigentes en los instrumentos del proyecto (TRD y TVD). None si no hay ninguno vigente."""
    instrumentos = list(ctx.db.scalars(select(Instrumento).where(Instrumento.proyecto_id == proyecto_id, Instrumento.tipo.in_(("TRD", "TVD")))))
    codigos: set[str] = set()
    hay = False
    for i in instrumentos:
        _actualizar_estados(ctx, i)
        v = ctx.db.scalar(select(VersionInstrumento).where(VersionInstrumento.instrumento_id == i.id, VersionInstrumento.estado == "vigente"))
        if v:
            hay = True
            codigos |= {e.codigo for e in ctx.db.scalars(select(ElementoInstrumento).where(ElementoInstrumento.version_id == v.id, ElementoInstrumento.nivel != "dependencia"))}
    return codigos if hay else None
