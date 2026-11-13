"""
Control de calidad de lo que produce la plataforma.

No basta con que el modelo y el equipo llenen las hojas: hay que revisar lo hecho y poder
demostrarle a la entidad contratante que se revisó. Este módulo pasa por encima de
todo lo cargado y devuelve una lista de hallazgos, cada uno con la carpeta, la gravedad, la
prueba que falló y qué hacer. No corrige nada por su cuenta: señala.

Las pruebas salen de las reglas del contrato y de los principios de procedencia y orden
original (Acuerdos 004 y 005 de 2013 y 002 de 2014 del Archivo General de la Nación).

Gravedades:
    error     no debería pasar a la siguiente etapa así
    revisar   hay que mirarlo, puede estar bien
    aviso     queda constancia, no detiene nada
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ERROR = "error"
REVISAR = "revisar"
AVISO = "aviso"

# Tipos documentales que por sí solos no le dicen nada a quien consulta el archivo histórico.
GENERICOS = {
    "OFICIO", "CARTA", "MEMORANDO", "COMUNICACION", "COMUNICACIÓN", "DOCUMENTO", "INFORME",
    "ACTA", "CIRCULAR", "RESOLUCION", "RESOLUCIÓN", "SOLICITUD", "RESPUESTA", "ANEXO",
    "PLANILLA", "FORMATO", "CONSTANCIA", "CERTIFICADO", "NOTA", "TELEGRAMA", "FACTURA",
}


@dataclass(frozen=True)
class Hallazgo:
    carpeta: str
    gravedad: str
    prueba: str
    mensaje: str
    donde: str = ""

    def como_dict(self) -> dict:
        return {"carpeta": self.carpeta, "gravedad": self.gravedad, "prueba": self.prueba,
                "mensaje": self.mensaje, "donde": self.donde}


@dataclass
class Informe:
    hallazgos: list[Hallazgo] = field(default_factory=list)
    revisados: int = 0

    def anotar(self, carpeta, gravedad, prueba, mensaje, donde=""):
        self.hallazgos.append(Hallazgo(carpeta, gravedad, prueba, mensaje, donde))

    @property
    def errores(self) -> int:
        return sum(1 for h in self.hallazgos if h.gravedad == ERROR)

    @property
    def por_revisar(self) -> int:
        return sum(1 for h in self.hallazgos if h.gravedad == REVISAR)

    def resumen(self) -> dict:
        conteo: dict[str, int] = {}
        for h in self.hallazgos:
            conteo[h.prueba] = conteo.get(h.prueba, 0) + 1
        return {"expedientes_revisados": self.revisados, "hallazgos": len(self.hallazgos),
                "errores": self.errores, "por_revisar": self.por_revisar,
                "por_prueba": dict(sorted(conteo.items(), key=lambda x: -x[1]))}


# ---------------------------------------------------------------------------
# Pruebas sobre un expediente
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pruebas sobre el conjunto
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Salida en Excel, para anexar a un acta o a un informe de avance
# ---------------------------------------------------------------------------

def informe_a_excel(informe: Informe, quien: str = "") -> Path:
    from datetime import datetime

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    colores = {ERROR: "FFC7CE", REVISAR: "FFEB9C", AVISO: "DDEBF7"}

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Hallazgos"

    hoja["A1"] = "ARCA · Control de calidad"
    hoja["A1"].font = Font(bold=True, size=14)
    hoja["A2"] = (f"Generado el {datetime.now():%Y-%m-%d %H:%M}"
                  + (f" por {quien}" if quien else ""))
    hoja["A3"] = (f"{informe.revisados} expedientes revisados · {informe.errores} errores · "
                  f"{informe.por_revisar} por revisar · {len(informe.hallazgos)} hallazgos")

    encabezados = ["Carpeta", "Gravedad", "Prueba", "Qué pasa", "Dónde se corrige"]
    for col, texto in enumerate(encabezados, start=1):
        celda = hoja.cell(row=5, column=col, value=texto)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="44546A")

    orden = {ERROR: 0, REVISAR: 1, AVISO: 2}
    for fila, h in enumerate(sorted(informe.hallazgos,
                                    key=lambda x: (orden.get(x.gravedad, 9), x.prueba, x.carpeta)),
                             start=6):
        for col, texto in enumerate([h.carpeta, h.gravedad, h.prueba, h.mensaje, h.donde], start=1):
            celda = hoja.cell(row=fila, column=col, value=texto)
            celda.alignment = Alignment(vertical="top", wrap_text=(col >= 4))
            celda.fill = PatternFill("solid", fgColor=colores.get(h.gravedad, "FFFFFF"))

    for col, ancho in zip("ABCDE", (18, 12, 30, 80, 40)):
        hoja.column_dimensions[col].width = ancho
    hoja.freeze_panes = "A6"

    resumen = libro.create_sheet("Resumen por prueba")
    resumen.append(["Prueba", "Cuántas veces"])
    resumen["A1"].font = resumen["B1"].font = Font(bold=True)
    for prueba, cuantos in informe.resumen()["por_prueba"].items():
        resumen.append([prueba, cuantos])
    resumen.column_dimensions["A"].width = 40
    resumen.column_dimensions["B"].width = 16

    salida = Path("deposito") / "informes"
    salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / f"ARCA_calidad_{datetime.now():%Y%m%d_%H%M}.xlsx"
    libro.save(ruta)
    return ruta
