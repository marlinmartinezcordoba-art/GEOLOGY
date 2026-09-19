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
from datetime import date

from sqlalchemy.orm import Session

from app.services.codigos import construir_codigo_referencia

REGLAS = "NTC 4095:2013 / ISAD(G) 2.ª edición"
# Equivalencia confirmada por la dirección del proyecto el 9 de septiembre de 2026.
CENTIMETROS_POR_CIEN_FOLIOS = 1.0
INSTRUMENTOS = ("F-GDM-003 V9 formato único de inventario documental; F-GDM-007 V4 hoja de "
                "control; base de descripción ISAD(G)")
LENGUA = "Español"
FORMA_INGRESO = "Transferencia secundaria"
MARCA_PROPUESTA = "[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN] "


def construir_descripcion(db: Session, exp, quien, propuesta: dict | None = None) -> None:
    """
    Completa los veintiséis elementos del expediente. `propuesta` es lo que el modelo de
    lenguaje sugirió tras leer el documento; puede venir vacía y la descripción igual se
    construye, porque nada esencial depende del modelo.
    """
    from app.models import Periodo, Seccion, Serie, Subserie

    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    serie = db.get(Serie, sub.serie_id) if sub else None
    seccion = db.get(Seccion, serie.seccion_id) if serie else None
    periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
    romano = periodo.numero_romano if periodo else ""

    # 3.1.1  Código de referencia (R4)
    consecutivo = _siguiente_consecutivo(db, romano)
    exp.codigo_referencia = construir_codigo_referencia(
        romano, sub.codigo if sub else "", serie.codigo if serie else "", consecutivo)

    # 3.1.2  Título atribuido. Lo propone el modelo; si no hay propuesta se arma con el
    #        asunto del inventario, que es información verificable.
    #
    #        El campo 7 de la hoja de control NO sirve aquí y por eso no se mira. Es corto y
    #        genérico a propósito —«Estudios de laboratorio»— porque identifica el expediente
    #        dentro de su carpeta; el 3.1.2 tiene que identificarlo dentro de todo el fondo.
    #        Un título que vale para doscientos expedientes vale para ninguno, y es la
    #        primera razón por la que devuelven un lote.
    if not exp.titulo:
        sugerido = (propuesta or {}).get("titulo")
        exp.titulo = ((MARCA_PROPUESTA + sugerido) if not texto_vacio_del_modelo(sugerido)
                      else _titulo_atribuido(db, exp, sub, seccion))

    # 3.1.4 y 3.1.5
    exp.nivel_descripcion = exp.nivel_descripcion or "Unidad documental"
    if exp.tramites:
        exp.volumen_folios = exp.volumen_folios or max((t.folio_hasta or 0) for t in exp.tramites)
    exp.soporte = exp.soporte or (sub.soporte if sub and sub.soporte else "Papel")
    exp.metros_lineales = exp.metros_lineales or metros_lineales(exp.volumen_folios)

    # 3.2  Contexto. Se hereda del periodo para no repetirlo en cada unidad (R33)
    if periodo:
        exp.historia_institucional = exp.historia_institucional or periodo.historia_institucional
        exp.caracteristicas_fisicas = exp.caracteristicas_fisicas or periodo.caracteristicas_fisicas
        if not exp.historia_archivistica:
            exp.historia_archivistica = _historia_archivistica(exp, periodo)
        if not exp.nombre_productor:
            exp.nombre_productor = _productor(
                periodo.entidad_productora,
                seccion.unidad_administrativa if seccion else None,
                seccion.oficina_productora if seccion else None)
    exp.forma_ingreso = exp.forma_ingreso or FORMA_INGRESO

    # 3.3  Contenido y estructura
    if not exp.alcance_contenido:
        sugerido = (propuesta or {}).get("alcance_contenido")
        exp.alcance_contenido = ((MARCA_PROPUESTA + sugerido)
                                 if not texto_vacio_del_modelo(sugerido)
                                 else _alcance_desde_tramites(exp))
    if not exp.valoracion and sub:                                   # R26
        exp.valoracion = _valoracion(sub, serie, romano, periodo)
    if not exp.organizacion:
        sugerido = (propuesta or {}).get("organizacion")
        exp.organizacion = ((MARCA_PROPUESTA + sugerido) if not texto_vacio_del_modelo(sugerido)
                            else _organizacion(exp))
    if not exp.notas:
        sugerido = (propuesta or {}).get("notas")
        # Las notas sí pueden quedar vacías: la norma no obliga a escribir algo aquí, y es
        # preferible el silencio a un «sin observaciones» que no aporta nada.
        exp.notas = None if texto_vacio_del_modelo(sugerido) else (MARCA_PROPUESTA + sugerido)
    exp.nuevos_ingresos = exp.nuevos_ingresos or "No se esperan nuevos ingresos: fondo acumulado cerrado."

    # 3.4  Condiciones de acceso y uso
    exp.condiciones_acceso = exp.condiciones_acceso or (
        "Documento público. Consulta en sala del Archivo Central del Servicio Geológico Colombiano.")
    exp.condiciones_reproduccion = exp.condiciones_reproduccion or (
        "Reproducción permitida citando la fuente, sujeta al estado de conservación del soporte.")
    exp.lengua = exp.lengua or LENGUA
    exp.instrumentos_descripcion = exp.instrumentos_descripcion or INSTRUMENTOS

    # 3.5  Documentación asociada
    exp.existencia_originales = exp.existencia_originales or (
        "Original en el Archivo Central del Servicio Geológico Colombiano.")
    exp.existencia_copias = exp.existencia_copias or "No se conocen copias."

    # 3.7  Control de la descripción
    exp.reglas_normas = exp.reglas_normas or REGLAS
    exp.fecha_descripcion = exp.fecha_descripcion or date.today()
    exp.nota_archivero = exp.nota_archivero or f"Descripción elaborada por {quien.nombre}."


def metros_lineales(folios) -> float | None:
    """
    Elemento 3.1.5. Extensión de la unidad en metros lineales.

    Cien folios ocupan un centímetro de estante, equivalencia confirmada por la dirección
    del proyecto. Un expediente de trescientos folios da 0,03 metros lineales. El F-GDM-003
    pide la extensión y el inventario de salida también, así que no basta con los folios.
    """
    try:
        n = int(folios or 0)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    centimetros = (n / 100.0) * CENTIMETROS_POR_CIEN_FOLIOS
    return round(centimetros / 100.0, 4)


def _siguiente_consecutivo(db: Session, romano: str) -> int:
    from app.models import Expediente
    prefijo = f"CO-SGC-AC-P{romano}-"
    return db.query(Expediente).filter(Expediente.codigo_referencia.like(prefijo + "%")).count() + 1


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

    Es lo que permite titular «Informes de análisis químico de la Sección de Laboratorio» en
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
    """«la Sección de Laboratorio», «el Instituto Geológico Nacional»."""
    o = str(oficina or "").strip()
    if not o:
        return ""
    femeninas = ("seccion", "sección", "division", "división", "comision", "comisión",
                 "direccion", "dirección", "oficina", "unidad", "subdireccion", "subdirección",
                 "gerencia", "secretaria", "secretaría")
    articulo = "la " if o.lower().startswith(femeninas) else "el "
    return articulo + o


def _titulo_atribuido(db: Session, exp, sub, seccion=None) -> str:
    """
    Elemento 3.1.2. Título atribuido.

    Si el asunto del inventario de origen dice algo, se respeta. Pero en un fondo acumulado
    la mayoría de los asuntos son inservibles como título: «CORRESPONDENCIA», «OFICIOS
    DESPACHADOS», o el nombre de la subserie repetido. En esos casos se construye un título
    de verdad con la naturaleza predominante de los trámites, la oficina productora y las
    fechas extremas en prosa, que es lo que la norma pide y lo que sirve para consultar.
    """
    from app.models import UnidadInventario
    from app.services.codigos import normalizar_texto
    from app.services.fechas import rango_en_letras

    unidad = (db.query(UnidadInventario)
                .filter(UnidadInventario.codigo_carpeta == exp.codigo_carpeta).first())
    asunto = (unidad.asunto or "").strip() if unidad else ""

    normalizado = normalizar_texto(asunto)
    generico = (
        not normalizado
        or (sub and normalizado == normalizar_texto(sub.nombre))
        or bool(_GENERICOS.match(normalizado))
        or len(asunto.split()) <= 2)

    if not generico:
        return asunto[0].upper() + asunto[1:]

    base, _ = naturaleza_predominante(exp.tramites)
    if not base:
        base = (sub.nombre if sub else asunto or exp.codigo_carpeta).lower()

    oficina = _con_articulo(seccion.oficina_productora if seccion else "")
    enlace = " por " if "recibid" in base else " de "
    titulo = base[0].upper() + base[1:] + (f"{enlace}{oficina}" if oficina else "")

    fechas = rango_en_letras(exp.fecha_inicial, exp.fecha_final)
    return f"{titulo}, {fechas}" if fechas else titulo


def _historia_archivistica(exp, periodo) -> str:
    traza = []
    if exp.caja_origen:
        traza.append(f"Recibida en la caja {exp.caja_origen} del Archivo Central del Servicio "
                     "Geológico Colombiano")
    if exp.caja_trabajo:
        traza.append(f"intervenida en la caja de trabajo {exp.caja_trabajo}")
    cola = ("; ".join(traza) + " en el marco del contrato 733 de 2026.") if traza else ""
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
        from app.services.fechas import fecha_en_letras
        cita = (f", convalidada por el Archivo General de la Nación el "
                f"{fecha_en_letras(convalidacion)}")
    else:
        cita = " convalidada"

    texto = (f"{leer_disposicion(codigo)} según la Tabla de Valoración Documental del periodo "
             f"{romano}{cita}, subserie {sub.codigo} {sub.nombre}.")
    if retencion is not None:
        texto += f" Retención en archivo central: {retencion} años."
    return texto
