"""M08 Inventarios y FUID: importar → mapear → validar → reportar → corregir → integrar.

Reglas (Instrucciones M08):
- No se sobrescribe la fuente: el archivo queda en el repositorio y cada fila se guarda tal como llegó,
  junto a su valor normalizado y sus errores.
- Solo se integran las filas válidas. Si quedan filas con errores, integrar exige un motivo y el lote deja
  constancia exacta de cuántas se aceptaron y cuántas se rechazaron (conciliación).
- Un identificador no se repite dentro del proyecto: una unidad existente nunca se pisa.
- La IA no participa aquí: nada se completa por inferencia.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select

from arca.modelos import ArchivoDigital, EstadoLote, EstadoProyecto, FilaInventario, LoteInventario, Proyecto, UnidadDocumental
from arca.modelos.base import ahora_utc
from arca.modulos.m08_inventarios import fuid
from arca.nucleo import almacen
from arca.nucleo.config import ajustes
from arca.nucleo.errores import DatosInvalidos, NoEncontrado, TransicionInvalida


def guardar_archivo(ctx, proyecto: Proyecto, contenido: bytes, nombre: str, formatos: set[str]) -> ArchivoDigital:
    ident = almacen.identificar(contenido, nombre)
    if ident is None or ident.formato not in formatos:
        raise DatosInvalidos(f"«{nombre}» no es un formato admitido aquí ({', '.join(sorted(formatos))})")
    clave = almacen.guardar(ctx.tenant_id, contenido)
    archivo = ArchivoDigital(
        tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, nombre_original=nombre[:500], formato=ident.formato, mime=ident.mime,
        tamano=len(contenido), sha256=almacen.huella(contenido), clave_almacen=clave, creado_en=ahora_utc(), creado_por=ctx.usuario.id,
    )
    ctx.db.add(archivo)
    ctx.db.flush()
    return archivo


def _exigir_abierto(proyecto: Proyecto) -> None:
    if proyecto.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def _validar_filas(ctx, lote: LoteInventario, hoja: fuid.Hoja) -> None:
    """Borra el resultado anterior del lote (si se cambió el mapeo) y vuelve a validar cada fila."""
    for anterior in ctx.db.scalars(select(FilaInventario).where(FilaInventario.lote_id == lote.id)):
        ctx.db.delete(anterior)
    ctx.db.flush()
    existentes = set(ctx.db.scalars(select(UnidadDocumental.clave).where(UnidadDocumental.proyecto_id == lote.proyecto_id)))
    from arca.modulos.m04_instrumentos.servicios import codigos_vigentes  # evita la importación circular (M04 guarda archivos con M08)

    vigentes = codigos_vigentes(ctx, lote.proyecto_id)
    vistas: dict[str, int] = {}
    validas = con_error = 0
    for numero, celdas in hoja.filas:
        normalizado, errores, avisos = fuid.normalizar(celdas, lote.mapeo)
        if vigentes is not None and normalizado.get("codigo_serie") and normalizado["codigo_serie"] not in vigentes:
            avisos.append(f"el código «{normalizado['codigo_serie']}» no está en la TRD/TVD vigente del proyecto")
        clave = normalizado["clave"]
        if clave:
            if clave in existentes:
                errores.append(f"el identificador «{normalizado['identificador']}» ya existe en el proyecto")
            elif clave in vistas:
                errores.append(f"el identificador «{normalizado['identificador']}» está repetido (fila {vistas[clave]})")
            else:
                vistas[clave] = numero
        ctx.db.add(FilaInventario(tenant_id=lote.tenant_id, lote_id=lote.id, numero_fila=numero, original=celdas, normalizado=normalizado, errores=errores, avisos=avisos))
        if errores:
            con_error += 1
        else:
            validas += 1
    lote.total_filas, lote.filas_validas, lote.filas_con_error = len(hoja.filas), validas, con_error
    lote.estado = EstadoLote.CON_ERRORES.value if con_error else EstadoLote.VALIDADO.value


def importar(ctx, proyecto: Proyecto, contenido: bytes, nombre: str) -> LoteInventario:
    _exigir_abierto(proyecto)
    hoja = fuid.leer(contenido, nombre, ajustes().max_filas_fuid)
    archivo = guardar_archivo(ctx, proyecto, contenido, nombre, {"XLSX", "CSV"})
    lote = LoteInventario(
        tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, archivo_id=archivo.id, nombre_archivo=nombre[:500], hoja=hoja.nombre_hoja,
        fila_encabezado=hoja.fila_encabezado, encabezados=hoja.encabezados, mapeo=hoja.mapeo, estado=EstadoLote.VALIDADO.value, creado_por=ctx.usuario.id,
    )
    ctx.db.add(lote)
    ctx.db.flush()
    try:
        fuid.validar_mapeo(dict(hoja.mapeo), len(hoja.encabezados))
        _validar_filas(ctx, lote, hoja)
    except DatosInvalidos as e:
        # El encabezado se encontró pero falta algún campo obligatorio: el lote queda para mapear a mano.
        lote.estado, lote.motivo_estado = EstadoLote.CON_ERRORES.value, e.mensaje
    ctx.auditar(accion="IMPORTAR_FUID", objeto="LoteInventario", objeto_id=lote.id,
                detalle=f"{proyecto.codigo} · {nombre} · {lote.total_filas} filas, {lote.filas_con_error} con errores · SHA-256 {archivo.sha256[:16]}…")
    ctx.db.commit()
    return lote


def obtener_lote(ctx, proyecto: Proyecto, lote_id: uuid.UUID) -> LoteInventario:
    lote = ctx.db.get(LoteInventario, lote_id)
    if lote is None or lote.proyecto_id != proyecto.id or lote.tenant_id != ctx.tenant_id:
        raise NoEncontrado("El lote no existe")
    return lote


def remapear(ctx, proyecto: Proyecto, lote: LoteInventario, mapeo: dict[str, int]) -> LoteInventario:
    _exigir_abierto(proyecto)
    if lote.estado in (EstadoLote.INTEGRADO.value, EstadoLote.DESCARTADO.value):
        raise TransicionInvalida("El lote ya se integró o se descartó")
    fuid.validar_mapeo(mapeo, len(lote.encabezados))
    archivo = ctx.db.get(ArchivoDigital, lote.archivo_id)
    hoja = fuid.leer(almacen.leer(archivo.clave_almacen, ctx.tenant_id), lote.nombre_archivo, ajustes().max_filas_fuid)
    anterior = lote.mapeo
    lote.mapeo, lote.motivo_estado, lote.actualizado_por = mapeo, None, ctx.usuario.id
    _validar_filas(ctx, lote, hoja)
    ctx.auditar(accion="MAPEAR_FUID", objeto="LoteInventario", objeto_id=lote.id, cambios={"mapeo": [anterior, mapeo]},
                detalle=f"{lote.filas_validas} válidas, {lote.filas_con_error} con errores")
    ctx.db.commit()
    return lote


def filas(ctx, lote: LoteInventario, solo_errores: bool = False, limite: int = 200, desde: int = 0) -> list[FilaInventario]:
    consulta = select(FilaInventario).where(FilaInventario.lote_id == lote.id)
    if solo_errores:
        consulta = consulta.where(func.json_array_length(FilaInventario.errores) > 0) if ctx.db.bind.dialect.name == "sqlite" else consulta.where(func.jsonb_array_length(FilaInventario.errores) > 0)
    return list(ctx.db.scalars(consulta.where(FilaInventario.numero_fila > desde).order_by(FilaInventario.numero_fila).limit(limite)))


def integrar(ctx, proyecto: Proyecto, lote: LoteInventario, motivo: str | None) -> LoteInventario:
    _exigir_abierto(proyecto)
    if lote.estado not in (EstadoLote.VALIDADO.value, EstadoLote.CON_ERRORES.value):
        raise TransicionInvalida("El lote ya se integró o se descartó")
    if lote.motivo_estado and not lote.total_filas:
        raise TransicionInvalida("Primero asigne las columnas obligatorias")
    if lote.filas_con_error and not (motivo and len(motivo.strip()) >= 5):
        raise DatosInvalidos(f"Hay {lote.filas_con_error} filas con errores que no se integrarán: escriba el motivo para continuar")
    existentes = set(ctx.db.scalars(select(UnidadDocumental.clave).where(UnidadDocumental.proyecto_id == proyecto.id)))
    integradas = 0
    for fila in ctx.db.scalars(select(FilaInventario).where(FilaInventario.lote_id == lote.id).order_by(FilaInventario.numero_fila)):
        if fila.errores:
            continue
        n = fila.normalizado
        if n["clave"] in existentes:  # alguien integró otro lote mientras tanto
            fila.errores = [*fila.errores, "el identificador ya existe en el proyecto"]
            continue
        unidad = UnidadDocumental(
            tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, lote_id=lote.id, identificador=n["identificador"], clave=n["clave"],
            numero_orden=n["numero_orden"], codigo_serie=n["codigo_serie"], nombre=n["nombre"],
            fecha_inicial=date.fromisoformat(n["fecha_inicial"]) if n["fecha_inicial"] else None,
            fecha_final=date.fromisoformat(n["fecha_final"]) if n["fecha_final"] else None,
            caja=n["caja"], carpeta=n["carpeta"], tomo=n["tomo"], otro=n["otro"], folios=n["folios"], soporte=n["soporte"],
            frecuencia_consulta=n["frecuencia_consulta"], notas=n["notas"], creado_por=ctx.usuario.id,
        )
        ctx.db.add(unidad)
        ctx.db.flush()
        fila.unidad_id = unidad.id
        existentes.add(n["clave"])
        integradas += 1
    lote.filas_integradas = integradas
    lote.filas_con_error = lote.total_filas - integradas
    lote.estado, lote.motivo_estado, lote.actualizado_por = EstadoLote.INTEGRADO.value, motivo, ctx.usuario.id
    ctx.auditar(accion="INTEGRAR_FUID", objeto="LoteInventario", objeto_id=lote.id, motivo=motivo,
                detalle=f"{proyecto.codigo} · {integradas} unidades integradas · {lote.total_filas - integradas} filas rechazadas")
    ctx.db.commit()
    return lote


def descartar(ctx, proyecto: Proyecto, lote: LoteInventario, motivo: str) -> LoteInventario:
    if lote.estado in (EstadoLote.INTEGRADO.value, EstadoLote.DESCARTADO.value):
        raise TransicionInvalida("El lote ya se integró o se descartó")
    lote.estado, lote.motivo_estado, lote.actualizado_por = EstadoLote.DESCARTADO.value, motivo, ctx.usuario.id
    ctx.auditar(accion="DESCARTAR_FUID", objeto="LoteInventario", objeto_id=lote.id, motivo=motivo)
    ctx.db.commit()
    return lote


def lotes(ctx, proyecto: Proyecto) -> list[LoteInventario]:
    return list(ctx.db.scalars(select(LoteInventario).where(LoteInventario.proyecto_id == proyecto.id).order_by(LoteInventario.creado_en.desc())))


def unidades(ctx, proyecto: Proyecto, texto: str | None = None, limite: int = 200, desplazamiento: int = 0) -> tuple[int, list[UnidadDocumental]]:
    consulta = select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)
    if texto:
        patron = f"%{texto.strip()}%"
        consulta = consulta.where(UnidadDocumental.identificador.ilike(patron) | UnidadDocumental.nombre.ilike(patron) | (UnidadDocumental.clave == fuid.clave_de(texto)))
    total = ctx.db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    return total, list(ctx.db.scalars(consulta.order_by(UnidadDocumental.creado_en, UnidadDocumental.identificador).offset(desplazamiento).limit(limite)))


def resumen_fila(f: FilaInventario) -> dict[str, Any]:
    return {"numero_fila": f.numero_fila, "original": f.original, "normalizado": f.normalizado, "errores": f.errores, "avisos": f.avisos, "unidad_id": f.unidad_id}
