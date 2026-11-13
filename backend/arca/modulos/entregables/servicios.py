"""Plantillas versionadas y expedición de FUID de salida, rótulos de caja y rótulos de carpeta (D-27).

Reglas:
- La plantilla la entrega la entidad. Solo se aceptan marcadores conocidos: si el formato pide un dato que
  ARCA no tiene, se dice cuál, en vez de dejar la casilla vacía en silencio.
- Una versión no se edita: se publica otra. La vigencia no es pasada. Publicar una vigente desde ahora
  reemplaza a la anterior, que queda como evidencia.
- Al expedir se usa la versión vigente (la del proyecto, y si no hay, la de la organización), y el documento
  queda guardado con su huella y con la versión con que se hizo.
"""

import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from arca.modelos import (
    ArchivoDigital,
    CajaProyecto,
    ClasificacionUnidad,
    ElementoInstrumento,
    EstadoRecurso,
    Expedicion,
    Plantilla,
    Proyecto,
    RecursoDigital,
    UnidadDocumental,
    VersionPlantilla,
)
from arca.modelos.base import ahora_utc, en_utc
from arca.modulos.entregables import motor
from arca.modulos.m08_inventarios.fuid import clave_de
from arca.modulos.m08_inventarios.servicios import guardar_archivo
from arca.nucleo import almacen
from arca.nucleo.errores import DatosInvalidos, NoEncontrado, TransicionInvalida

COMUNES = {
    "entidad": "Razón social de la organización que ejecuta", "nit": "NIT de la organización", "proyecto": "Nombre del proyecto",
    "codigo_proyecto": "Código del proyecto", "entidad_cliente": "Entidad para la que se ejecuta", "contrato": "Número de contrato",
    "fecha": "Fecha de expedición", "codigo_formato": "Código del formato (de la versión de la plantilla)", "version_formato": "Versión de la plantilla",
}
UNIDAD = {
    "numero_orden": "Número de orden", "identificador": "Identificador de la unidad", "codigo_serie": "Código de la serie o subserie",
    "nombre": "Nombre de la serie, subserie o asunto", "fecha_inicial": "Fecha inicial", "fecha_final": "Fecha final", "caja": "Caja",
    "carpeta": "Carpeta", "tomo": "Tomo", "otro": "Otro", "folios": "Número de folios", "soporte": "Soporte", "frecuencia_consulta": "Frecuencia de consulta",
    "notas": "Notas", "imagenes": "Imágenes digitalizadas", "estado_digitalizacion": "Estado de la digitalización",
    "codigo_clasificacion": "Código según la TRD o TVD (clasificación)", "serie": "Serie (según la clasificación)",
    "subserie": "Subserie (según la clasificación)", "dependencia": "Código de la dependencia (según la clasificación)",
    "fase": "Fase del ciclo vital (archivo de gestión, central o histórico)",
    "folios_inventario": "Folios que declaraba el inventario de origen", "origen_folios": "De dónde salen los folios (hoja de control verificada o inventario)",
}
TIPOS: dict[str, dict[str, Any]] = {
    "fuid": {
        "nombre": "FUID de salida (inventario documental)",
        "encabezado": {**COMUNES, "total_unidades": "Total de unidades", "total_folios": "Total de folios", "total_imagenes": "Total de imágenes",
                       "objeto": "Objeto del inventario (transferencia primaria, secundaria, inventario individual…)", "numero_transferencia": "Número de la transferencia",
                       "oficina_productora": "Oficina productora (en una transferencia)", "codigo_oficina": "Código de la oficina productora", "fecha_corte": "Fecha de corte de la transferencia"},
        "fila": UNIDAD,
    },
    "rotulo_caja": {
        "nombre": "Rótulo de caja",
        "encabezado": {**COMUNES, "caja": "Número de la caja", "frente": "Frente", "lote": "Lote", "sede": "Sede", "ubicacion": "Ubicación",
                       "carpetas": "Carpetas en la caja", "primer_identificador": "Primera unidad", "ultimo_identificador": "Última unidad",
                       "fecha_inicial": "Fecha inicial más antigua", "fecha_final": "Fecha final más reciente", "series": "Series de la caja", "folios": "Folios de la caja"},
        "fila": UNIDAD,
    },
    "acta_eliminacion": {
        "nombre": "Acta de eliminación documental",
        "encabezado": {**COMUNES, "numero_acta": "Número del acta de eliminación", "numero_proceso": "Número del proceso de disposición",
                       "acta_comite": "Acta del comité que aprobó la eliminación", "fecha_comite": "Fecha del acta del comité",
                       "publicacion_inicio": "Inicio de la publicación del inventario", "publicacion_fin": "Fin del plazo de publicación",
                       "publicacion_enlace": "Dónde se publicó el inventario", "metodo": "Método de eliminación", "fecha_ejecucion": "Fecha de la eliminación",
                       "series": "Series y subseries eliminadas", "dependencias": "Dependencias", "fecha_inicial": "Fecha inicial más antigua",
                       "fecha_final": "Fecha final más reciente", "total_unidades": "Total de unidades", "total_folios": "Total de folios", "total_cajas": "Total de cajas"},
        "fila": UNIDAD,
    },
    "hoja_control": {
        "nombre": "Hoja de control del expediente",
        "encabezado": {**COMUNES, **{k: v for k, v in UNIDAD.items() if k not in ("imagenes", "estado_digitalizacion")},
                       "oficina_productora": "Oficina productora (dependencia de la clasificación)", "total_folios": "Total de folios contados en la hoja",
                       "total_documentos": "Número de documentos (trámites)", "elaboro": "Quién la elaboró", "verifico": "Quién la verificó",
                       "fecha_verificacion": "Fecha de verificación", "diferencia_folios": "Constancia si los folios no coinciden con el FUID"},
        "fila": {"orden": "Número del trámite", "fecha": "Fecha del documento (o S. F.)", "tipo_documental": "Tipo documental", "detalle": "Detalle o asunto",
                 "folio_desde": "Folio inicial", "folio_hasta": "Folio final", "folios": "Número de folios", "no_radicado": "Número de radicado",
                 "observaciones": "Observaciones", "asunto": "Asunto", "remitente": "Remitente", "destinatario": "Destinatario", "firmantes": "Firmantes",
                 "lugar": "Lugar", "numero": "Número del documento"},
    },
    "descripcion_isadg": {
        "nombre": "Base de descripción ISAD(G)",
        "encabezado": {**COMUNES, "total_unidades": "Unidades descritas"},
        "fila": {"codigo_referencia": "3.1.1 Código de referencia", "titulo": "3.1.2 Título", "fecha_inicial": "3.1.3 Fecha inicial", "fecha_final": "3.1.3 Fecha final",
                 "nivel": "3.1.4 Nivel de descripción", "volumen": "3.1.5 Volumen y soporte", "productor": "3.2.1 Nombre del productor",
                 "historia_archivistica": "3.2.3 Historia archivística", "forma_ingreso": "3.2.4 Forma de ingreso", "alcance": "3.3.1 Alcance y contenido",
                 "valoracion": "3.3.2 Valoración, selección y eliminación", "organizacion": "3.3.4 Organización", "acceso": "3.4.1 Condiciones de acceso",
                 "lengua": "3.4.3 Lengua", "instrumentos": "3.4.5 Instrumentos de descripción", "copias": "3.5.2 Copias", "notas": "3.6.1 Notas",
                 "nota_archivero": "3.7.1 Nota del archivero", "reglas": "3.7.2 Reglas o normas", "fecha_descripcion": "3.7.3 Fecha de la descripción",
                 "identificador": "Identificador de la unidad", "caja": "Caja", "carpeta": "Carpeta"},
    },
    "rotulo_carpeta": {
        "nombre": "Rótulo de carpeta",
        "encabezado": {**COMUNES, **UNIDAD},
        "fila": {},
    },
}


def tipo_o_error(tipo: str) -> dict[str, Any]:
    if tipo not in TIPOS:
        raise DatosInvalidos(f"Tipo de plantilla desconocido: {tipo}. Use {', '.join(TIPOS)}")
    return TIPOS[tipo]


def plantilla_base(tipo: str) -> bytes:
    """Formato de partida, sin datos, para que la entidad lo ajuste a su imagen institucional."""
    t = tipo_o_error(tipo)
    if tipo == "fuid":
        return motor.plantilla_base(
            "FORMATO ÚNICO DE INVENTARIO DOCUMENTAL",
            [("Entidad remitente", "entidad_cliente"), ("Entidad productora", "entidad"), ("Oficina productora", "oficina_productora"), ("Objeto", "objeto"),
             ("N.º de transferencia", "numero_transferencia"), ("Proyecto", "proyecto"), ("Fecha", "fecha"), ("Código del formato", "codigo_formato")],
            [(t["fila"][c], c) for c in ("numero_orden", "identificador", "codigo_serie", "codigo_clasificacion", "nombre", "fecha_inicial", "fecha_final", "caja", "carpeta", "tomo", "otro", "folios", "soporte", "frecuencia_consulta", "notas")],
            ["Total de unidades: {{total_unidades}} · Total de folios: {{total_folios}}", "", "Elaboró: ______________________        Recibió: ______________________"],
        )
    if tipo == "acta_eliminacion":
        return motor.plantilla_base(
            "ACTA DE ELIMINACIÓN DOCUMENTAL",
            [("Acta n.º", "numero_acta"), ("Entidad", "entidad_cliente"), ("Dependencias", "dependencias"), ("Aprobada por el comité en el acta", "acta_comite"),
             ("Fecha del acta del comité", "fecha_comite"), ("Inventario publicado desde", "publicacion_inicio"), ("Hasta", "publicacion_fin"),
             ("Publicado en", "publicacion_enlace"), ("Método de eliminación", "metodo"), ("Fecha de la eliminación", "fecha_ejecucion"), ("Series y subseries", "series")],
            [(t["fila"][c], c) for c in ("numero_orden", "identificador", "codigo_clasificacion", "nombre", "fecha_inicial", "fecha_final", "caja", "carpeta", "folios", "soporte")],
            ["Total de unidades: {{total_unidades}} · Total de folios: {{total_folios}} · Total de cajas: {{total_cajas}}", "",
             "Elaboró: ______________________        Revisó: ______________________        Aprobó: ______________________"],
        )
    if tipo == "hoja_control":
        return motor.plantilla_base(
            "HOJA DE CONTROL",
            [("Entidad", "entidad_cliente"), ("Oficina productora", "oficina_productora"), ("Serie", "serie"), ("Subserie", "subserie"),
             ("Código", "codigo_clasificacion"), ("Expediente", "nombre"), ("Identificador", "identificador"), ("Fechas extremas", "fecha_inicial"),
             ("Hasta", "fecha_final"), ("Caja", "caja"), ("Carpeta", "carpeta")],
            [("N.º", "orden"), ("Fecha", "fecha"), ("Tipo documental", "tipo_documental"), ("Detalle", "detalle"), ("Folio desde", "folio_desde"),
             ("Folio hasta", "folio_hasta"), ("Folios", "folios"), ("Radicado", "no_radicado"), ("Observaciones", "observaciones")],
            ["Total de folios: {{total_folios}} · Documentos: {{total_documentos}}", "{{diferencia_folios}}", "",
             "Elaboró: {{elaboro}}        Verificó: {{verifico}} ({{fecha_verificacion}})"],
        )
    if tipo == "descripcion_isadg":
        return motor.plantilla_base(
            "BASE DE DESCRIPCIÓN ISAD(G) · NTC 4095",
            [("Entidad", "entidad_cliente"), ("Proyecto", "proyecto"), ("Unidades descritas", "total_unidades"), ("Fecha", "fecha")],
            [(t["fila"][c], c) for c in ("codigo_referencia", "titulo", "fecha_inicial", "fecha_final", "nivel", "volumen", "productor", "historia_archivistica",
                                         "forma_ingreso", "alcance", "valoracion", "organizacion", "acceso", "lengua", "instrumentos", "copias", "notas",
                                         "nota_archivero", "reglas", "fecha_descripcion")],
            ["Código del formato: {{codigo_formato}}"],
        )
    if tipo == "rotulo_caja":
        return motor.plantilla_base(
            "RÓTULO DE CAJA",
            [("Entidad", "entidad_cliente"), ("Caja", "caja"), ("Carpetas", "carpetas"), ("Fechas extremas", "fecha_inicial"), ("Hasta", "fecha_final"), ("Series", "series")],
            [("Orden", "numero_orden"), ("Identificador", "identificador"), ("Asunto", "nombre"), ("Folios", "folios")],
            ["Código del formato: {{codigo_formato}}"],
        )
    return motor.plantilla_base(
        "RÓTULO DE CARPETA",
        [("Entidad", "entidad_cliente"), ("Serie", "serie"), ("Subserie", "subserie"), ("Código", "codigo_clasificacion"), ("Asunto", "nombre"), ("Fechas extremas", "fecha_inicial"), ("Hasta", "fecha_final"),
         ("Folios", "folios"), ("Caja", "caja"), ("Carpeta", "carpeta"), ("Identificador", "identificador")],
        [],
        ["Código del formato: {{codigo_formato}}"],
    )


# --- Plantillas y versiones ------------------------------------------------------------------


def _proyecto_del_tenant(ctx, proyecto_id: uuid.UUID | None) -> None:
    if proyecto_id is None:
        return
    p = ctx.db.get(Proyecto, proyecto_id)
    if p is None or p.tenant_id != ctx.tenant_id:
        raise NoEncontrado("El proyecto no existe")


def obtener(ctx, plantilla_id: uuid.UUID) -> Plantilla:
    p = ctx.db.get(Plantilla, plantilla_id)
    if p is None or p.tenant_id != ctx.tenant_id:
        raise NoEncontrado("La plantilla no existe")
    return p


def listar(ctx, proyecto_id: uuid.UUID | None = None) -> list[Plantilla]:
    filtro = or_(Plantilla.proyecto_id.is_(None), Plantilla.proyecto_id == proyecto_id) if proyecto_id else Plantilla.proyecto_id.is_(None)
    return list(ctx.db.scalars(select(Plantilla).where(Plantilla.tenant_id == ctx.tenant_id, filtro).order_by(Plantilla.tipo, Plantilla.nombre)))


def versiones(ctx, plantilla: Plantilla) -> list[VersionPlantilla]:
    _actualizar_estados(ctx, plantilla)
    return list(ctx.db.scalars(select(VersionPlantilla).where(VersionPlantilla.plantilla_id == plantilla.id).order_by(VersionPlantilla.version)))


def _validar_archivo(tipo: str, contenido: bytes) -> list[str]:
    t = tipo_o_error(tipo)
    encabezado, fila = motor.marcadores(contenido)
    if not encabezado and not fila:
        raise DatosInvalidos("La plantilla no tiene ningún marcador {{campo}}: no hay dónde poner los datos")
    desconocidos = sorted(encabezado - set(t["encabezado"])) + sorted(f"fila.{c}" for c in fila - set(t["fila"]))
    if desconocidos:
        raise DatosInvalidos(f"Marcadores que ARCA no conoce para «{t['nombre']}»: {', '.join(desconocidos)}. Consulte la lista de campos disponibles.")
    if fila and not t["fila"]:
        raise DatosInvalidos(f"«{t['nombre']}» no tiene filas: quite los marcadores {{{{fila.…}}}}")
    return sorted(encabezado) + sorted(f"fila.{c}" for c in fila)


def crear(ctx, tipo: str, nombre: str, descripcion: str, proyecto_id: uuid.UUID | None) -> Plantilla:
    tipo_o_error(tipo)
    _proyecto_del_tenant(ctx, proyecto_id)
    if ctx.db.scalar(select(Plantilla).where(Plantilla.tenant_id == ctx.tenant_id, Plantilla.proyecto_id == proyecto_id if proyecto_id else Plantilla.proyecto_id.is_(None),
                                            Plantilla.tipo == tipo, Plantilla.nombre == nombre.strip())):
        raise DatosInvalidos("Ya existe una plantilla de ese tipo con ese nombre")
    p = Plantilla(tenant_id=ctx.tenant_id, proyecto_id=proyecto_id, tipo=tipo, nombre=nombre.strip(), descripcion=descripcion.strip(), creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(p)
    ctx.db.flush()
    ctx.auditar(accion="CREAR_PLANTILLA", objeto="Plantilla", objeto_id=p.id, detalle=f"{TIPOS[tipo]['nombre']} · {p.nombre}")
    ctx.db.commit()
    return p


def _actualizar_estados(ctx, plantilla: Plantilla) -> None:
    """La vigente es la de mayor vigencia ya alcanzada; las anteriores quedan reemplazadas y las futuras, programadas."""
    ahora = ahora_utc()
    todas = list(ctx.db.scalars(select(VersionPlantilla).where(VersionPlantilla.plantilla_id == plantilla.id)))
    alcanzadas = sorted((v for v in todas if en_utc(v.vigente_desde) <= ahora), key=lambda v: (en_utc(v.vigente_desde), v.version))
    vigente = alcanzadas[-1] if alcanzadas else None
    for v in todas:
        v.estado = "vigente" if v is vigente else ("programada" if en_utc(v.vigente_desde) > ahora else "reemplazada")


def publicar_version(ctx, plantilla: Plantilla, contenido: bytes, nombre_archivo: str, motivo: str, codigo_formato: str,
                     valores_fijos: dict[str, Any], vigente_desde: datetime | None) -> VersionPlantilla:
    campos = _validar_archivo(plantilla.tipo, contenido)
    disponibles = set(TIPOS[plantilla.tipo]["encabezado"])
    if desconocidos := set(valores_fijos) - disponibles:
        raise DatosInvalidos(f"Valores fijos para campos que no existen: {', '.join(sorted(desconocidos))}")
    ahora = ahora_utc()
    vigencia = en_utc(vigente_desde) if vigente_desde else ahora
    if vigencia < ahora - timedelta(minutes=2):
        raise DatosInvalidos("La vigencia no puede ser pasada: lo ya expedido conserva la versión con que se hizo")
    proyecto = ctx.db.get(Proyecto, plantilla.proyecto_id) if plantilla.proyecto_id else None
    archivo = guardar_archivo(ctx, proyecto or _proyecto_cualquiera(ctx), contenido, nombre_archivo, {"XLSX"})
    ultima = ctx.db.scalar(select(func.max(VersionPlantilla.version)).where(VersionPlantilla.plantilla_id == plantilla.id)) or 0
    v = VersionPlantilla(
        tenant_id=ctx.tenant_id, plantilla_id=plantilla.id, version=ultima + 1, codigo_formato=codigo_formato.strip(), archivo_id=archivo.id, campos=campos,
        valores_fijos={k: str(val) for k, val in valores_fijos.items()}, vigente_desde=max(vigencia, ahora), motivo=motivo, creado_en=ahora, creado_por=ctx.usuario.id,
    )
    ctx.db.add(v)
    ctx.db.flush()
    _actualizar_estados(ctx, plantilla)
    ctx.auditar(accion="PUBLICAR_PLANTILLA", objeto="VersionPlantilla", objeto_id=v.id, motivo=motivo,
                detalle=f"{plantilla.nombre} v{v.version} · {codigo_formato or 'sin código'} · vigente desde {v.vigente_desde.isoformat()} · SHA-256 {archivo.sha256[:16]}…")
    ctx.db.commit()
    return v


def _proyecto_cualquiera(ctx) -> Proyecto:
    """Las plantillas de la organización guardan su archivo bajo el primer proyecto (el repositorio se organiza por proyecto)."""
    p = ctx.db.scalar(select(Proyecto).where(Proyecto.tenant_id == ctx.tenant_id).order_by(Proyecto.creado_en).limit(1))
    if p is None:
        raise DatosInvalidos("Cree primero un proyecto: el archivo de la plantilla se custodia en el repositorio del proyecto")
    return p


def version_vigente(ctx, proyecto: Proyecto, tipo: str, plantilla_id: uuid.UUID | None = None) -> VersionPlantilla:
    if plantilla_id:
        candidatas = [obtener(ctx, plantilla_id)]
        if candidatas[0].tipo != tipo:
            raise DatosInvalidos("Esa plantilla es de otro tipo")
    else:
        candidatas = sorted((p for p in listar(ctx, proyecto.id) if p.tipo == tipo), key=lambda p: p.proyecto_id is None)  # primero las del proyecto
    for p in candidatas:
        _actualizar_estados(ctx, p)
        v = ctx.db.scalar(select(VersionPlantilla).where(VersionPlantilla.plantilla_id == p.id, VersionPlantilla.estado == "vigente"))
        if v:
            return v
    raise DatosInvalidos(f"No hay una plantilla vigente de «{TIPOS[tipo]['nombre']}». Súbala en Plantillas (puede partir del formato base).")


# --- Datos para llenar ------------------------------------------------------------------------


def _comunes(ctx, proyecto: Proyecto, v: VersionPlantilla) -> dict[str, Any]:
    org = ctx.organizacion
    return {"entidad": org.razon_social, "nit": org.identificacion, "proyecto": proyecto.nombre, "codigo_proyecto": proyecto.codigo,
            "entidad_cliente": proyecto.entidad_cliente, "contrato": proyecto.numero_contrato or "", "fecha": datetime.now().date(),
            "codigo_formato": v.codigo_formato, "version_formato": v.version}


def _unidades(ctx, proyecto: Proyecto, cajas: list[str] | None, lote: str | None, unidad_ids: list[uuid.UUID] | None = None) -> list[UnidadDocumental]:
    consulta = select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)
    if unidad_ids is not None:
        consulta = consulta.where(UnidadDocumental.id.in_(unidad_ids))
    filas = list(ctx.db.scalars(consulta.order_by(UnidadDocumental.creado_en)))
    if cajas:
        buscadas = {clave_de(c) for c in cajas}
        filas = [u for u in filas if u.caja and clave_de(u.caja) in buscadas]
    if lote:
        lotes_cajas = {c.clave for c in ctx.db.scalars(select(CajaProyecto).where(CajaProyecto.proyecto_id == proyecto.id, CajaProyecto.lote == lote))}
        filas = [u for u in filas if u.caja and clave_de(u.caja) in lotes_cajas]
    return filas


def _imagenes_por_unidad(ctx, proyecto: Proyecto) -> dict[uuid.UUID, tuple[int, str]]:
    datos: dict[uuid.UUID, list] = defaultdict(lambda: [0, set()])
    for unidad_id, paginas, estado in ctx.db.execute(
        select(RecursoDigital.unidad_id, RecursoDigital.paginas, RecursoDigital.estado).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None))
    ):
        if estado != EstadoRecurso.REEMPLAZADO.value:
            datos[unidad_id][0] += paginas or 0
            datos[unidad_id][1].add(estado)
    salida = {}
    for uid, (paginas, estados) in datos.items():
        estado = "Aprobada" if estados == {"aprobado"} else "Con recaptura" if estados & {"rechazado", "recaptura"} else "Por revisar"
        salida[uid] = (paginas, estado)
    return salida


def _clasificaciones(ctx, proyecto: Proyecto) -> dict[uuid.UUID, dict[str, Any]]:
    """Código, serie, subserie y dependencia de la clasificación activa de cada unidad."""
    salida: dict[uuid.UUID, dict[str, Any]] = {}
    filas = ctx.db.execute(
        select(ClasificacionUnidad.unidad_id, ClasificacionUnidad.version_id, ElementoInstrumento)
        .join(ElementoInstrumento, ClasificacionUnidad.elemento_id == ElementoInstrumento.id)
        .where(ClasificacionUnidad.proyecto_id == proyecto.id, ClasificacionUnidad.estado == "confirmada")
    ).all()
    series = {(e.version_id, e.codigo): e.nombre for e in ctx.db.scalars(select(ElementoInstrumento).where(
        ElementoInstrumento.version_id.in_({f[1] for f in filas}), ElementoInstrumento.nivel == "serie"))} if filas else {}
    for unidad_id, version_id, e in filas:
        es_sub = e.nivel == "subserie"
        salida[unidad_id] = {"codigo_clasificacion": e.codigo, "serie": series.get((version_id, e.padre), "") if es_sub else e.nombre,
                             "subserie": e.nombre if es_sub else "", "dependencia": e.codigo_dependencia}
    return salida


FASES = {"gestion": "Archivo de gestión", "central": "Archivo central", "historico": "Archivo histórico"}


def _hojas_verificadas(ctx, proyecto: Proyecto) -> dict[uuid.UUID, dict[str, Any]]:
    """Folios contados y fechas extremas de cada hoja de control verificada: lo que manda en el FUID de salida."""
    from arca.modelos import HojaControl, TramiteHoja  # noqa: PLC0415

    salida: dict[uuid.UUID, dict[str, Any]] = {}
    hojas = {h.id: h for h in ctx.db.scalars(select(HojaControl).where(HojaControl.proyecto_id == proyecto.id, HojaControl.estado == "verificada"))}
    fechas: dict[uuid.UUID, list[str]] = defaultdict(list)
    if hojas:
        for hid, texto in ctx.db.execute(select(TramiteHoja.hoja_id, TramiteHoja.fecha_texto).where(TramiteHoja.hoja_id.in_(hojas), TramiteHoja.fecha_texto.is_not(None))):
            fechas[hid].append(texto)
    for hid, h in hojas.items():
        f = sorted(fechas[hid])
        salida[h.unidad_id] = {"folios": h.total_folios, "inicial": _fecha(f[0]) if f else None, "final": _fecha(f[-1]) if f else None}
    return salida


def _fecha(texto: str):
    """La fecha completa como fecha; la parcial («1990-07») como texto, tal cual."""
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return texto


def _fila_unidad(u: UnidadDocumental, imagenes: dict[uuid.UUID, tuple[int, str]], clasif: dict[uuid.UUID, dict[str, Any]] | None = None,
                 hojas: dict[uuid.UUID, dict[str, Any]] | None = None) -> dict[str, Any]:
    paginas, estado = imagenes.get(u.id, (0, "Sin digitalizar"))
    c = (clasif or {}).get(u.id, {})
    h = (hojas or {}).get(u.id)
    folios, notas = u.folios, u.notas
    inicial, final = u.fecha_inicial, u.fecha_final
    if h:
        folios = h["folios"] if h["folios"] is not None else u.folios
        inicial, final = h["inicial"] or u.fecha_inicial, h["final"] or u.fecha_final
        if u.folios is not None and h["folios"] is not None and h["folios"] != u.folios:
            constancia = f"Folios contados en la hoja de control: {h['folios']}; el inventario de origen declaraba {u.folios}."
            notas = f"{notas} {constancia}".strip() if notas else constancia
    return {"numero_orden": u.numero_orden, "identificador": u.identificador, "codigo_serie": u.codigo_serie, "nombre": u.nombre, "fecha_inicial": inicial,
            "fecha_final": final, "caja": u.caja, "carpeta": u.carpeta, "tomo": u.tomo, "otro": u.otro, "folios": folios, "soporte": SOPORTES.get(u.soporte, u.soporte),
            "frecuencia_consulta": u.frecuencia_consulta, "notas": notas, "imagenes": paginas or None, "estado_digitalizacion": estado,
            "folios_inventario": u.folios, "origen_folios": "hoja de control verificada" if h else "inventario de origen",
            "codigo_clasificacion": c.get("codigo_clasificacion", ""), "serie": c.get("serie", ""), "subserie": c.get("subserie", ""), "dependencia": c.get("dependencia", ""),
            "fase": FASES.get(u.fase, u.fase)}


def _orden_natural(clave: str) -> list:
    """«C2» antes que «C10»: el orden en que se rotulan y se archivan las cajas."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", clave)]


SOPORTES = {"fisico": "Físico", "electronico": "Electrónico", "hibrido": "Híbrido"}


def _valores_fijos(v: VersionPlantilla) -> dict[str, Any]:
    return {k: val for k, val in (v.valores_fijos or {}).items() if val not in (None, "")}


def expedir(ctx, proyecto: Proyecto, tipo: str, cajas: list[str] | None, lote: str | None, plantilla_id: uuid.UUID | None,
            unidad_ids: list[uuid.UUID] | None = None, encabezado_extra: dict[str, Any] | None = None, filtro_extra: dict[str, Any] | None = None) -> Expedicion:
    """Llena la plantilla vigente. `unidad_ids` y `encabezado_extra` los usa, por ejemplo, el inventario de una transferencia."""
    v = version_vigente(ctx, proyecto, tipo, plantilla_id)
    archivo_plantilla = ctx.db.get(ArchivoDigital, v.archivo_id)
    contenido = almacen.leer(archivo_plantilla.clave_almacen, ctx.tenant_id)
    if almacen.huella(contenido) != archivo_plantilla.sha256:
        raise TransicionInvalida("ALERTA DE INTEGRIDAD: el archivo de la plantilla no coincide con su huella")
    comunes = {**_comunes(ctx, proyecto, v), "objeto": "", "numero_transferencia": "", "oficina_productora": "", "codigo_oficina": "", "fecha_corte": None,
               **(encabezado_extra or {}), **_valores_fijos(v)}
    unidades = _unidades(ctx, proyecto, cajas, lote, unidad_ids)
    imagenes = _imagenes_por_unidad(ctx, proyecto)
    clasif = _clasificaciones(ctx, proyecto)
    hojas = _hojas_verificadas(ctx, proyecto)
    if tipo in ("fuid", "acta_eliminacion"):
        if not unidades:
            raise DatosInvalidos("No hay unidades documentales para ese filtro")
        filas = [_fila_unidad(u, imagenes, clasif, hojas) for u in unidades]
        encabezado = {**comunes, "total_unidades": len(filas), "total_folios": sum(f["folios"] or 0 for f in filas), "total_imagenes": sum(f["imagenes"] or 0 for f in filas)}
        resultado, elementos = motor.llenar(contenido, encabezado, filas), len(filas)
    elif tipo == "rotulo_caja":
        base_cajas = {c.clave: c for c in ctx.db.scalars(select(CajaProyecto).where(CajaProyecto.proyecto_id == proyecto.id))}
        por_caja: dict[str, list[UnidadDocumental]] = defaultdict(list)
        for u in unidades:
            if u.caja:
                por_caja[clave_de(u.caja)].append(u)
        claves = [clave_de(c) for c in cajas] if cajas else sorted(set(por_caja) | ({c.clave for c in base_cajas.values() if not lote or c.lote == lote}), key=_orden_natural)
        lista = []
        for clave in claves:
            caja, contenido_caja = base_cajas.get(clave), por_caja.get(clave, [])
            if caja is None and not contenido_caja:
                continue
            fechas_i = [u.fecha_inicial for u in contenido_caja if u.fecha_inicial]
            fechas_f = [u.fecha_final for u in contenido_caja if u.fecha_final]
            codigo = caja.codigo if caja else contenido_caja[0].caja
            encabezado = {**comunes, "caja": codigo, "frente": caja.frente if caja else None, "lote": caja.lote if caja else "", "sede": caja.sede if caja else "",
                          "ubicacion": caja.ubicacion if caja else "", "carpetas": (caja.carpetas if caja and caja.carpetas is not None else len(contenido_caja)),
                          "primer_identificador": contenido_caja[0].identificador if contenido_caja else "", "ultimo_identificador": contenido_caja[-1].identificador if contenido_caja else "",
                          "fecha_inicial": min(fechas_i) if fechas_i else None, "fecha_final": max(fechas_f) if fechas_f else None,
                          "series": ", ".join(sorted({u.codigo_serie for u in contenido_caja if u.codigo_serie})), "folios": sum(u.folios or 0 for u in contenido_caja)}
            lista.append((f"Caja {codigo}", encabezado, [_fila_unidad(u, imagenes, clasif, hojas) for u in contenido_caja]))
        resultado, elementos = motor.llenar_varios(contenido, lista), len(lista)
    else:
        lista = [(u.identificador, {**comunes, **_fila_unidad(u, imagenes, clasif, hojas)}, []) for u in unidades]
        resultado, elementos = motor.llenar_varios(contenido, lista), len(lista)
    nombre = f"{ {'fuid': 'FUID', 'rotulo_caja': 'Rotulos_caja', 'rotulo_carpeta': 'Rotulos_carpeta', 'acta_eliminacion': 'Acta_eliminacion'}[tipo] }_{proyecto.codigo}_{datetime.now():%Y%m%d_%H%M}.xlsx"
    archivo = guardar_archivo(ctx, proyecto, resultado, nombre, {"XLSX"})
    e = Expedicion(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, tipo=tipo, version_id=v.id, archivo_id=archivo.id,
                   filtro={"cajas": cajas or [], "lote": lote or "", **(filtro_extra or {})}, elementos=elementos, creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(e)
    ctx.db.flush()
    ctx.auditar(accion="EXPEDIR", objeto="Expedicion", objeto_id=e.id,
                detalle=f"{TIPOS[tipo]['nombre']} · {elementos} elementos · plantilla v{v.version} · SHA-256 {archivo.sha256[:16]}…")
    ctx.db.commit()
    return e


def expedir_filas(ctx, proyecto: Proyecto, tipo: str, encabezado: dict[str, Any], filas: list[dict[str, Any]], nombre: str, filtro: dict[str, Any]) -> Expedicion:
    """Llena la plantilla vigente con un encabezado y unas filas que arma otro módulo (por ejemplo, la hoja de control)."""
    v = version_vigente(ctx, proyecto, tipo, None)
    archivo_plantilla = ctx.db.get(ArchivoDigital, v.archivo_id)
    contenido = almacen.leer(archivo_plantilla.clave_almacen, ctx.tenant_id)
    if almacen.huella(contenido) != archivo_plantilla.sha256:
        raise TransicionInvalida("ALERTA DE INTEGRIDAD: el archivo de la plantilla no coincide con su huella")
    datos = {**_comunes(ctx, proyecto, v), **encabezado, **_valores_fijos(v)}
    resultado = motor.llenar(contenido, datos, filas)
    archivo = guardar_archivo(ctx, proyecto, resultado, f"{nombre}_{datetime.now():%Y%m%d_%H%M}.xlsx", {"XLSX"})
    e = Expedicion(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, tipo=tipo, version_id=v.id, archivo_id=archivo.id, filtro=filtro, elementos=len(filas),
                   creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(e)
    ctx.db.flush()
    ctx.auditar(accion="EXPEDIR", objeto="Expedicion", objeto_id=e.id, detalle=f"{TIPOS[tipo]['nombre']} · {len(filas)} filas · plantilla v{v.version} · SHA-256 {archivo.sha256[:16]}…")
    ctx.db.commit()
    return e


def expediciones(ctx, proyecto: Proyecto) -> list[tuple[Expedicion, VersionPlantilla, ArchivoDigital]]:
    filas = ctx.db.execute(
        select(Expedicion, VersionPlantilla, ArchivoDigital).join(VersionPlantilla, Expedicion.version_id == VersionPlantilla.id)
        .join(ArchivoDigital, Expedicion.archivo_id == ArchivoDigital.id).where(Expedicion.proyecto_id == proyecto.id).order_by(Expedicion.creado_en.desc())
    ).all()
    return [tuple(f) for f in filas]


def archivo_de(ctx, proyecto: Proyecto, expedicion_id: uuid.UUID) -> tuple[bytes, ArchivoDigital]:
    e = ctx.db.get(Expedicion, expedicion_id)
    if e is None or e.proyecto_id != proyecto.id:
        raise NoEncontrado("La expedición no existe")
    archivo = ctx.db.get(ArchivoDigital, e.archivo_id)
    datos = almacen.leer(archivo.clave_almacen, ctx.tenant_id)
    if almacen.huella(datos) != archivo.sha256:
        raise TransicionInvalida("ALERTA DE INTEGRIDAD: el documento expedido no coincide con su huella")
    return datos, archivo


def archivo_version(ctx, version_id: uuid.UUID) -> tuple[bytes, ArchivoDigital]:
    v = ctx.db.get(VersionPlantilla, version_id)
    if v is None or v.tenant_id != ctx.tenant_id:
        raise NoEncontrado("La versión no existe")
    archivo = ctx.db.get(ArchivoDigital, v.archivo_id)
    return almacen.leer(archivo.clave_almacen, ctx.tenant_id), archivo
