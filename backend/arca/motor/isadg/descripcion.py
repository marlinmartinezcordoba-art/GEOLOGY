"""
Construcción de la descripción ISAD(G).  Reglas R4, R26, R32 a R38.

Todo lo que se puede deducir se deduce con código, no con un modelo de lenguaje: el código
de referencia, la valoración tomada de la tabla convalidada, las fechas extremas, el volumen,
la lengua, la forma de ingreso y el contexto heredado del periodo.

Al modelo de lenguaje se le deja solo lo que exige leer el documento, que son el título
atribuido y el alcance y contenido, y siempre como PROPUESTA marcada, nunca escrita
directamente como descripción aprobada.
"""
from __future__ import annotations

import re

REGLAS = "NTC 4095:2013 / ISAD(G) 2.ª edición"
# Equivalencia por defecto; cada proyecto puede fijar la suya.
CENTIMETROS_POR_CIEN_FOLIOS = 1.0
# Instrumentos de descripción por defecto; cada proyecto los nombra según sus propias plantillas.
INSTRUMENTOS = "Formato único de inventario documental; hoja de control; base de descripción ISAD(G)"
LENGUA = "Español"
FORMA_INGRESO = "Transferencia secundaria"
MARCA_PROPUESTA = "[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN] "


def metros_lineales(folios) -> float | None:
    """
    Elemento 3.1.5. Extensión de la unidad en metros lineales.

    Cien folios ocupan un centímetro de estante (equivalencia por defecto). Un expediente de trescientos folios da 0,03 metros lineales. El FUID
    pide la extensión, así que no basta con los folios.
    """
    try:
        n = int(folios or 0)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    centimetros = (n / 100.0) * CENTIMETROS_POR_CIEN_FOLIOS
    return round(centimetros / 100.0, 4)


def _productor(*partes) -> str:
    """
    Elemento 3.2.1. Entidad, unidad administrativa y oficina productora, en ese orden y sin
    repetir. En muchas secciones del fondo la unidad administrativa y la oficina productora
    traen el mismo nombre, y escribirlo dos veces seguidas ensucia la descripción.
    """
    limpias: list[str] = []
    for x in partes:
        t = str(x or "").strip().rstrip(".")
        if t and not any(p.upper() == t.upper() for p in limpias):
            limpias.append(t)
    return ". ".join(limpias)


_GENERICOS = re.compile(
    r"^(OFICIOS?(DESPACHADOS?|RECIBIDOS?)?|CORRESPONDENCIA|INFORMES?|COMUNICACIONES?|"
    r"ACTAS?|CONTRATOS?|DOCUMENTOS?|EXPEDIENTES?|VARIOS|GENERAL(ES)?|SINASUNTO)$")


def texto_vacio_del_modelo(t) -> bool:
    """
    Detecta las salidas del modelo que no dicen nada.

    Un modelo que no encuentra qué escribir suele devolver «pendiente», «sin evidencia» o
    «no aplica» en vez de una cadena vacía. Sin esta guarda esos textos entraban a la
    descripción como si fueran contenido y quedaban archivados así.
    """
    x = str(t or "").strip()
    if not x:
        return True
    return bool(re.match(
        r"^(pendiente|sin (evidencia|informaci[oó]n|determinar|datos)|no (se evidencia|aplica|"
        r"disponible|determinado)|n/?a|ninguno?|desconocido)\b", x, re.IGNORECASE))


def naturaleza_predominante(tramites) -> tuple[str, float]:
    """
    El tipo documental que más se repite en la hoja de control, en plural.

    Es lo que permite titular «Informes de visitas técnicas de la Oficina de Planeación» en
    vez de repetir el nombre de la subserie.

    Se agrupa por las dos primeras palabras con contenido, porque agrupar por la frase
    completa deja a «oficio despachado al Ministerio» y «oficio despachado a la Gobernación»
    como dos naturalezas distintas y ninguna llega a ser predominante. Para escribir el
    título se usa la parte que todos los trámites del grupo tienen en común, que conserva el
    «químico» de «informes de análisis químico» sin arrastrar el asunto de cada uno.
    """
    enlaces = {"de", "del", "la", "el", "los", "las", "a", "al", "en", "con", "por",
               "para", "y", "sobre", "un", "una", "sus", "su"}

    grupos: dict[str, list[list[str]]] = {}
    for t in tramites:
        base = re.sub(r"[,;:.].*$", "", str(getattr(t, "tipo_documental", "") or "")).strip()
        palabras = [w for w in base.lower().split() if w]
        if not palabras:
            continue
        contenido = [w for w in palabras if w not in enlaces][:2]
        if not contenido:
            continue
        grupos.setdefault(" ".join(contenido), []).append(palabras)

    if not grupos:
        return "", 0.0

    clave = max(grupos, key=lambda k: len(grupos[k]))
    frases = grupos[clave]

    # Lo que todas las frases del grupo comparten al comienzo, hasta seis palabras.
    comun: list[str] = []
    for i in range(min(6, min(len(f) for f in frases))):
        palabra = frases[0][i]
        if all(f[i] == palabra for f in frases):
            comun.append(palabra)
        else:
            break
    while comun and comun[-1] in enlaces:
        comun.pop()
    texto = " ".join(comun) or clave

    texto = re.sub(r"^oficio (despachado|recibido)", r"oficios \1s", texto)
    texto = re.sub(r"^informe\b", "informes", texto)
    texto = re.sub(r"^acta\b", "actas", texto)
    texto = re.sub(r"^comunicaci[oó]n\b", "comunicaciones", texto)
    texto = re.sub(r"^solicitud\b", "solicitudes", texto)
    texto = re.sub(r"^resoluci[oó]n\b", "resoluciones", texto)
    return texto, len(frases) / len(tramites)


def _con_articulo(oficina: str) -> str:
    """«la Oficina de Planeación», «el Departamento Administrativo»."""
    o = str(oficina or "").strip()
    if not o:
        return ""
    femeninas = ("seccion", "sección", "division", "división", "comision", "comisión",
                 "direccion", "dirección", "oficina", "unidad", "subdireccion", "subdirección",
                 "gerencia", "secretaria", "secretaría")
    articulo = "la " if o.lower().startswith(femeninas) else "el "
    return articulo + o


def _historia_archivistica(exp, periodo) -> str:
    traza = []
    if exp.caja_origen:
        traza.append(f"Recibida en la caja de origen {exp.caja_origen}")
    if exp.caja_trabajo:
        traza.append(f"intervenida en la caja de trabajo {exp.caja_trabajo}")
    cola = ("; ".join(traza) + ".") if traza else ""
    return " ".join(x for x in ((periodo.historia_archivistica or ""), cola) if x).strip()


def _alcance_desde_tramites(exp) -> str:
    tipos = []
    for t in exp.tramites:
        tipo = (t.tipo_documental or "").strip()
        if tipo and tipo.lower() not in [x.lower() for x in tipos]:
            tipos.append(tipo)
    if not tipos:
        return "Unidad documental sin trámites descritos."
    listado = "; ".join(tipos[:12]) + ("…" if len(tipos) > 12 else "")
    return f"La unidad reúne {len(exp.tramites)} trámites que comprenden: {listado}."


def _organizacion(exp) -> str:
    folios = exp.volumen_folios or 0
    return (f"Ordenación cronológica de los trámites, con foliación continua de "
            f"{folios} folios.")


def leer_disposicion(codigo: str) -> str:
    """
    Traduce la sigla de disposición final de la tabla de valoración a lo que significa.

    En las tablas del contrato la casilla trae CT, E, S o M, a veces combinadas como CT/M.
    Escribir «disposición final CT» en el elemento 3.3.2 obliga a quien consulte a tener la
    tabla al lado; escribir «Conservación total con reproducción técnica» no.
    """
    c = str(codigo or "").upper()
    if "CT" in c:
        texto = "Conservación total"
    elif "S" in c:
        texto = "Selección"
    elif "E" in c:
        texto = "Eliminación"
    else:
        return "Disposición final sin determinar en la tabla de valoración"
    if "M" in c:
        texto += " con reproducción técnica (microfilmación o digitalización)"
    return texto


def _valoracion(sub, serie, romano: str, periodo=None) -> str:
    """
    Elemento 3.3.2, valoración, selección y eliminación.

    La disposición final se hereda de la tabla de valoración convalidada; nunca se deduce ni
    se inventa. Se cita la convalidación por el Archivo General de la Nación porque es lo que
    da sustento normativo a la disposición aplicada.
    """
    retencion = sub.retencion_central_anios
    if retencion is None and serie:
        retencion = serie.retencion_central_anios
    codigo = sub.disposicion_final or (serie.disposicion_final if serie else "")

    convalidacion = getattr(periodo, "fecha_convalidacion_tvd", None) if periodo else None
    if convalidacion:
        from arca.motor.fechas import fecha_en_letras
        cita = (f", convalidada por el Archivo General de la Nación el "
                f"{fecha_en_letras(convalidacion)}")
    else:
        cita = " convalidada"

    texto = (f"{leer_disposicion(codigo)} según la Tabla de Valoración Documental del periodo "
             f"{romano}{cita}, subserie {sub.codigo} {sub.nombre}.")
    if retencion is not None:
        texto += f" Retención en archivo central: {retencion} años."
    return texto
