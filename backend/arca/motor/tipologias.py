"""
Calidad de la columna «tipo documental» de la hoja de control.

POR QUÉ ESTA COLUMNA Y NO OTRA. La hoja de control es el instrumento con el que alguien va a
buscar dentro del expediente dentro de treinta años. Lo que esté escrito ahí es lo que va a
encontrar. Si el mismo tipo documental aparece escrito de tres maneras a lo largo del fondo,
quien busque «informe de análisis» no encuentra los que quedaron como «Informe analisis», y
el instrumento falla justo en lo único que tenía que hacer.

CÓMO SE PARTE LO QUE HAY ESCRITO. El equipo escribe la casilla así:

    Informe de visita técnica - Predio La Esperanza, vereda El Retiro, radicado 1234
    └──────── el TIPO ───────┘   └──────────────── el DETALLE ─────────────────┘

El tipo es la clase de documento y tiene que ser el mismo en todo el fondo. El detalle es lo
que distingue a ESE trámite de los demás y no se toca ni una letra: ahí viven los números,
los nombres propios y los lugares, que es lo que de verdad sirve para buscar. La
normalización se aplica ÚNICAMENTE a la parte de la izquierda.

DE DÓNDE SALE LA FORMA CORRECTA. No de una lista que alguien inventó, sino de la tabla de
valoración convalidada. Si la subserie se llama «Informes de Visitas Técnicas», el tipo
documental de sus trámites es «Informe de visita técnica». La tabla es la
autoridad; esto solo la aplica.

Y NADA SE CAMBIA SOLO. Este módulo agrupa las variantes y propone una forma unificada. Quien
decide es una persona, por lote, viendo qué se va a cambiar y en cuántos trámites.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# Con qué separa el equipo el tipo del detalle. El guion largo y el corto conviven en las
# hojas porque Word cambia uno por otro sin avisar.
SEPARADORES = (" - ", " – ", " — ", ": ", " | ", " · ")

# Palabras que no distinguen un tipo de otro y que solo estorban al comparar variantes.
_VACIAS = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "Y", "EN", "CON", "POR", "PARA", "AL",
           "UN", "UNA", "SOBRE", "SU", "SUS", "A"}

# Señales de que en la casilla del tipo se metió algo que pertenece a otra columna.
_ESTADO_DEL_PAPEL = ("ROTO", "ROTA", "MANCHAD", "DETERIOR", "ILEGIBLE", "HUMEDAD", "HONGO",
                     "RASGAD", "QUEMAD", "DESCOLORID", "FALTA EL FOLIO", "FALTAN FOLIOS")
_FOLIACION = re.compile(r"\bFOLIOS?\s*\d|\bF\.?\s*\d{1,4}\s*(?:AL?|-)\s*\d{1,4}\b")

# Palabras cortas que van en mayúscula por énfasis y no son siglas.
_NO_SON_SIGLAS = {"ANEXO", "TOMO", "PARTE", "FOLIO", "NOTA", "ACTA", "PLAN", "ETC", "VER",
                  "SIN", "NO", "SI", "MES", "ANO", "DIA", "SGDEA"}

# Cómo se pasa a singular la palabra que nombra la clase de documento. El español no tiene
# una regla única —«informes» sale de «informe» y «papeles» de «papel», y las dos terminan
# igual—, así que se resuelven primero las terminaciones inequívocas y después se listan las
# cabezas que de verdad aparecen en la tabla convalidada de este fondo. Lo que no esté aquí
# pierde la ese final, que acierta en la gran mayoría.
_SINGULARES = {
    "INFORMES": "Informe", "ESTUDIOS": "Estudio", "ACTAS": "Acta", "CONTRATOS": "Contrato",
    "PROGRAMAS": "Programa", "LIBROS": "Libro", "PROYECTOS": "Proyecto",
    "COMPROBANTES": "Comprobante", "CUENTAS": "Cuenta", "PROCESOS": "Proceso",
    "CERTIFICADOS": "Certificado", "INVENTARIOS": "Inventario", "ACUERDOS": "Acuerdo",
    "CONVENIOS": "Convenio", "HISTORIAS": "Historia", "HISTORIALES": "Historial",
    "NOVEDADES": "Novedad", "ORDENES": "Orden", "PROPUESTAS": "Propuesta",
    "FICHAS": "Ficha", "CONCEPTOS": "Concepto", "BALANCES": "Balance",
    "ANALISIS": "Análisis", "CORRESPONDENCIA": "Correspondencia", "NOMINA": "Nómina",
    "CATALOGO": "Catálogo", "CAJA": "Caja", "PLAN": "Plan", "PROGRAMA": "Programa",
}

# Por encima de esto, lo que hay en la casilla ya no es un tipo documental: es el asunto.
TOPE_DEL_TIPO = 80


@dataclass
class Variante:
    """Una forma en que quedó escrito un tipo documental, y cuántas veces."""
    texto: str
    veces: int
    tramites: list = field(default_factory=list)       # (carpeta, no_item)


@dataclass
class Grupo:
    """Todas las formas del MISMO tipo documental, con la que se propone unificar."""
    raices: tuple
    variantes: list
    propuesta: str
    de_la_tabla: bool = False
    subserie: str = ""

    @property
    def veces(self) -> int:
        return sum(v.veces for v in self.variantes)

    @property
    def hay_que_cambiar(self) -> int:
        """Cuántos trámites quedarían distintos de como están hoy."""
        return sum(v.veces for v in self.variantes if v.texto != self.propuesta)

    @property
    def porque(self) -> str:
        if self.de_la_tabla:
            return (f"La tabla convalidada llama a esta subserie «{self.subserie}». El tipo "
                    "documental de sus trámites se escribe en singular a partir de ese nombre.")
        if len(self.variantes) > 1:
            return (f"El mismo tipo quedó escrito de {len(self.variantes)} maneras. Se propone "
                    "la más frecuente y completa.")
        return "Se corrige la escritura: mayúscula solo al principio."


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def partir(tipo: str) -> tuple[str, str]:
    """
    Separa el tipo documental del detalle del trámite.

    Se corta por el PRIMER separador, porque el detalle suele traer más guiones adentro y
    cortando por el último se llevaría medio detalle para el lado del tipo.
    """
    texto = str(tipo or "").strip()
    posiciones = [(texto.find(s), s) for s in SEPARADORES if texto.find(s) > 0]
    if not posiciones:
        return texto, ""
    corte, separador = min(posiciones)
    return texto[:corte].strip(), texto[corte + len(separador):].strip()


def _raices(tipo: str) -> tuple:
    """Las palabras con contenido, para reconocer dos formas del mismo tipo."""
    limpio = re.sub(r"[^A-Z0-9 ]", " ", _sin_tildes(tipo).upper())
    return tuple(sorted({p for p in limpio.split() if p and p not in _VACIAS and len(p) > 2}))


def como_sustantivo(texto: str) -> str:
    """
    Mayúscula solo en la primera letra, como se escribe un tipo documental.

    Las siglas se respetan: «Informe de laboratorio del ICA» no se vuelve «del ica». Se
    reconocen porque vienen enteras en mayúscula y son cortas, que es como se escriben.
    """
    palabras = str(texto or "").strip().split()
    if not palabras:
        return ""
    salida = []
    for p in palabras:
        letras = re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]", "", p)
        # Una sigla va entera en mayúscula, es corta y NO es una palabra corriente. Sin esta
        # última comprobación, «DE» y «DEL» pasaban por siglas y quedaban gritando en mitad
        # del tipo documental.
        es_sigla = (len(letras) > 1 and letras.isupper() and len(letras) <= 5
                    and _sin_tildes(letras).upper() not in _VACIAS
                    and _sin_tildes(letras).upper() not in _NO_SON_SIGLAS)
        salida.append(p if es_sigla else p.lower())
    primera = salida[0]
    salida[0] = primera[:1].upper() + primera[1:]
    return " ".join(salida)


def desde_la_subserie(nombre_subserie: str) -> str:
    """
    El tipo documental que corresponde al nombre de la subserie, en singular.

    «Informes de Visitas Técnicas» da «Informe de visitas técnicas». Se
    singulariza únicamente la PRIMERA palabra, que es la que nombra la clase de documento;
    las demás son complemento y en la tabla ya vienen como van.
    """
    nombre = str(nombre_subserie or "").split("›")[-1].strip()
    if not nombre or nombre.upper() in ("N/A", "NA", ""):
        return ""
    # Se pasa a singular la cabeza y los adjetivos que concuerdan con ella, y se para en la
    # primera preposición: en «Contratos de Prestación de Servicios» lo que va después del
    # «de» es complemento y conserva su número, mientras que en «Libros Contables Auxiliares»
    # los tres van juntos y los tres tienen que cambiar.
    palabras = nombre.split()
    salida, sigo = [], True
    for i, palabra in enumerate(palabras):
        if sigo and _sin_tildes(palabra).upper() in _PREPOSICIONES:
            sigo = False
        salida.append(_singular(palabra) if (sigo or i == 0) else palabra)
    return como_sustantivo(" ".join(salida))


_PREPOSICIONES = {"DE", "DEL", "PARA", "EN", "CON", "POR", "A", "AL", "Y", "SOBRE"}


def _singular(palabra: str) -> str:
    """La palabra que nombra la clase de documento, en singular."""
    llave = _sin_tildes(palabra).upper()
    if llave in _SINGULARES:
        return _SINGULARES[llave]
    bajo = palabra.lower()
    if bajo.endswith("ciones"):
        return palabra[:-6] + "ción"                # Resoluciones → Resolución
    if bajo.endswith("siones"):
        return palabra[:-6] + "sión"
    if bajo.endswith("ines"):
        return palabra[:-4] + "ín"                  # Boletines → Boletín
    if bajo.endswith("sis"):
        return palabra                              # Análisis no cambia
    # Aquí el español no perdona. «Auxiliares» pierde las dos letras y queda «auxiliar»,
    # pero «contables» pierde solo la ese y queda «contable»; las dos terminan en «les» y se
    # comportan distinto. Por eso se listan las terminaciones, en vez de mirar una letra.
    if len(palabra) > 4:
        if bajo.endswith(("bles", "ntes", "ntes")):
            return palabra[:-1]                     # contables → contable
        if bajo.endswith(("ales", "ares", "iles", "ores", "eres", "anes", "ades", "udes",
                          "ones", "ises", "oles", "ules")):
            return palabra[:-2]                     # auxiliares → auxiliar
    if len(palabra) > 3 and bajo.endswith("s"):
        return palabra[:-1]
    return palabra


def _mejor_variante(variantes: list) -> str:
    """
    Cuál de las formas escritas se toma como buena.

    Primero la que más veces se escribió, porque es la que el equipo usa de verdad. Entre las
    que empatan, la que tiene más palabras: «Informe de análisis» dice más que «Informe
    análisis», y lo que falta casi siempre es la preposición.
    """
    return max(variantes, key=lambda v: (v.veces, len(v.texto.split()), -len(v.texto))).texto


def agrupar(tramites: list, subserie_por_carpeta: dict | None = None) -> list[Grupo]:
    """
    Reúne las formas del mismo tipo documental y propone con cuál unificarlas.

    tramites   iterable de (carpeta, no_item, tipo_documental)
    """
    por_raiz: dict = defaultdict(list)
    subserie_de = subserie_por_carpeta or {}
    subseries_del_grupo: dict = defaultdict(Counter)

    for carpeta, no_item, tipo in tramites:
        cabeza, detalle = partir(tipo)
        if not cabeza:
            continue
        # Cuando la casilla trae el asunto entero, sin separador, no se propone nada: bajarle
        # las mayúsculas a «predio La Esperanza» o a «Jefe de la Oficina de Planeación»
        # destruiría los nombres propios. Eso sale como reparo de fondo y lo reescribe una
        # persona, que es la única que sabe dónde termina el tipo y dónde empieza el asunto.
        if not detalle and len(cabeza) > TOPE_DEL_TIPO:
            continue
        raices = _raices(cabeza)
        if not raices:
            continue
        por_raiz[raices].append((carpeta, no_item, cabeza))
        if subserie_de.get(carpeta):
            subseries_del_grupo[raices][subserie_de[carpeta]] += 1

    grupos = []
    for raices, filas in por_raiz.items():
        cuenta = Counter(c for _, _, c in filas)
        variantes = [Variante(texto=texto, veces=veces,
                              tramites=[(c, n) for c, n, t in filas if t == texto])
                     for texto, veces in cuenta.most_common()]

        # Si todas las carpetas del grupo son de la misma subserie, la tabla convalidada manda.
        subserie, de_la_tabla, propuesta = "", False, ""
        candidatas = subseries_del_grupo.get(raices)
        if candidatas and len(candidatas) == 1:
            subserie = next(iter(candidatas))
            desde_tabla = desde_la_subserie(subserie)
            if desde_tabla and _raices(desde_tabla) == raices:
                propuesta, de_la_tabla = desde_tabla, True

        if not propuesta:
            propuesta = como_sustantivo(_mejor_variante(variantes))

        grupos.append(Grupo(raices=raices, variantes=variantes, propuesta=propuesta,
                            de_la_tabla=de_la_tabla, subserie=subserie))

    grupos.sort(key=lambda g: (-g.hay_que_cambiar, -g.veces))
    return grupos


# ---------------------------------------------------------------------------
# Lo que está mal y no es cuestión de escritura
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Reparo:
    carpeta: str
    no_item: int
    que_dice: str
    problema: str
    que_hacer: str


def reparos(tramites: list) -> list[Reparo]:
    """
    Lo que hay en la casilla y no debería estar ahí.

    Son tres cosas distintas y se arreglan distinto: el estado del papel, que va en
    observaciones; la foliación, que ya tiene sus dos columnas; y el asunto entero metido
    donde iba el tipo, que no es un error de escritura sino de criterio.
    """
    salida = []
    for carpeta, no_item, tipo in tramites:
        texto = str(tipo or "").strip()
        if not texto:
            continue
        cabeza, detalle = partir(texto)
        arriba = _sin_tildes(texto).upper()

        if any(m in arriba for m in _ESTADO_DEL_PAPEL):
            salida.append(Reparo(
                carpeta, no_item, texto[:110],
                "El estado del papel está escrito en el tipo documental.",
                "Pásela a la columna Observaciones, que es donde van las novedades, "
                "alteraciones y faltantes de la carpeta."))
            continue

        if _FOLIACION.search(arriba):
            salida.append(Reparo(
                carpeta, no_item, texto[:110],
                "La foliación está escrita dentro del tipo documental.",
                "Los folios van en las columnas 12.1 Desde y 12.2 Hasta, no en el texto."))
            continue

        if not detalle and len(cabeza) > TOPE_DEL_TIPO:
            salida.append(Reparo(
                carpeta, no_item, texto[:110],
                f"La casilla trae {len(cabeza)} caracteres de corrido y sin separador: eso "
                "es el asunto del trámite, no su tipo documental.",
                "Escríbalo como «Tipo documental - detalle del trámite». El tipo es la clase "
                "de documento; el detalle es lo que distingue a este de los demás."))
    return salida
