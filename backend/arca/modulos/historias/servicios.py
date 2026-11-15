"""Historias laborales (D-43): lo que ARCA automatiza en un proyecto de digitalización y organización de historias laborales.

Una historia laboral es el expediente de una persona (Acuerdo AGN 001 de 2024, Título 9, Capítulo 5). Lo que ARCA hace:

- **Titular.** Propone el tipo y número de documento y el nombre de la persona: del FUID (el nombre de la unidad suele
  traerlos) y, si no, del OCR (el número que más se repite junto a «C.C.», «cédula», «identificado con»…). Cada dato
  dice de dónde salió. Una persona lo confirma.
- **Documentos de otra persona.** Señala las páginas donde aparece un número de documento distinto al del titular: es
  el error más grave en una historia laboral (un documento archivado en el expediente equivocado).
- **Tipos documentales mínimos.** Compara los tipos de la hoja de control con los obligatorios que fije la dirección
  (los del Banco Terminológico del AGN o los de la TRD de la entidad) y dice cuáles faltan.
- **Orden cronológico.** (En la hoja de control, para todo expediente.) Avisa cuando un documento tiene fecha anterior
  al que lo precede.
- **Duplicados.** Avisa cuando dos expedientes tienen el mismo titular.

Nada de esto decide por una persona: son propuestas y avisos, con la página de donde salen.
"""

import re
import unicodedata
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from arca.modelos import (
    ClasificacionUnidad,
    ConfigHistorias,
    ElementoInstrumento,
    EstadoProyecto,
    HojaControl,
    Proyecto,
    TextoPagina,
    TitularExpediente,
    TramiteHoja,
    UnidadDocumental,
)
from arca.modelos.base import ahora_utc
from arca.modulos.m10_digitalizacion.paginas import paginas
from arca.nucleo.errores import DatosInvalidos, NoEncontrado, TransicionInvalida

TIPOS_DOCUMENTO = {"CC": "Cédula de ciudadanía", "CE": "Cédula de extranjería", "TI": "Tarjeta de identidad", "PA": "Pasaporte", "PEP": "Permiso especial de permanencia"}
_MARCA = (r"(?<![a-záéíóúñ])(?:c\.?\s?c\.?|c[eé]d(?:ula)?\.?(?:\s+de\s+(?:ciudadan[ií]a|extranjer[ií]a))?|t\.?\s?i\.?|c\.?\s?e\.?|"
          r"tarjeta\s+de\s+identidad|documento\s+de\s+identidad|identificad[oa]\s+con(?:\s+(?:la\s+)?(?:c[eé]dula(?:\s+de\s+ciudadan[ií]a)?|c\.?\s?c\.?))?)")
DOCUMENTO = re.compile(_MARCA + r"\s*(?:n(?:o|ro|[uú]m(?:ero)?)?\s*[\.º°]*\s*)?[:#.]?\s*((?:\d{1,3}[.,\s]){1,3}\d{3}(?!\d)|\d{5,11}(?!\d))", re.IGNORECASE)
SUELTO = re.compile(r"(?<![\d.,])((?:\d{1,3}\.){1,3}\d{3}|\d{6,11})(?![\d.,]*\d)")
TIPO_MARCA = re.compile(r"(?<![a-záéíóúñ])(c\.?\s?e\.?|c[eé]dula\s+de\s+extranjer[ií]a|t\.?\s?i\.?|tarjeta\s+de\s+identidad)", re.IGNORECASE)
RELLENO = re.compile(r"\b(tomo\s*\d+|t\.\s*\d+|historia(?:s)?\s+laboral(?:es)?(?:\s+de)?|hoja\s+de\s+vida(?:\s+de)?|expediente(?:\s+de)?|funcionari[oa]|ex\s*funcionari[oa]|"
                     r"c\.?\s?c\.?|c[eé]dula(?:\s+de\s+ciudadan[ií]a)?|n(?:o|ro|[uú]mero)\.?|identificad[oa]\s+con)\b", re.IGNORECASE)


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def _plano(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (texto or "").lower()) if unicodedata.category(c) != "Mn").strip()


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def documentos_en(texto: str) -> list[str]:
    """Los números de documento de identidad escritos en un texto, junto a su rótulo («C.C.», «cédula», «identificado con»…)."""
    salida = []
    for m in DOCUMENTO.finditer(texto or ""):
        n = _digitos(m.group(1))
        if 5 <= len(n) <= 11 and n not in salida:
            salida.append(n)
    return salida


def del_fuid(nombre: str, notas: str = "") -> dict[str, str]:
    """Del nombre de la unidad en el FUID (p. ej. «Historia laboral PÉREZ GÓMEZ ANA · C.C. 52.123.456»): número, tipo y nombre."""
    texto = f"{nombre or ''} {notas or ''}"
    numeros = documentos_en(texto)
    if not numeros:
        sueltos = [_digitos(m.group(1)) for m in SUELTO.finditer(texto)]
        numeros = [n for n in sueltos if 6 <= len(n) <= 11]
    salida: dict[str, str] = {}
    if numeros:
        salida["numero_documento"] = numeros[0]
        t = TIPO_MARCA.search(texto)
        if t:
            salida["tipo_documento"] = "CE" if _plano(t.group(1)).startswith("c") else "TI"
    persona = DOCUMENTO.sub(" ", nombre or "")
    persona = SUELTO.sub(" ", persona)
    persona = RELLENO.sub(" ", persona)
    persona = re.sub(r"\s+", " ", re.sub(r"[·•|:;,\-–—()\[\]#]+", " ", persona)).strip(" .")
    if numeros and len(persona) >= 5 and any(c.isalpha() for c in persona):  # sin número, el nombre de la unidad no es el de una persona
        salida["nombres"] = persona[:300]
    return salida


# --- Configuración ----------------------------------------------------------------------------


def config_de(ctx, proyecto: Proyecto) -> ConfigHistorias | None:
    return ctx.db.scalar(select(ConfigHistorias).where(ConfigHistorias.proyecto_id == proyecto.id))


def _codigo_clasificacion(ctx, unidad_id: uuid.UUID) -> tuple[str, list[str]] | None:
    fila = ctx.db.execute(select(ElementoInstrumento.codigo, ElementoInstrumento.tipos_documentales).join(ClasificacionUnidad, ClasificacionUnidad.elemento_id == ElementoInstrumento.id)
                          .where(ClasificacionUnidad.unidad_id == unidad_id, ClasificacionUnidad.estado == "confirmada")).first()
    return (fila[0], list(fila[1] or [])) if fila else None


def aplica(ctx, conf: ConfigHistorias | None, u: UnidadDocumental) -> bool:
    if conf is None or not conf.activo:
        return False
    if not conf.series:
        return True
    c = _codigo_clasificacion(ctx, u.id)
    return bool(c and any(c[0] == s or c[0].startswith(s) for s in conf.series))


def ver_config(ctx, proyecto: Proyecto) -> dict[str, Any]:
    conf = config_de(ctx, proyecto)
    sugeridos: list[str] = []
    for tipos in ctx.db.scalars(select(ElementoInstrumento.tipos_documentales).join(ClasificacionUnidad, ClasificacionUnidad.elemento_id == ElementoInstrumento.id)
                                .where(ClasificacionUnidad.proyecto_id == proyecto.id, ClasificacionUnidad.estado == "confirmada").distinct()):
        for t in tipos or []:
            if t not in sugeridos:
                sugeridos.append(t)
    base = {"tipos_documento": TIPOS_DOCUMENTO, "tipos_de_la_trd": sugeridos[:200],
            "aviso": "Los tipos documentales mínimos de la serie están en el Banco Terminológico (BANTER) del AGN y en la TRD de la entidad: márquelos aquí."}
    if conf is None:
        return {"configurado": False, "activo": False, "series": [], "tipos_obligatorios": [], "acceso_restringido": True, **base}
    return {"configurado": True, "activo": conf.activo, "series": conf.series, "tipos_obligatorios": conf.tipos_obligatorios, "motivo": conf.motivo,
            "acceso_restringido": conf.acceso_restringido,
            "actualizado_en": conf.actualizado_en, **base}


def guardar_config(ctx, proyecto: Proyecto, activo: bool, series: list[str], tipos: list[str], motivo: str, acceso_restringido: bool = True) -> ConfigHistorias:
    _abierto(proyecto)
    tipos = list(dict.fromkeys(t.strip()[:200] for t in tipos if t.strip()))
    series = list(dict.fromkeys(s.strip()[:80] for s in series if s.strip()))
    conf = config_de(ctx, proyecto)
    if conf is None:
        conf = ConfigHistorias(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id)
        ctx.db.add(conf)
    conf.activo, conf.series, conf.tipos_obligatorios, conf.motivo, conf.actualizado_en, conf.actualizado_por = activo, series, tipos, motivo.strip(), ahora_utc(), ctx.usuario.id
    conf.acceso_restringido = acceso_restringido
    ctx.auditar(accion="CONFIGURAR_HISTORIAS", objeto="Proyecto", objeto_id=proyecto.id,
                detalle=f"{proyecto.codigo} · {'activo' if activo else 'inactivo'} · acceso {'restringido' if acceso_restringido else 'según la TRD'} · series: {', '.join(series) or 'todo el proyecto'} · {len(tipos)} tipos obligatorios · {motivo.strip()}")
    ctx.db.commit()
    return conf


def restringida(ctx, u: UnidadDocumental) -> bool:
    """Una historia laboral es de acceso restringido (artículo 9.5.3) si la configuración lo pide, diga lo que diga la TRD."""
    conf = ctx.db.scalar(select(ConfigHistorias).where(ConfigHistorias.proyecto_id == u.proyecto_id))
    return bool(conf and conf.acceso_restringido and aplica(ctx, conf, u))


def restringidas(ctx, unidades: list[UnidadDocumental]) -> set[uuid.UUID]:
    confs = {c.proyecto_id: c for c in ctx.db.scalars(select(ConfigHistorias).where(ConfigHistorias.proyecto_id.in_({u.proyecto_id for u in unidades})))} if unidades else {}
    return {u.id for u in unidades if (c := confs.get(u.proyecto_id)) and c.acceso_restringido and aplica(ctx, c, u)}


def bases_de_retencion(ctx, proyecto: Proyecto) -> dict[uuid.UUID, Any]:
    """Para cada historia laboral, desde cuándo se cuenta la retención: la fecha de retiro del titular confirmado, o
    `SIN_RETIRO` si la persona sigue vinculada. Las unidades que no son historias laborales no aparecen."""
    from arca.modulos.m04_instrumentos.clasificacion import SIN_RETIRO  # noqa: PLC0415

    conf = config_de(ctx, proyecto)
    if conf is None or not conf.activo:
        return {}
    titulares = {t.unidad_id: t for t in ctx.db.scalars(select(TitularExpediente).where(TitularExpediente.proyecto_id == proyecto.id, TitularExpediente.estado == "confirmado"))}
    salida: dict[uuid.UUID, Any] = {}
    for uid, t in titulares.items():
        u = ctx.db.get(UnidadDocumental, uid)
        if aplica(ctx, conf, u):
            salida[uid] = t.fecha_retiro or SIN_RETIRO
    return salida


# --- Titular ----------------------------------------------------------------------------------


def titular_de(ctx, u: UnidadDocumental) -> TitularExpediente | None:
    return ctx.db.scalar(select(TitularExpediente).where(TitularExpediente.unidad_id == u.id))


def textos_por_pagina(ctx, u: UnidadDocumental) -> list[tuple[int, str]]:
    lista = paginas(ctx, u)
    if not lista:
        return []
    leidas = {(t.recurso_id, t.pagina): t.texto for t in ctx.db.scalars(select(TextoPagina).where(TextoPagina.recurso_id.in_({p["recurso_id"] for p in lista}),
                                                                                                    TextoPagina.estado == "leida"))}
    return [(p["n"], leidas[(p["recurso_id"], p["pagina_en_archivo"])]) for p in lista if (p["recurso_id"], p["pagina_en_archivo"]) in leidas]


def _paginas_con(textos: list[tuple[int, str]]) -> dict[str, list[int]]:
    donde: dict[str, list[int]] = {}
    for n, texto in textos:
        for d in documentos_en(texto):
            donde.setdefault(d, []).append(n)
    return donde


def _crear(ctx, proyecto: Proyecto, u: UnidadDocumental) -> TitularExpediente:
    """Crea el titular; si otro proceso (el flujo automático) lo acaba de crear, devuelve ese."""
    try:
        with ctx.db.begin_nested():
            t = TitularExpediente(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=u.id, origen={}, estado="propuesto", actualizado_en=ahora_utc())
            ctx.db.add(t)
        return t
    except IntegrityError:
        return titular_de(ctx, u)


def proponer(ctx, proyecto: Proyecto, u: UnidadDocumental) -> TitularExpediente | None:
    """Propone el titular del FUID y del OCR. Lo ya confirmado por una persona no se toca."""
    t = titular_de(ctx, u)
    if t is not None and t.estado == "confirmado":
        return t
    fuid = del_fuid(u.nombre, u.notas or "")
    donde = _paginas_con(textos_por_pagina(ctx, u))
    origen: dict[str, dict[str, str]] = {}
    numero = fuid.get("numero_documento", "")
    if numero:
        origen["numero_documento"] = {"fuente": "fuid", "detalle": f"del nombre de la unidad en el FUID: «{u.nombre[:120]}»"
                                      + (f" · aparece en las páginas {', '.join(map(str, donde[numero][:8]))}" if numero in donde else " · no aparece en el texto leído")}
    elif donde:
        numero, pags = max(donde.items(), key=lambda x: (len(x[1]), -x[1][0]))
        origen["numero_documento"] = {"fuente": "ocr", "detalle": f"el número de documento que más se repite en el texto leído: páginas {', '.join(map(str, pags[:8]))}"}
    if not numero and not fuid.get("nombres"):
        return t
    if t is None:
        t = _crear(ctx, proyecto, u)
        if t.estado == "confirmado":
            return t
    t.numero_documento, t.tipo_documento = numero, fuid.get("tipo_documento", "CC")
    if fuid.get("nombres"):
        t.nombres = fuid["nombres"]
        origen["nombres"] = {"fuente": "fuid", "detalle": "del nombre de la unidad en el FUID"}
    t.origen, t.estado, t.actualizado_en = origen, "propuesto", ahora_utc()
    ctx.auditar(accion="PROPONER_TITULAR", objeto="UnidadDocumental", objeto_id=u.id,
                detalle=f"{u.identificador} · {t.tipo_documento} {numero or '—'} · {t.nombres or '—'} · " + " · ".join(f"{k}: {v['fuente']}" for k, v in origen.items()))
    ctx.db.commit()
    return t


def confirmar(ctx, proyecto: Proyecto, u: UnidadDocumental, datos: dict[str, Any]) -> TitularExpediente:
    """Una persona confirma (y corrige) el titular. Lo que cambia queda con su nombre como origen."""
    _abierto(proyecto)
    t = titular_de(ctx, u) or _crear(ctx, proyecto, u)
    if datos.get("tipo_documento") and datos["tipo_documento"] not in TIPOS_DOCUMENTO:
        raise DatosInvalidos("Tipo de documento no admitido: CC, CE, TI, PA o PEP")
    numero = datos.get("numero_documento")
    if numero is not None:
        numero = re.sub(r"[^0-9A-Za-z]", "", str(numero)).upper()
        if not 5 <= len(numero) <= 15:
            raise DatosInvalidos("El número de documento tiene entre 5 y 15 caracteres")
    if datos.get("fecha_vinculacion") and datos.get("fecha_retiro") and datos["fecha_retiro"] < datos["fecha_vinculacion"]:
        raise DatosInvalidos("La fecha de retiro es anterior a la de vinculación")
    origen = dict(t.origen or {})
    for campo in ("tipo_documento", "numero_documento", "nombres", "cargo", "dependencia", "fecha_vinculacion", "fecha_retiro"):
        if campo not in datos or datos[campo] is None:
            continue
        valor = numero if campo == "numero_documento" else (datos[campo].strip()[:300] if isinstance(datos[campo], str) else datos[campo])
        if valor != getattr(t, campo):
            setattr(t, campo, valor)
            origen[campo] = {"fuente": "persona", "detalle": f"escrito por {ctx.usuario.nombre_completo}"}
    if not t.numero_documento or not t.nombres:
        raise DatosInvalidos("Para confirmar, el titular necesita número de documento y nombre")
    t.origen, t.estado, t.actualizado_en, t.confirmado_en, t.confirmado_por = origen, "confirmado", ahora_utc(), ahora_utc(), ctx.usuario.id
    u.actualizado_en = ahora_utc()  # la consulta se pone al día
    ctx.auditar(accion="CONFIRMAR_TITULAR", objeto="UnidadDocumental", objeto_id=u.id, detalle=f"{u.identificador} · {t.tipo_documento} {t.numero_documento} · {t.nombres}")
    ctx.db.commit()
    return t


def como_dict(t: TitularExpediente | None) -> dict[str, Any] | None:
    if t is None:
        return None
    return {"tipo_documento": t.tipo_documento, "numero_documento": t.numero_documento, "nombres": t.nombres, "cargo": t.cargo, "dependencia": t.dependencia,
            "fecha_vinculacion": t.fecha_vinculacion.isoformat() if t.fecha_vinculacion else None, "fecha_retiro": t.fecha_retiro.isoformat() if t.fecha_retiro else None,
            "estado": t.estado, "origen": t.origen or {}, "confirmado_en": t.confirmado_en}


# --- Revisión del expediente ------------------------------------------------------------------


def _tipos_de_la_hoja(ctx, u: UnidadDocumental) -> tuple[list[str], str | None]:
    h = ctx.db.scalar(select(HojaControl).where(HojaControl.unidad_id == u.id))
    if h is None:
        return [], None
    return [t for t in ctx.db.scalars(select(TramiteHoja.tipo_documental).where(TramiteHoja.hoja_id == h.id)) if t], h.estado


def revisar(ctx, proyecto: Proyecto, u: UnidadDocumental, conf: ConfigHistorias | None = None) -> dict[str, Any]:
    conf = conf or config_de(ctx, proyecto)
    t = titular_de(ctx, u)
    textos = textos_por_pagina(ctx, u)
    donde = _paginas_con(textos)
    alertas: list[dict[str, Any]] = []
    numero = t.numero_documento if t else ""
    ajenos = [{"numero": n, "paginas": p} for n, p in sorted(donde.items(), key=lambda x: x[1][0]) if numero and n != numero]
    for a in ajenos:
        alertas.append({"clase": "otra_persona", "paginas": a["paginas"],
                        "mensaje": f"aparece otro número de documento ({a['numero']}) en las páginas {', '.join(map(str, a['paginas'][:10]))}: revise si son documentos de otra persona"})
    if numero and textos and numero not in donde:
        alertas.append({"clase": "sin_titular", "paginas": [], "mensaje": f"el número del titular ({numero}) no aparece en ningún documento leído"})
    if not numero:
        alertas.append({"clase": "sin_numero", "paginas": [], "mensaje": "el expediente no tiene número de documento del titular"})
    elif ctx.db.scalar(select(func.count()).where(TitularExpediente.proyecto_id == proyecto.id, TitularExpediente.numero_documento == numero,
                                                  TitularExpediente.unidad_id != u.id)):
        otros = list(ctx.db.scalars(select(UnidadDocumental.identificador).join(TitularExpediente, TitularExpediente.unidad_id == UnidadDocumental.id)
                                    .where(TitularExpediente.proyecto_id == proyecto.id, TitularExpediente.numero_documento == numero, TitularExpediente.unidad_id != u.id)))
        alertas.append({"clase": "duplicado", "paginas": [], "mensaje": f"otro expediente tiene el mismo titular ({', '.join(otros[:5])}): revise si son tomos o un duplicado"})
    tipos, estado_hoja = _tipos_de_la_hoja(ctx, u)
    presentes = {_plano(x) for x in tipos}
    obligatorios = list(conf.tipos_obligatorios) if conf else []
    faltan = [x for x in obligatorios if _plano(x) not in presentes]
    if faltan and estado_hoja:
        alertas.append({"clase": "faltan_tipos", "paginas": [],
                        "mensaje": f"faltan {len(faltan)} de los {len(obligatorios)} tipos documentales mínimos de la serie: {', '.join(faltan[:8])}"})
    return {"unidad_id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "titular": como_dict(t),
            "completitud": {"obligatorios": len(obligatorios), "presentes": len(obligatorios) - len(faltan), "faltan": faltan, "hoja": estado_hoja},
            "documentos_encontrados": [{"numero": n, "paginas": p} for n, p in donde.items()], "paginas_leidas": len(textos), "alertas": alertas}


def avisos_hoja(ctx, u: UnidadDocumental) -> list[str]:
    """Los avisos de historias laborales que muestra la validación de la hoja de control."""
    proyecto = ctx.db.get(Proyecto, u.proyecto_id)
    conf = config_de(ctx, proyecto)
    if not aplica(ctx, conf, u):
        return []
    return [f"historia laboral: {a['mensaje']}" for a in revisar(ctx, proyecto, u, conf)["alertas"]]


def expedientes(ctx, proyecto: Proyecto, alerta: str | None = None, desplazamiento: int = 0, limite: int = 100) -> dict[str, Any]:
    conf = config_de(ctx, proyecto)
    unidades = [u for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id).order_by(UnidadDocumental.caja, UnidadDocumental.identificador))
                if aplica(ctx, conf, u)]
    filas = [revisar(ctx, proyecto, u, conf) for u in unidades]
    cuenta = Counter(a["clase"] for f in filas for a in f["alertas"])
    if alerta:
        filas = [f for f in filas if any(a["clase"] == alerta for a in f["alertas"])]
    resumen = {"expedientes": len(unidades), "confirmados": sum(1 for f in filas if f["titular"] and f["titular"]["estado"] == "confirmado"),
               "con_alertas": sum(1 for f in filas if f["alertas"]), "por_clase": dict(cuenta)}
    return {"resumen": resumen, "total": len(filas), "filas": filas[desplazamiento: desplazamiento + limite]}


def proponer_todos(ctx, proyecto: Proyecto) -> int:
    _abierto(proyecto)
    conf = config_de(ctx, proyecto)
    n = 0
    for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)):
        if aplica(ctx, conf, u):
            antes = titular_de(ctx, u)
            if antes is None or antes.estado != "confirmado":
                n += 1 if proponer(ctx, proyecto, u) is not None else 0
    return n


def expedir_lista_chequeo(ctx, proyecto: Proyecto, u: UnidadDocumental):
    """La lista de chequeo de la historia en el formato de la entidad: los tipos mínimos (presentes o no) y los demás de la hoja."""
    from arca.modulos.entregables import servicios as entregables  # noqa: PLC0415

    conf = config_de(ctx, proyecto)
    if not aplica(ctx, conf, u):
        raise TransicionInvalida("Esta unidad no es una historia laboral según la configuración del proyecto")
    if not conf.tipos_obligatorios:
        raise TransicionInvalida("Falta la lista de tipos documentales mínimos en la configuración de historias laborales")
    h = ctx.db.scalar(select(HojaControl).where(HojaControl.unidad_id == u.id))
    if h is None:
        raise TransicionInvalida("La historia no tiene hoja de control: la lista de chequeo sale de ella")
    tramites = list(ctx.db.scalars(select(TramiteHoja).where(TramiteHoja.hoja_id == h.id).order_by(TramiteHoja.orden)))
    r = revisar(ctx, proyecto, u, conf)
    filas, usados = [], set()
    for tipo in conf.tipos_obligatorios:
        t = next((x for x in tramites if _plano(x.tipo_documental) == _plano(tipo)), None)
        if t:
            usados.add(t.id)
        filas.append({"tipo_documental": tipo, "minimo": "Sí", "presente": "Sí" if t else "No", "folio_desde": t.folio_desde if t else None,
                      "folio_hasta": t.folio_hasta if t else None, "fecha": (t.fecha or t.fecha_texto or "S. F.") if t else None,
                      "observacion": "" if t else "No está en el expediente"})
    for t in tramites:
        if t.id not in usados and t.tipo_documental:
            filas.append({"tipo_documental": t.tipo_documental, "minimo": "No", "presente": "Sí", "folio_desde": t.folio_desde, "folio_hasta": t.folio_hasta,
                          "fecha": t.fecha or t.fecha_texto or "S. F.", "observacion": "No es de los tipos mínimos de la serie"})
    for i, f in enumerate(filas, start=1):
        f["numero"] = i
    c = _codigo_clasificacion(ctx, u.id)
    encabezado = {
        "numero_orden": u.numero_orden, "identificador": u.identificador, "codigo_serie": u.codigo_serie, "nombre": u.nombre, "caja": u.caja, "carpeta": u.carpeta,
        "tomo": u.tomo, "otro": u.otro, "folios": u.folios, "soporte": u.soporte, "frecuencia_consulta": u.frecuencia_consulta, "notas": u.notas, "fase": u.fase,
        "fecha_inicial": u.fecha_inicial, "fecha_final": u.fecha_final, "codigo_clasificacion": c[0] if c else "", "serie": "", "subserie": "", "dependencia": "",
        "oficina_productora": "", **entregables.titular_fila(titular_de(ctx, u)),
        "total_obligatorios": r["completitud"]["obligatorios"], "total_presentes": r["completitud"]["presentes"], "total_faltantes": len(r["completitud"]["faltan"]),
        "faltantes": ("Faltan: " + ", ".join(r["completitud"]["faltan"])) if r["completitud"]["faltan"] else "Están todos los tipos mínimos.",
        "estado_hoja": h.estado, "alertas": " · ".join(a["mensaje"] for a in r["alertas"] if a["clase"] != "faltan_tipos"),
    }
    return entregables.expedir_filas(ctx, proyecto, "lista_chequeo", encabezado, filas, f"Lista_chequeo_{u.identificador}", {"lista_chequeo": u.identificador})


def unidad(ctx, proyecto: Proyecto, unidad_id: uuid.UUID) -> UnidadDocumental:
    u = ctx.db.get(UnidadDocumental, unidad_id)
    if u is None or u.proyecto_id != proyecto.id:
        raise NoEncontrado("La unidad no existe")
    return u

