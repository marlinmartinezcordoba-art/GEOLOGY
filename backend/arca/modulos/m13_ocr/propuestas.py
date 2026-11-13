"""M13 → hoja de control: del texto leído por OCR, una propuesta de documentos, con la evidencia de cada dato.

Qué se propone, siempre como PROPUESTA que una persona confirma (la IA y el OCR proponen, nunca deciden):
- Dónde empieza cada documento: una página empieza documento nuevo cuando su encabezado (las primeras líneas)
  trae el título de un tipo documental («ACTA N.º 005», «CITACIÓN», «RESOLUCIÓN») y no dice que es continuación
  o anexo, y además cambia el tipo o el número frente al documento que venía.
- El tipo documental: primero la lista de la subserie en la TRD; si no coincide, una lista general de tipos
  frecuentes (y entonces queda el aviso de que no está en la TRD).
- La fecha: la primera fecha escrita en el encabezado del documento, normalizada con las reglas del motor
  (día primero, por el uso colombiano; una fecha parcial queda parcial).
- El detalle: el renglón del título y el siguiente, tal como están escritos (no se tocan los nombres propios).
- El radicado, si aparece escrito como tal.

Cada dato propuesto lleva la página y el renglón de donde se tomó y la confianza del OCR en ese renglón.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from arca.motor.codigos import normalizar_texto
from arca.motor.fechas import normalizar_fecha

ENCABEZADO = 14  # renglones que se miran como encabezado de una página
GENERALES = [
    "Acta", "Acuerdo", "Anexo", "Auto", "Certificado", "Certificación", "Circular", "Citación", "Comunicación", "Concepto", "Constancia", "Contrato",
    "Cuenta de cobro", "Decreto", "Derecho de petición", "Factura", "Fallo", "Formato", "Informe", "Lista de asistencia", "Memorando", "Notificación",
    "Oficio", "Orden de pago", "Plan", "Planilla", "Proyecto", "Recibo", "Resolución", "Solicitud", "Tutela",
]
CONTINUACION = re.compile(r"\b(continuaci[oó]n|cont\.|anexo|p[aá]gina\s+\d+\s+de|hoja\s+\d+\s+de|folio\s+\d+\s+de)\b", re.IGNORECASE)
NUMERO = re.compile(r"\bN(?:o|ro|úm(?:ero)?)?\s*[.\s]*[º°o2]?\.?\s*(\d{1,7}(?:[-/]\d{1,4})?)", re.IGNORECASE)
RADICADO = re.compile(r"\bradicad[oa]\s*(?:n(?:o|ro|úmero)?\s*[.º°]*)?\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{3,30})", re.IGNORECASE)
MESES = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
FECHAS = [
    re.compile(rf"\b\d{{1,2}}\s+de\s+(?:{MESES})\s+(?:de|del)\s+\d{{4}}\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(rf"\b(?:{MESES})\s+(?:de|del)\s+\d{{4}}\b", re.IGNORECASE),
]


@dataclass
class Evidencia:
    pagina: int
    fragmento: str
    confianza: float | None

    def frase(self) -> str:
        conf = f", confianza {self.confianza:.0f} %" if self.confianza is not None else ""
        return f"propuesto por OCR de la página {self.pagina}: «{self.fragmento[:120]}»{conf}"


@dataclass
class DocumentoPropuesto:
    pagina_desde: int
    pagina_hasta: int
    tipo: str = ""
    tipo_en_trd: bool = False
    numero: str = ""
    fecha: str = ""
    detalle: str = ""
    radicado: str = ""
    evidencias: dict[str, Evidencia] = field(default_factory=dict)
    confianza: str = "baja"  # alta | media | baja: qué tan seguro es el corte y el tipo
    metadatos: dict[str, str] = field(default_factory=dict)  # asunto, remitente, destinatario, firmantes, lugar, numero

    def como_dict(self) -> dict[str, Any]:
        return {"pagina_desde": self.pagina_desde, "pagina_hasta": self.pagina_hasta, "tipo": self.tipo, "tipo_en_trd": self.tipo_en_trd, "fecha": self.fecha,
                "detalle": self.detalle, "radicado": self.radicado, "confianza": self.confianza, "metadatos": self.metadatos,
                "evidencias": {k: {"pagina": e.pagina, "fragmento": e.fragmento, "confianza": e.confianza} for k, e in self.evidencias.items()}}


METADATOS = {"asunto": "Asunto", "remitente": "Remitente", "destinatario": "Destinatario", "firmantes": "Firmantes", "lugar": "Lugar", "numero": "Número"}
ASUNTO = re.compile(r"^\s*(?:asunto|ref(?:erencia)?)\s*[:.\-]\s*(.*)$", re.IGNORECASE)
PARA = re.compile(r"^\s*(?:para|destinatario|dirigido\s+a)\s*[:.\-]\s*(.+)$", re.IGNORECASE)
DE = re.compile(r"^\s*(?:de|remitente|origen)\s*:\s*(.+)$", re.IGNORECASE)
SALUDO = re.compile(r"^\s*(?:señor(?:a|es|as)?|sr\.?|sra\.?|doctor(?:a)?|dr\.?|dra\.?|ingenier[oa]|ing\.|licenciad[oa])\b[\s.:]*(.*)$", re.IGNORECASE)
CIERRE = re.compile(r"^\s*(?:atentamente|cordialmente|respetuosamente|sin otro particular|con toda consideraci[oó]n)\b", re.IGNORECASE)
NO_ES_LUGAR = re.compile(r"\b(comit[eé]|sesi[oó]n|reuni[oó]n|consejo|junta|asamblea|acta|oficio|resoluci[oó]n|fecha|asunto|radicado|n[uú]mero)\b", re.IGNORECASE)
FIRMA = re.compile(r"^\s*(?:presidente|presidenta|secretari[oa]|firma|aprob[oó]|elabor[oó]|revis[oó])\s*[:.\-]\s*(.+)$", re.IGNORECASE)


def _siguiente(lineas: list[tuple[str, float | None]], i: int, n: int = 2) -> list[tuple[str, float | None]]:
    return [x for x in lineas[i + 1 : i + 1 + 6] if x[0].strip()][:n]


def extraer_metadatos(paginas: list[dict[str, Any]], d: "DocumentoPropuesto") -> None:
    """Asunto, remitente, destinatario, firmantes y lugar de un documento, con la página y el renglón de donde salieron.

    Solo lo que está escrito con su rótulo o en su lugar de costumbre (el «Asunto:», el «Señor» del destinatario, la firma
    después del «Atentamente», la ciudad antes de la fecha). Si no está, no se propone.
    """
    def poner(campo: str, valor: str, n: int, renglon: str, conf: float | None) -> None:
        valor = re.sub(r"\s+", " ", valor).strip(" .,;:-")
        if valor and campo not in d.metadatos and len(valor) <= 300:
            d.metadatos[campo] = valor
            d.evidencias[f"metadatos.{campo}"] = Evidencia(n, renglon, conf)

    firmantes: list[str] = []
    for p in paginas:
        if not d.pagina_desde <= p["n"] <= d.pagina_hasta:
            continue
        lineas = [(str(t), c) for t, c in (p.get("lineas") or [])]
        for i, (t, conf) in enumerate(lineas):
            if (m := ASUNTO.match(t)) and "asunto" not in d.metadatos:
                valor = m.group(1) or " ".join(x for x, _ in _siguiente(lineas, i, 1))
                poner("asunto", valor, p["n"], t, conf)
            elif m := PARA.match(t):
                poner("destinatario", m.group(1), p["n"], t, conf)
            elif m := DE.match(t):
                poner("remitente", m.group(1), p["n"], t, conf)
            elif (m := SALUDO.match(t)) and "destinatario" not in d.metadatos and p["n"] == d.pagina_desde:
                resto = m.group(1).strip()
                nombre = resto if len(resto) > 3 else " ".join(x for x, _ in _siguiente(lineas, i, 1))
                poner("destinatario", nombre, p["n"], t, conf)
            elif CIERRE.match(t):
                bloque = _siguiente(lineas, i, 2)
                if bloque and not any(ch.isdigit() for ch in bloque[0][0]):
                    firmante = bloque[0][0] + (f" ({bloque[1][0]})" if len(bloque) > 1 and len(bloque[1][0]) <= 80 else "")
                    firmantes.append(firmante.strip())
                    d.evidencias.setdefault("metadatos.firmantes", Evidencia(p["n"], " · ".join(x for x, _ in bloque), bloque[0][1]))
            elif m := FIRMA.match(t):
                firmantes.append(m.group(1).strip())
                d.evidencias.setdefault("metadatos.firmantes", Evidencia(p["n"], t, conf))
    if firmantes:
        d.metadatos["firmantes"] = "; ".join(dict.fromkeys(f for f in firmantes if f))[:300]
    if "fecha" in d.evidencias:
        renglon = d.evidencias["fecha"].fragmento
        for patron in FECHAS:
            if ((m := patron.search(renglon)) and (antes := renglon[: m.start()].strip(" ,.-")) and 2 <= len(antes) <= 40 and not any(ch.isdigit() for ch in antes)
                    and len(antes.split()) <= 4 and not NO_ES_LUGAR.search(antes)):
                poner("lugar", antes, d.evidencias["fecha"].pagina, renglon, d.evidencias["fecha"].confianza)
                break
    if d.numero and "tipo_documental" in d.evidencias:  # el número como está escrito («045»), no el normalizado para comparar
        m = NUMERO.search(d.evidencias["tipo_documental"].fragmento)
        d.metadatos["numero"] = m.group(1) if m else d.numero


def corregir(texto: str) -> str:
    """Solo la confusión conocida del OCR con el signo de número: «N.2 005» es «N.º 005». Nada más se toca."""
    return re.sub(r"\bN\.\s?2\s+(?=\d)", "N.º ", texto or "")


def _palabras(texto: str) -> list[str]:
    return [normalizar_texto(p) for p in re.split(r"[\s·,;:()\-–—/]+", texto or "") if normalizar_texto(p)]


def _es_titulo(linea: str, tipo: str) -> bool:
    """El renglón es el título de ese tipo: empieza con él (y es corto), o es un renglón corto en mayúsculas que lo contiene."""
    p, t = _palabras(linea), _palabras(tipo)
    if not t or not p:
        return False
    if p[: len(t)] == t and len(p) <= 12:
        return True
    letras = [c for c in linea if c.isalpha()]
    en_mayusculas = bool(letras) and sum(c.isupper() for c in letras) / len(letras) > 0.7
    return en_mayusculas and len(p) <= 6 and any(p[i : i + len(t)] == t for i in range(len(p) - len(t) + 1))


def _tipo_en(lineas: list[tuple[str, float | None]], tipos_trd: list[str]) -> tuple[str, bool, int] | None:
    """(tipo, si es de la TRD, índice del renglón) del primer título que se reconozca en el encabezado."""
    for i, (linea, _) in enumerate(lineas[:ENCABEZADO]):
        for lista, de_trd in ((sorted(tipos_trd, key=len, reverse=True), True), (sorted(GENERALES, key=len, reverse=True), False)):
            for tipo in lista:
                if _es_titulo(linea, tipo):
                    return tipo, de_trd, i
    return None


def _fecha_en(lineas: list[tuple[str, float | None]]) -> tuple[str, int] | None:
    for i, (linea, _) in enumerate(lineas[:ENCABEZADO]):
        for patron in FECHAS:
            if m := patron.search(linea):
                f = normalizar_fecha(m.group(0))
                if f.texto and 1800 <= int(f.texto[:4]) <= 2100:
                    return f.texto, i
    return None


def proponer(paginas: list[dict[str, Any]], tipos_trd: list[str]) -> list[DocumentoPropuesto]:
    """`paginas`: [{n, estado, lineas: [[texto, confianza], …], confianza}] en el orden del expediente."""
    docs: list[DocumentoPropuesto] = []
    for p in paginas:
        lineas = [(str(t), c) for t, c in (p.get("lineas") or [])]
        cabecera = " ".join(t for t, _ in lineas[:ENCABEZADO])
        hallado = _tipo_en(lineas, tipos_trd) if lineas else None
        numero = ""
        if hallado and (m := NUMERO.search(lineas[hallado[2]][0])):
            numero = m.group(1).lstrip("0") or "0"
        # La marca de continuación vale solo junto al título (o en los primeros renglones si no hay título): una palabra
        # como «anexo» en el cuerpo del documento no lo convierte en la continuación del anterior.
        cerca = " ".join(t for t, _ in (lineas[hallado[2]: hallado[2] + 2] if hallado else lineas[:4]))
        continua = bool(CONTINUACION.search(cerca))
        actual = docs[-1] if docs else None
        nuevo = actual is None or (hallado is not None and not continua and (normalizar_texto(hallado[0]) != normalizar_texto(actual.tipo) or (numero and numero != actual.numero)))
        if not nuevo:
            actual.pagina_hasta = p["n"]
            continue
        d = DocumentoPropuesto(pagina_desde=p["n"], pagina_hasta=p["n"])
        if hallado:
            tipo, de_trd, i = hallado
            d.tipo, d.tipo_en_trd, d.numero = tipo, de_trd, numero
            titulo, conf = lineas[i]
            d.evidencias["tipo_documental"] = Evidencia(p["n"], titulo, conf)
            siguiente = next((t for t, _ in lineas[i + 1 : i + 3] if t.strip()), "")
            d.detalle = corregir(f"{titulo.strip()} · {siguiente.strip()}" if siguiente and len(siguiente) <= 120 else titulo.strip())
            d.evidencias["detalle"] = Evidencia(p["n"], d.detalle, conf)
            ocr = p.get("confianza")
            d.confianza = "alta" if de_trd and (ocr or 0) >= 80 else ("media" if (ocr or 0) >= 60 else "baja")
        if f := _fecha_en(lineas):
            d.fecha = f[0]
            d.evidencias["fecha"] = Evidencia(p["n"], lineas[f[1]][0], lineas[f[1]][1])
        if m := RADICADO.search(cabecera):
            d.radicado = m.group(1)
            d.evidencias["no_radicado"] = Evidencia(p["n"], m.group(0), p.get("confianza"))
        docs.append(d)
    for d in docs:
        extraer_metadatos(paginas, d)
        if (asunto := d.metadatos.get("asunto")) and "Asunto" not in d.detalle:
            d.detalle = f"{d.detalle} · Asunto: {asunto}" if d.detalle else f"Asunto: {asunto}"
    return docs
