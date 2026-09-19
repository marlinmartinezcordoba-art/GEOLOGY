"""
Clasificación contra la tabla de valoración documental.  Reglas R22 a R26.

Transcripción de asimilarEncabezadoATvd_, buscarSubserieEnCualquierPeriodo_ y
valoracionSegunTvd_ del motor anterior. La lista de subseries es cerrada: el sistema
no inventa series ni subseries que no estén en la tabla convalidada.
"""
from __future__ import annotations

from dataclasses import dataclass

from geology.dominio.codigos import normalizar_texto


@dataclass(frozen=True)
class OpcionTvd:
    """
    Una subserie de la tabla de valoración documental de un periodo.

    HALLAZGO del 9 de septiembre. Un mismo periodo tiene VARIAS oficinas productoras, y el
    código de serie y el de subserie se repiten entre ellas: en el periodo I, «01 ESTUDIOS ›
    01 Estudios Geológicos» existe en la Comisión Científica Nacional (dependencia 100.1) y
    otra vez en la Comisión Geológica del Urabá (100.2). Son dos productores distintos y por
    el principio de procedencia NO son la misma clasificación.

    Mientras la identidad de una opción fue solo «serie|subserie», esas filas se pisaban unas
    a otras: la lista desplegable mostraba renglones idénticos sin poder distinguirlos, el
    código de dependencia que se llenaba era el de la primera que apareciera, y en el periodo
    XIV veintiuna de las setenta y cinco filas de la tabla no se podían escoger. Por eso la
    identidad incluye ahora la dependencia.
    """
    periodo: str
    cod_serie: str
    serie: str
    cod_subserie: str
    subserie: str
    retencion_central_anios: int | None = None
    disposicion_final: str | None = None
    codigo_dependencia: str = ""
    oficina_productora: str = ""

    @property
    def clave(self) -> str:
        """Lo que identifica sin ambigüedad una fila de la tabla de valoración."""
        return f"{self.codigo_dependencia}|{self.cod_serie}|{self.cod_subserie}"

    def __str__(self) -> str:
        return " ".join(x for x in (self.cod_serie, self.serie, "›", self.cod_subserie, self.subserie) if x)

    def con_productor(self) -> str:
        """Como se escribe cuando hay que distinguir de qué oficina productora es."""
        oficina = f"{self.oficina_productora} · " if self.oficina_productora else ""
        return f"{oficina}{self}"


@dataclass(frozen=True)
class Encabezado:
    """Los campos de clasificación que trae el encabezado de la hoja de control."""
    codigo_serie: str = ""
    serie: str = ""
    codigo_subserie: str = ""
    subserie: str = ""
    nombre_expediente: str = ""


@dataclass(frozen=True)
class Clasificacion:
    opcion: OpcionTvd | None
    por_nombre: bool = False
    observacion: str = ""

    @property
    def alineada(self) -> bool:
        return self.opcion is not None


def asimilar_encabezado(encabezado: Encabezado, opciones: list[OpcionTvd]) -> Clasificacion:
    """
    R23. Busca en la lista cerrada del periodo la subserie del encabezado, en cuatro pasos.

    Primero por código de serie y de subserie juntos, que es lo exacto, porque el código de
    subserie por sí solo se repite en cada serie. Segundo, por código de subserie escrito
    completo cuando trae cuatro o más caracteres. Tercero, por nombre normalizado. Cuarto,
    cuando el encabezado trae serie sin subserie y esa serie tiene una única subserie.
    """
    cod_sub = normalizar_texto(encabezado.codigo_subserie)
    cod_ser = normalizar_texto(encabezado.codigo_serie)
    nom_sub = normalizar_texto(encabezado.subserie)
    nom_ser = normalizar_texto(encabezado.serie)

    for o in opciones:
        if cod_sub and normalizar_texto(o.cod_subserie) == cod_sub and (
                not cod_ser or normalizar_texto(o.cod_serie) == cod_ser):
            return Clasificacion(o, por_nombre=False)

    if cod_sub and len(cod_sub) >= 4:
        for o in opciones:
            if normalizar_texto(o.cod_subserie) == cod_sub:
                return Clasificacion(o, por_nombre=False)

    for o in opciones:
        if nom_sub and normalizar_texto(o.subserie) == nom_sub and (
                not nom_ser or normalizar_texto(o.serie) == nom_ser):
            return Clasificacion(o, por_nombre=True)

    if cod_ser and not cod_sub and not nom_sub:
        candidatas = [o for o in opciones if normalizar_texto(o.cod_serie) == cod_ser]
        if len(candidatas) == 1:
            return Clasificacion(candidatas[0], por_nombre=True)

    return Clasificacion(None)


def asimilar_con_equivalencia(encabezado: Encabezado, opciones_del_periodo: list[OpcionTvd],
                              todas_las_opciones: list[OpcionTvd]) -> Clasificacion:
    """
    R24. Si el encabezado trae la clasificación de otro periodo, se busca la subserie
    equivalente en el periodo que corresponde, se alinea y se deja constancia del cambio.
    """
    directa = asimilar_encabezado(encabezado, opciones_del_periodo)
    if directa.alineada:
        return directa

    for o in todas_las_opciones:
        if normalizar_texto(o.subserie) and normalizar_texto(o.subserie) == normalizar_texto(encabezado.subserie):
            equivalente = asimilar_encabezado(
                Encabezado(serie=o.serie, subserie=o.subserie), opciones_del_periodo)
            if equivalente.alineada:
                periodo_destino = opciones_del_periodo[0].periodo if opciones_del_periodo else ""
                return Clasificacion(
                    equivalente.opcion, por_nombre=True,
                    observacion=(f"El encabezado trae la clasificación del periodo {o.periodo}; "
                                 f"al generar se alineará a la subserie equivalente del periodo "
                                 f"{periodo_destino}."))
    return Clasificacion(None)


def valoracion_segun_tvd(opcion: OpcionTvd, periodo: str) -> str:
    """
    R26. La valoración y la disposición final no se redactan a mano: se toman de la tabla
    de valoración documental convalidada de la subserie asignada.
    """
    retencion = opcion.retencion_central_anios
    disposicion = opcion.disposicion_final or "—"
    return (f"Según la Tabla de Valoración Documental convalidada del periodo {periodo}, "
            f"la subserie {opcion.subserie} tiene una retención en archivo central de "
            f"{retencion if retencion is not None else '—'} años y disposición final "
            f"{disposicion}.")


def error_de_clasificacion(periodo: str) -> str:
    """R25. Mensaje cuando la serie y la subserie no corresponden a la tabla del periodo."""
    return (f"La serie y subserie del encabezado no corresponden a la tabla de valoración "
            f"del periodo {periodo}. Elija la subserie en el editor.")


# ---------------------------------------------------------------------------
# Elección de subserie por el contenido del expediente
# ---------------------------------------------------------------------------
# La dirección del proyecto pidió que la plataforma NUNCA deje la casilla de serie y
# subserie sin escoger. Antes, cuando el código del inventario no existía en la tabla de
# valoración del periodo —que es lo corriente, porque el inventario se levantó con otra
# estructura— la lista quedaba en «— elija la serie y la subserie —» y el trabajo de
# clasificar recaía entero en la persona. Ahora la plataforma siempre propone una, dice por
# qué la propuso y con cuánta seguridad, y la persona valida o la cambia.
#
# La propuesta NUNCA sale de la lista cerrada de la tabla convalidada: no se inventa ni una
# serie ni una subserie que no esté en la tabla del periodo.

CONFIANZA_ALTA = "alta"
CONFIANZA_MEDIA = "media"
CONFIANZA_BAJA = "baja"

# Longitud a la que se corta cada palabra para compararla. Así «INFORMES» encuentra
# «INFORME», y «MUESTRAS» encuentra «MUESTREO», que es lo que pasa de verdad entre el
# lenguaje del documento y el nombre de la subserie.
_RAIZ = 6


@dataclass(frozen=True)
class Eleccion:
    """La subserie que la plataforma propone, con el porqué a la vista."""
    opcion: OpcionTvd | None = None
    porque: str = ""
    confianza: str = CONFIANZA_BAJA
    origen: str = "ninguna"          # inventario · modelo · contenido · unica · respaldo

    @property
    def hay(self) -> bool:
        return self.opcion is not None

    def como_dict(self) -> dict | None:
        if not self.opcion:
            return None
        o = self.opcion
        return {"cod_serie": o.cod_serie, "serie": o.serie,
                "cod_subserie": o.cod_subserie, "subserie": o.subserie,
                "codigo_dependencia": o.codigo_dependencia,
                "dependencia": o.oficina_productora}

    def frase(self) -> str:
        if not self.opcion:
            return ""
        o = self.opcion
        return (f"Subserie propuesta {o.con_productor()} ({self.porque}). "
                "Confírmela o cámbiela si el documento dice otra cosa.")


def _raices(texto: str) -> set[str]:
    """Las palabras con contenido de un texto, cortadas a su raíz para poder compararlas."""
    from geology.dominio.codigos import palabras_significativas
    return {p[:_RAIZ] for p in palabras_significativas(texto)}


def puntuar_opcion(opcion: OpcionTvd, raices_del_documento: set[str]) -> int:
    """
    Cuánto se parece el contenido del expediente al nombre de una subserie de la tabla.

    El nombre de la subserie pesa el doble que el de la serie: la serie es una familia ancha
    («CORRESPONDENCIA») y la subserie es la que de verdad distingue («CORRESPONDENCIA
    RECIBIDA DE ENTIDADES OFICIALES»).
    """
    if not raices_del_documento:
        return 0
    en_sub = len(raices_del_documento & _raices(opcion.subserie))
    en_ser = len(raices_del_documento & _raices(opcion.serie))
    return en_sub * 2 + en_ser


def elegir_por_contenido(opciones: list[OpcionTvd], textos: list[str],
                         mas_usadas: dict | None = None) -> Eleccion:
    """
    Escoge, de la lista cerrada del periodo, la subserie a la que pertenece el expediente.

    Se compara lo que dice el documento —los tipos documentales que se leyeron, el asunto
    del inventario, el título— contra los nombres de las series y subseries de la tabla.

    Si nada coincide no se deja vacío: se propone la subserie que más se ha usado en ese
    periodo, y si tampoco hay historia, la primera de la tabla. En ambos casos la propuesta
    queda marcada como de confianza baja y con su explicación, para que la persona la mire.
    """
    if not opciones:
        return Eleccion()
    if len(opciones) == 1:
        return Eleccion(opciones[0], "es la única subserie de la tabla de este periodo",
                        CONFIANZA_ALTA, "unica")

    raices = _raices(" ".join(t for t in textos if t))
    mejor, puntaje = None, 0
    for o in opciones:
        p = puntuar_opcion(o, raices)
        if p > puntaje:
            mejor, puntaje = o, p

    if mejor and puntaje >= 4:
        return Eleccion(mejor, "por el contenido leído del expediente", CONFIANZA_ALTA,
                        "contenido")
    if mejor and puntaje >= 2:
        return Eleccion(mejor, "por el contenido leído del expediente, coincidencia parcial",
                        CONFIANZA_MEDIA, "contenido")
    if mejor:
        return Eleccion(mejor, "coincidencia débil con el contenido, revísela",
                        CONFIANZA_BAJA, "contenido")

    if mas_usadas:
        # Las claves son las de OpcionTvd.clave, es decir dependencia|serie|subserie: sin la
        # dependencia dos filas distintas de la tabla se contarían como una sola.
        clave = max(mas_usadas, key=lambda k: mas_usadas[k])
        for o in opciones:
            if o.clave == clave:
                return Eleccion(o, "sin coincidencia de palabras: se propone la subserie que "
                                   "más se ha usado en este periodo", CONFIANZA_BAJA, "respaldo")

    primera = sorted(opciones, key=lambda o: (o.codigo_dependencia, o.cod_serie, o.cod_subserie))[0]
    return Eleccion(primera, "sin coincidencia de palabras: se propone la primera de la tabla "
                             "del periodo", CONFIANZA_BAJA, "respaldo")


def elegir_de_la_lista(opciones: list[OpcionTvd], cod_serie: str, cod_subserie: str,
                       subserie: str = "", dependencia: str = "") -> OpcionTvd | None:
    """
    Comprueba que una elección —venga de donde venga— esté de verdad en la tabla del periodo.

    Es la reja que impide que una propuesta del modelo entre con una serie o una subserie
    que no existe en la tabla convalidada.

    Cuando la misma pareja de códigos existe en varias oficinas productoras del periodo, la
    dependencia desempata. Sin ella se toma la primera, pero queda escogida una fila concreta
    de la tabla y no una pareja de códigos ambigua.
    """
    encontrada = asimilar_encabezado(
        Encabezado(cod_serie or "", "", cod_subserie or "", subserie or ""), opciones).opcion
    if not encontrada:
        return None
    if not dependencia:
        return encontrada
    dep = normalizar_texto(dependencia)
    for o in opciones:
        if (o.cod_serie == encontrada.cod_serie and o.cod_subserie == encontrada.cod_subserie
                and normalizar_texto(o.codigo_dependencia) == dep):
            return o
    return encontrada
