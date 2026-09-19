"""
Revisión de la descripción antes de entregarla.

Esto no es un control de estilo. Es la lista de lo que hace que a un lote se lo devuelvan, y
cada regla está aquí porque quien recibe la revisa en treinta segundos y no necesita más.

Hay dos gravedades y la diferencia importa. DEVUELVE es incumplimiento de norma: el elemento
obligatorio vacío, el título que no identifica la unidad, la fecha que contradice la hoja de
control. Con uno solo de esos la entrega se cae entera, así que la base no se expide como
definitiva mientras quede alguno. REVISE es algo que hay que mirar con el expediente delante
y que solo una persona puede resolver; no bloquea, pero queda escrito con nombre y apellido
para que nadie pueda decir después que no se advirtió.

Ninguna regla de aquí adivina ni corrige sola. Una descripción arreglada por un programa deja
de ser la descripción del archivista, y en un instrumento de entrega eso no se puede.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

# Palabras que por sí solas no son un título: son el nombre de una clase de documento. Un
# título atribuido tiene que identificar ESTA unidad y ninguna otra.
_GENERICAS = {
    "informes", "informe", "oficios", "oficio", "correspondencia", "comunicaciones",
    "estudios", "estudio", "documentos", "documento", "expediente", "expedientes",
    "actas", "acta", "contratos", "contrato", "resoluciones", "resolucion", "carpeta",
    "memorandos", "circulares", "conceptos", "cuentas", "varios", "otros", "general",
    "sin titulo", "sin asunto", "libro", "tomo", "legajo",
}

# Tipos documentales que, si encabezan el título, dicen a qué serie pertenece la unidad. Se
# usan para detectar el título que contradice la subserie con la que quedó clasificada.
_TIPOS = {
    "oficio": "comunicaciones", "oficios": "comunicaciones", "carta": "comunicaciones",
    "correspondencia": "comunicaciones", "memorando": "comunicaciones",
    "circular": "comunicaciones", "telegrama": "comunicaciones",
    "acta": "actas", "actas": "actas",
    "resolucion": "actos administrativos", "resoluciones": "actos administrativos",
    "decreto": "actos administrativos", "acuerdo": "actos administrativos",
    "contrato": "contratos", "contratos": "contratos", "convenio": "contratos",
    "informe": "informes", "informes": "informes",
    "estudio": "estudios", "estudios": "estudios",
    "analisis": "estudios", "ensayo": "estudios", "muestra": "estudios",
    "plano": "cartografia", "planos": "cartografia", "mapa": "cartografia",
}

# Con qué se dice el soporte. El volumen sin soporte está incompleto según 3.1.5.
_SOPORTES = ("papel", "digital", "fotograf", "plano", "microfilm", "cinta", "vidrio",
             "pergamino", "calco", "acetato", "mixto")

DEVUELVE = "DEVUELVE"
REVISE = "REVISE"


@dataclass(frozen=True)
class Hallazgo:
    gravedad: str
    regla: str
    unidad: str
    nivel: str
    que_pasa: str
    como_se_arregla: str


def _limpio(texto) -> str:
    """Sin tildes, sin puntuación, en minúscula: para comparar, nunca para escribir."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9ñ ]+", " ", t).strip()


def _palabras(texto) -> list[str]:
    return [p for p in _limpio(texto).split() if len(p) > 2]


def _tiene_soporte(volumen: str) -> bool:
    v = _limpio(volumen)
    return any(s in v for s in _SOPORTES)


def _familia_del_titulo(titulo: str) -> str:
    """A qué clase de documento apunta el título por su primera palabra significativa."""
    for p in _palabras(titulo):
        if p in _TIPOS:
            return _TIPOS[p]
    return ""


def _familia_de_la_subserie(nombre: str) -> str:
    for p in _palabras(nombre):
        if p in _TIPOS:
            return _TIPOS[p]
    return ""


# ---------------------------------------------------------------------------
# Las reglas
# ---------------------------------------------------------------------------
def _obligatorios(r, hallazgos: list) -> None:
    """
    Los seis elementos que la norma exige en todo nivel. Sin uno de ellos la unidad no está
    descrita, y ahí no hay discusión posible con quien recibe.
    """
    exigidos = [("codigo_referencia", "3.1.1 Código de referencia"),
                ("titulo", "3.1.2 Título"),
                ("fecha_inicial", "3.1.3 Fechas extremas"),
                ("volumen", "3.1.5 Volumen y soporte")]
    # El productor se describe en el fondo y en la sección; los niveles de abajo lo heredan.
    if r.nivel in ("Fondo", "Sección"):
        exigidos.append(("productor", "3.2.1 Nombre del productor"))

    for clave, regla in exigidos:
        if not str(r[clave] or "").strip():
            hallazgos.append(Hallazgo(
                DEVUELVE, regla, r["codigo_referencia"] or "(sin código)", r.nivel,
                "El elemento está vacío y la norma lo exige en todos los niveles.",
                "Complételo antes de entregar. Un obligatorio vacío tumba el lote completo."))


def _volumen_con_soporte(r, hallazgos: list) -> None:
    volumen = str(r["volumen"] or "")
    if volumen and not _tiene_soporte(volumen):
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.1.5 Volumen y soporte", r["codigo_referencia"], r.nivel,
            f"El volumen dice «{volumen[:60]}» pero no dice en qué soporte está.",
            "Agregue el soporte: papel, digital, fotografía, plano. «186 folios» sin más "
            "está incompleto según la norma."))


def _titulo_identifica(r, nombre_subserie: str, hallazgos: list) -> None:
    """
    El título atribuido tiene que identificar ESTA unidad y ninguna otra.

    Un título que repite el nombre de la subserie no describe, clasifica: dice a qué grupo
    pertenece la unidad, que es justamente lo que ya dice la columna de al lado. Y una sola
    palabra genérica —«Informes», «Oficios»— sirve igual para doscientos expedientes, que es
    lo mismo que no servir para ninguno.
    """
    if r.nivel != "Expediente":
        return
    titulo = str(r["titulo"] or "").strip()
    if not titulo:
        return
    limpio = _limpio(titulo)

    # El nombre llega como «SERIE › Subserie»; se parte ANTES de limpiar, porque la limpieza
    # se come el separador y dejaría las dos mitades pegadas.
    solo_subserie = str(nombre_subserie or "").split("›")[-1].strip()
    if solo_subserie and limpio in (_limpio(solo_subserie), _limpio(nombre_subserie)):
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.1.2 Título", r["codigo_referencia"], r.nivel,
            f"El título «{titulo}» es el nombre de la subserie. Eso no describe, clasifica.",
            "Escriba qué documento es, sobre qué asunto y de quién o sobre qué lugar. "
            "Por ejemplo «Informes de análisis de muestras de carbón de la mina El Zulia, "
            "Norte de Santander»."))
        return

    if limpio in _GENERICAS:
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.1.2 Título", r["codigo_referencia"], r.nivel,
            f"«{titulo}» sirve igual para doscientos expedientes, o sea para ninguno.",
            "Un título atribuido identifica una sola unidad. Diga el asunto concreto y, si "
            "lo hay, el lugar o la entidad de la que trata."))
        return

    significativas = [p for p in _palabras(titulo) if p not in _GENERICAS]
    if len(significativas) < 2:
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.1.2 Título", r["codigo_referencia"], r.nivel,
            f"«{titulo}» solo tiene palabras de clase de documento; no dice de qué trata.",
            "Agregue el asunto. La fórmula es qué documento, sobre qué, de quién o dónde."))


def _titulo_no_contradice_la_clasificacion(r, nombre_subserie: str, hallazgos: list) -> None:
    """
    Si el título dice «oficios despachados» y la subserie dice «informes de laboratorio», una
    de las dos está mal, y el que revise lo ve de una. Aquí no se decide cuál: se advierte.
    """
    if r.nivel != "Expediente" or not nombre_subserie:
        return
    del_titulo = _familia_del_titulo(r["titulo"])
    de_la_sub = _familia_de_la_subserie(nombre_subserie)
    if del_titulo and de_la_sub and del_titulo != de_la_sub:
        hallazgos.append(Hallazgo(
            REVISE, "3.1.2 / clasificación", r["codigo_referencia"], r.nivel,
            f"El título apunta a {del_titulo} y la subserie es «{nombre_subserie}», que es de "
            f"{de_la_sub}. Una de las dos está mal.",
            "Mire el expediente y decida. Si de verdad son de la clase que dice el título, "
            "cambie la subserie; si no, corrija el título. No se entrega con las dos."))


def _fechas_coherentes(r, periodo, hallazgos: list) -> None:
    """Las fechas del expediente tienen que caber en el periodo institucional que lo produjo."""
    ini, fin = str(r["fecha_inicial"] or ""), str(r["fecha_final"] or "")
    if ini and fin and fin < ini:
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.1.3 Fechas extremas", r["codigo_referencia"], r.nivel,
            f"La fecha final ({fin}) es anterior a la inicial ({ini}).",
            "Corrija el orden. En un libro empastado las extremas se leen por el orden de "
            "los folios, no por la fecha más antigua y la más reciente."))
        return
    if r.nivel != "Expediente" or not periodo or not ini:
        return
    desde = periodo.fecha_inicio.isoformat() if periodo.fecha_inicio else ""
    hasta = periodo.fecha_fin.isoformat() if periodo.fecha_fin else ""
    if desde and ini < desde or (hasta and fin and fin > hasta):
        hallazgos.append(Hallazgo(
            REVISE, "3.1.3 Fechas extremas", r["codigo_referencia"], r.nivel,
            f"Las fechas ({ini} a {fin or '—'}) se salen del periodo "
            f"{periodo.numero_romano} ({desde} a {hasta}).",
            "O el periodo asignado no es el que corresponde, o el expediente trae documentos "
            "antecedentes de otra época. Si es lo segundo, déjelo dicho en las notas."))


def _fechas_iguales_a_la_hoja(r, extremas_hoja, hallazgos: list) -> None:
    """
    Lo que dice la descripción tiene que ser lo mismo que dice la hoja de control F-GDM-007.

    Es el cotejo más barato que puede hacer quien recibe, y por eso es el primero que hace.
    """
    if r.nivel != "Expediente" or not extremas_hoja:
        return
    ini_hoja, fin_hoja = extremas_hoja
    ini, fin = str(r["fecha_inicial"] or ""), str(r["fecha_final"] or "")
    if ini_hoja and ini and ini != ini_hoja:
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.1.3 contra F-GDM-007", r["codigo_referencia"], r.nivel,
            f"La descripción dice que empieza el {ini} y la hoja de control dice {ini_hoja}.",
            "Iguálelas. Si la hoja está bien, corrija la descripción; si la hoja está mal, "
            "corríjala y vuelva a verificarla."))
    if fin_hoja and fin and fin != fin_hoja:
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.1.3 contra F-GDM-007", r["codigo_referencia"], r.nivel,
            f"La descripción dice que termina el {fin} y la hoja de control dice {fin_hoja}.",
            "Iguálelas antes de entregar."))


def _alcance_aporta(r, hallazgos: list) -> None:
    """
    El alcance y contenido va donde no cabe el título: tipos documentales, asuntos y vacíos.
    Repetir el título con otras palabras no agrega nada y se nota.
    """
    if r.nivel != "Expediente":
        return
    alcance = str(r["alcance"] or "").strip()
    titulo = str(r["titulo"] or "").strip()
    if not alcance:
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.3.1 Alcance y contenido", r["codigo_referencia"], r.nivel,
            "El expediente no tiene alcance y contenido. Sin él esto es un renglón de "
            "inventario, no una descripción.",
            "Escriba qué tipos documentales hay adentro, sobre qué versan y qué falta. "
            "Declarar un vacío —«no aparecen los resultados de las muestras 340 a 352»— "
            "vale más que tres renglones bien redactados."))
        return
    if _limpio(alcance) == _limpio(titulo):
        hallazgos.append(Hallazgo(
            DEVUELVE, "3.3.1 Alcance y contenido", r["codigo_referencia"], r.nivel,
            "El alcance y contenido es el título otra vez.",
            "Ahí va lo que en el título no cabe: los tipos documentales, los asuntos y los "
            "vacíos que usted encontró al foliar."))
        return
    propias = set(_palabras(alcance)) - set(_palabras(titulo))
    if len(propias) < 4:
        hallazgos.append(Hallazgo(
            REVISE, "3.3.1 Alcance y contenido", r["codigo_referencia"], r.nivel,
            "El alcance apenas reformula el título; casi no agrega información propia.",
            "Agregue los tipos documentales y, si los hay, los vacíos de la unidad."))


def _folios_cuadran(r, diferencia: str, hallazgos: list) -> None:
    if r.nivel == "Expediente" and diferencia:
        hallazgos.append(Hallazgo(
            REVISE, "3.1.5 Volumen", r["codigo_referencia"], r.nivel,
            str(diferencia)[:180],
            "Cuente el expediente físico y deje la conclusión escrita. Si la diferencia es "
            "real, tiene que quedar dicha también en el inventario de salida."))


# ---------------------------------------------------------------------------
# La revisión completa
# ---------------------------------------------------------------------------
def revisar(renglones: list, contexto: dict | None = None) -> list[Hallazgo]:
    """
    Pasa toda la base por las reglas y devuelve los hallazgos, los graves primero.

    contexto trae, por código de referencia del expediente, el nombre de su subserie, su
    periodo institucional, las fechas extremas de su hoja de control y la diferencia de
    folios si la hubo. Sin contexto se corren igual las reglas que no lo necesitan.
    """
    ctx = contexto or {}
    hallazgos: list[Hallazgo] = []
    subserie_vigente = ""

    for r in renglones:
        if r.nivel == "Subserie":
            subserie_vigente = str(r["titulo"] or "")
        propio = ctx.get(r["codigo_referencia"], {})
        nombre_sub = propio.get("subserie", subserie_vigente)

        _obligatorios(r, hallazgos)
        _volumen_con_soporte(r, hallazgos)
        _titulo_identifica(r, nombre_sub, hallazgos)
        _titulo_no_contradice_la_clasificacion(r, nombre_sub, hallazgos)
        _fechas_coherentes(r, propio.get("periodo"), hallazgos)
        _fechas_iguales_a_la_hoja(r, propio.get("extremas_hoja"), hallazgos)
        _alcance_aporta(r, hallazgos)
        _folios_cuadran(r, propio.get("diferencia_folios", ""), hallazgos)

    return sorted(hallazgos, key=lambda h: (h.gravedad != DEVUELVE, h.unidad, h.regla))


def contexto_de(db, renglones: list) -> dict:
    """Reúne de la base lo que las reglas necesitan saber de cada expediente."""
    from app.models import Expediente, Periodo, Serie, Subserie, Tramite

    codigos = [r["codigo_referencia"] for r in renglones if r.nivel == "Expediente"]
    if not codigos:
        return {}
    expedientes = (db.query(Expediente)
                     .filter(Expediente.codigo_referencia.in_(codigos)).all())
    periodos = {p.id: p for p in db.query(Periodo).all()}
    subseries = {s.id: s for s in db.query(Subserie).all()}
    series = {s.id: s for s in db.query(Serie).all()}

    salida = {}
    for e in expedientes:
        fechas = [t.fecha for t in db.query(Tramite)
                  .filter(Tramite.expediente_id == e.id).all() if t.fecha]
        sub = subseries.get(e.subserie_id)
        nombre = ""
        if sub:
            serie = series.get(sub.serie_id)
            nombre = f"{serie.nombre} › {sub.nombre}" if serie else sub.nombre
        salida[e.codigo_referencia] = {
            "subserie": nombre,
            "periodo": periodos.get(e.periodo_id),
            "extremas_hoja": ((min(fechas).isoformat(), max(fechas).isoformat())
                              if fechas else None),
            "diferencia_folios": e.diferencia_folios or "",
        }
    return salida


def resumen(hallazgos: list[Hallazgo]) -> dict:
    graves = [h for h in hallazgos if h.gravedad == DEVUELVE]
    return {
        "se_puede_entregar": not graves,
        "devuelve": len(graves),
        "revise": len(hallazgos) - len(graves),
        "unidades_con_problema": len({h.unidad for h in hallazgos}),
        "por_regla": _por_regla(hallazgos),
        "fecha": date.today().isoformat(),
    }


def _por_regla(hallazgos: list[Hallazgo]) -> dict:
    cuenta: dict[str, int] = {}
    for h in hallazgos:
        cuenta[h.regla] = cuenta.get(h.regla, 0) + 1
    return dict(sorted(cuenta.items(), key=lambda kv: -kv[1]))
