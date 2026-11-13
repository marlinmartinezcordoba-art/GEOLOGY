"""M10 Recepción de lo digitalizado y M11 control de calidad.

Flujo: cargar una carpeta (o archivos sueltos) → identificar la unidad de cada archivo → descartar duplicados
por huella → medir la ficha técnica → evaluar contra el perfil del proyecto → aprobar, rechazar o enviar a
revisión → una persona decide lo dudoso, pide recaptura o asigna lo que no se reconoció.

Reglas:
- El original se guarda tal cual llega y no se modifica (Maestro ARC-10; Instrucciones M12).
- Nada se reordena ni se elimina por inferencia: la página o la parte que falta se señala, no se inventa.
- Una recaptura no borra la anterior: la deja «reemplazada» como evidencia.
"""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select

from arca.modelos import ArchivoDigital, EstadoProyecto, EstadoRecurso, Proyecto, RecursoDigital, UnidadDocumental
from arca.modelos.base import ahora_utc
from arca.modulos.flujo.cola import encolar_ctx
from arca.modulos.m03_configuracion.servicios import parametro_vigente
from arca.modulos.m08_inventarios.servicios import guardar_archivo
from arca.modulos.m10_digitalizacion import calidad, identificacion, perfil
from arca.nucleo import almacen
from arca.nucleo.errores import Conflicto, DatosInvalidos, NoEncontrado, TransicionInvalida

ACTIVOS = (EstadoRecurso.APROBADO.value, EstadoRecurso.EN_REVISION.value, EstadoRecurso.RECHAZADO.value, EstadoRecurso.SIN_IDENTIFICAR.value)


def perfil_de(ctx, proyecto: Proyecto) -> tuple[dict[str, Any], int | None]:
    p = parametro_vigente(ctx.db, ctx.tenant_id, perfil.CLAVE, proyecto.id)
    return perfil.vigente(p.valor if p else None), (p.version if p else None)


class _Indice:
    """Las unidades del proyecto, indexadas por clave exacta y por número final (cuando el prefijo difiere)."""

    def __init__(self, unidades: list[UnidadDocumental]):
        self.por_clave = {u.clave: u for u in unidades}
        por_numero: dict[int, list[UnidadDocumental]] = defaultdict(list)
        for u in unidades:
            if (n := identificacion.numero_final(u.clave)) is not None:
                por_numero[n].append(u)
        self.por_numero = por_numero

    def buscar(self, candidato: identificacion.Candidato) -> tuple[UnidadDocumental | None, int]:
        for clave, parte in candidato.opciones:
            if clave in self.por_clave:
                return self.por_clave[clave], parte
        for clave, parte in candidato.opciones:
            n = identificacion.numero_final(clave)
            if n is not None and len(self.por_numero.get(n, [])) == 1:
                return self.por_numero[n][0], parte
        return None, 0


def _exigir_abierto(proyecto: Proyecto) -> None:
    if proyecto.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def recibir(ctx, proyecto: Proyecto, archivos: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    """Recibe un lote de archivos con su ruta relativa dentro de la carpeta cargada. Devuelve un reporte por archivo."""
    _exigir_abierto(proyecto)
    if not archivos:
        raise DatosInvalidos("No llegó ningún archivo")
    reglas, version = perfil_de(ctx, proyecto)
    indice = _Indice(list(ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id))))
    huellas_previas = set(
        ctx.db.scalars(
            select(ArchivoDigital.sha256).join(RecursoDigital, RecursoDigital.archivo_id == ArchivoDigital.id).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.estado.in_(ACTIVOS))
        )
    )
    reporte: list[dict[str, Any]] = []
    for ruta, contenido in archivos:
        ruta = ruta.replace("\\", "/")[:1000]
        candidato = identificacion.analizar(ruta, reglas["identificar_por"])
        if candidato is None:
            reporte.append({"ruta": ruta, "resultado": "ignorado", "detalle": "No es un PDF ni una imagen"})
            continue
        if candidato.modalidad == "pdf" and "pdf" not in reglas["modalidades"] or candidato.modalidad == "imagen" and "imagenes" not in reglas["modalidades"]:
            reporte.append({"ruta": ruta, "resultado": "ignorado", "detalle": "El perfil del proyecto no admite esta forma de entrega"})
            continue
        huella = almacen.huella(contenido)
        if huella in huellas_previas:
            reporte.append({"ruta": ruta, "resultado": "duplicado", "detalle": "Este mismo archivo ya se había recibido en el proyecto"})
            continue
        ident = almacen.identificar(contenido, ruta)
        if ident is None or ident.formato not in perfil.FORMATOS:
            reporte.append({"ruta": ruta, "resultado": "rechazado", "detalle": "El contenido no corresponde a un PDF o imagen válido"})
            continue
        archivo = guardar_archivo(ctx, proyecto, contenido, ruta.rsplit("/", 1)[-1], set(perfil.FORMATOS))
        huellas_previas.add(huella)
        ficha = calidad.ficha_pdf(contenido) if ident.formato == "PDF" else calidad.ficha_imagen(contenido, float(reglas["umbral_blanco"]))
        hallazgos = calidad.evaluar(ficha, ident.formato, reglas)
        unidad, parte = indice.buscar(candidato)
        estado = calidad.decidir(hallazgos, reglas) if unidad else EstadoRecurso.SIN_IDENTIFICAR.value
        recurso = RecursoDigital(
            tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=unidad.id if unidad else None, archivo_id=archivo.id, ruta_original=ruta,
            modalidad=candidato.modalidad, parte=parte, pagina=candidato.pagina, paginas=int(ficha.get("paginas") or 0), ficha=ficha,
            hallazgos=hallazgos, estado=estado, perfil_version=version, creado_en=ahora_utc(), creado_por=ctx.usuario.id,
        )
        # Una recaptura pedida para esta misma unidad y posición queda reemplazada por lo que acaba de llegar.
        if unidad:
            previa = ctx.db.scalar(
                select(RecursoDigital).where(
                    RecursoDigital.unidad_id == unidad.id, RecursoDigital.estado == EstadoRecurso.RECAPTURA.value, RecursoDigital.modalidad == candidato.modalidad,
                    RecursoDigital.parte == parte, (RecursoDigital.pagina == candidato.pagina) if candidato.pagina is not None else RecursoDigital.pagina.is_(None),
                )
            )
            if previa:
                previa.estado = EstadoRecurso.REEMPLAZADO.value
                recurso.reemplaza_id = previa.id
        ctx.db.add(recurso)
        ctx.db.flush()
        reporte.append({"ruta": ruta, "resultado": "recibido", "recurso_id": str(recurso.id), "unidad": unidad.identificador if unidad else None, "estado": estado,
                        "hallazgos": [h["mensaje"] for h in hallazgos]})
    recibidos = sum(1 for r in reporte if r["resultado"] == "recibido")
    ids = [uuid.UUID(r["recurso_id"]) for r in reporte if r.get("recurso_id")]
    for uid in {x.unidad_id for x in ctx.db.scalars(select(RecursoDigital).where(RecursoDigital.id.in_(ids)))} - {None} if ids else set():
        encolar_ctx(ctx, proyecto.id, uid, "carga de archivos")
    ctx.auditar(accion="RECIBIR_DIGITALIZACION", objeto="Proyecto", objeto_id=proyecto.id,
                detalle=f"{proyecto.codigo} · {recibidos} recibidos de {len(reporte)} · perfil v{version or 'por defecto'}")
    ctx.db.commit()
    return reporte


def completitud(unidad: UnidadDocumental, recursos: list[RecursoDigital], reglas: dict[str, Any]) -> list[dict[str, Any]]:
    """Alertas del expediente completo: partes o páginas que faltan e imágenes contra folios del FUID.

    Se calculan sobre la unidad, no sobre cada archivo, porque una carpeta puede llegar en varias cargas:
    lo que hoy falta puede llegar mañana. Señala; nunca reordena ni completa.
    """
    activos = [r for r in recursos if r.estado in ACTIVOS]
    alertas: list[dict[str, Any]] = []
    if faltan := identificacion.saltos([r.parte for r in activos if r.modalidad == "pdf" and r.parte]):
        alertas.append(calidad.hallazgo("salto_secuencia", "revisar", f"faltan las partes {', '.join(map(str, faltan))}"))
    if faltan := identificacion.saltos([r.pagina for r in activos if r.modalidad == "imagen" and r.pagina is not None]):
        muestra = ", ".join(map(str, faltan[:10])) + ("…" if len(faltan) > 10 else "")
        alertas.append(calidad.hallazgo("salto_secuencia", "revisar", f"faltan las páginas {muestra}"))
    total = sum(r.paginas for r in activos)
    if reglas["comparar_folios"] and unidad.folios and total and total not in (unidad.folios, unidad.folios * 2):
        alertas.append(calidad.hallazgo("folios_no_coinciden", "revisar", f"{total} imágenes y {unidad.folios} folios en el FUID"))
    return alertas


def estado_unidad(recursos: list[RecursoDigital]) -> str:
    estados = {r.estado for r in recursos if r.estado != EstadoRecurso.REEMPLAZADO.value}
    if not estados:
        return "sin_imagenes"
    if estados & {EstadoRecurso.RECHAZADO.value, EstadoRecurso.RECAPTURA.value}:
        return "recaptura"
    if EstadoRecurso.EN_REVISION.value in estados:
        return "en_revision"
    return "aprobada"


def unidades(ctx, proyecto: Proyecto, filtro: str | None, limite: int, desplazamiento: int) -> tuple[int, list[dict[str, Any]]]:
    """Expedientes del inventario con el avance de su digitalización y sus alertas de completitud."""
    reglas, _ = perfil_de(ctx, proyecto)
    todas = list(ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id).order_by(UnidadDocumental.creado_en, UnidadDocumental.identificador)))
    por_unidad: dict[uuid.UUID, list[RecursoDigital]] = defaultdict(list)
    for r in ctx.db.scalars(select(RecursoDigital).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None))):
        por_unidad[r.unidad_id].append(r)
    filas = []
    for u in todas:
        recursos = por_unidad.get(u.id, [])
        activos = [r for r in recursos if r.estado in ACTIVOS]
        estado = estado_unidad(recursos)
        alertas = completitud(u, recursos, reglas) if activos else []
        fila = {"id": u.id, "identificador": u.identificador, "nombre": u.nombre, "folios": u.folios, "caja": u.caja, "carpeta": u.carpeta,
                "archivos": len(activos), "imagenes": sum(r.paginas for r in activos), "estado": estado, "alertas": alertas}
        if filtro is None or filtro == estado or (filtro == "con_alertas" and alertas):
            filas.append(fila)
    return len(filas), filas[desplazamiento : desplazamiento + limite]


def obtener(ctx, proyecto: Proyecto, recurso_id: uuid.UUID) -> RecursoDigital:
    r = ctx.db.get(RecursoDigital, recurso_id)
    if r is None or r.proyecto_id != proyecto.id or r.tenant_id != ctx.tenant_id:
        raise NoEncontrado("El archivo no existe")
    return r


def decidir(ctx, proyecto: Proyecto, recurso: RecursoDigital, decision: str, motivo: str) -> RecursoDigital:
    _exigir_abierto(proyecto)
    if recurso.estado in (EstadoRecurso.REEMPLAZADO.value, EstadoRecurso.SIN_IDENTIFICAR.value):
        raise TransicionInvalida("Primero asígnelo a una unidad del inventario" if recurso.estado == EstadoRecurso.SIN_IDENTIFICAR.value else "Este archivo ya fue reemplazado por una recaptura")
    destino = {"aprobar": EstadoRecurso.APROBADO.value, "recaptura": EstadoRecurso.RECAPTURA.value}.get(decision)
    if destino is None:
        raise DatosInvalidos("La decisión es «aprobar» o «recaptura»")
    if destino == EstadoRecurso.APROBADO.value and any(h["codigo"] == "ilegible" for h in recurso.hallazgos):
        raise Conflicto("Un archivo ilegible no se puede aprobar: pida la recaptura")
    if recurso.creado_por == ctx.usuario.id and destino == EstadoRecurso.APROBADO.value and recurso.hallazgos:
        raise Conflicto("Quien cargó el archivo no aprueba sus propias alertas de calidad (segregación de funciones)")
    anterior = recurso.estado
    recurso.estado, recurso.decidido_por, recurso.motivo_decision = destino, ctx.usuario.id, motivo
    ctx.auditar(accion="APROBAR_CALIDAD" if destino == EstadoRecurso.APROBADO.value else "PEDIR_RECAPTURA", objeto="RecursoDigital", objeto_id=recurso.id,
                motivo=motivo, cambios={"estado": [anterior, destino]}, detalle=recurso.ruta_original)
    encolar_ctx(ctx, proyecto.id, recurso.unidad_id, "decisión de calidad")
    ctx.db.commit()
    return recurso


def asignar(ctx, proyecto: Proyecto, recurso: RecursoDigital, unidad_id: uuid.UUID, parte: int, pagina: int | None, motivo: str) -> RecursoDigital:
    _exigir_abierto(proyecto)
    if recurso.estado != EstadoRecurso.SIN_IDENTIFICAR.value:
        raise TransicionInvalida("Solo se asignan los archivos sin identificar")
    unidad = ctx.db.get(UnidadDocumental, unidad_id)
    if unidad is None or unidad.proyecto_id != proyecto.id:
        raise NoEncontrado("La unidad no existe en este proyecto")
    reglas, _ = perfil_de(ctx, proyecto)
    recurso.unidad_id, recurso.parte, recurso.pagina = unidad.id, parte, pagina
    recurso.estado = calidad.decidir(recurso.hallazgos, reglas)
    recurso.decidido_por, recurso.motivo_decision = ctx.usuario.id, motivo
    ctx.db.flush()
    ctx.auditar(accion="ASIGNAR_ARCHIVO", objeto="RecursoDigital", objeto_id=recurso.id, motivo=motivo, detalle=f"{recurso.ruta_original} → {unidad.identificador}")
    encolar_ctx(ctx, proyecto.id, recurso.unidad_id, "archivo asignado")
    ctx.db.commit()
    return recurso


def listar(ctx, proyecto: Proyecto, estado: str | None, unidad_id: uuid.UUID | None, limite: int, desplazamiento: int) -> tuple[int, list[RecursoDigital]]:
    consulta = select(RecursoDigital).where(RecursoDigital.proyecto_id == proyecto.id)
    if estado:
        consulta = consulta.where(RecursoDigital.estado == estado)
    if unidad_id:
        consulta = consulta.where(RecursoDigital.unidad_id == unidad_id)
    total = ctx.db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = ctx.db.scalars(consulta.order_by(RecursoDigital.creado_en.desc(), RecursoDigital.ruta_original).offset(desplazamiento).limit(limite))
    return total, list(filas)


def resumen(ctx, proyecto: Proyecto) -> dict[str, Any]:
    """Avance de la digitalización: archivos por estado y unidades con y sin imágenes."""
    por_estado = dict(ctx.db.execute(select(RecursoDigital.estado, func.count()).where(RecursoDigital.proyecto_id == proyecto.id).group_by(RecursoDigital.estado)).all())
    unidades = ctx.db.scalar(select(func.count()).select_from(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)) or 0
    con_imagenes = ctx.db.scalar(
        select(func.count(func.distinct(RecursoDigital.unidad_id))).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None), RecursoDigital.estado.in_(ACTIVOS))
    ) or 0
    pendientes = ctx.db.scalar(
        select(func.count(func.distinct(RecursoDigital.unidad_id))).where(
            RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.estado.in_((EstadoRecurso.EN_REVISION.value, EstadoRecurso.RECHAZADO.value, EstadoRecurso.RECAPTURA.value))
        )
    ) or 0
    paginas = ctx.db.scalar(
        select(func.coalesce(func.sum(RecursoDigital.paginas), 0)).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None), RecursoDigital.estado.in_(ACTIVOS))
    ) or 0
    return {"por_estado": por_estado, "unidades": unidades, "unidades_con_imagenes": con_imagenes, "unidades_con_pendientes": pendientes,
            "unidades_aprobadas": max(0, con_imagenes - pendientes), "imagenes": paginas}


def contenido(ctx, recurso: RecursoDigital) -> tuple[bytes, ArchivoDigital]:
    archivo = ctx.db.get(ArchivoDigital, recurso.archivo_id)
    datos = almacen.leer(archivo.clave_almacen, ctx.tenant_id)
    if almacen.huella(datos) != archivo.sha256:
        raise Conflicto("ALERTA DE INTEGRIDAD: el archivo del repositorio no coincide con su huella. Avise al administrador.")
    return datos, archivo
