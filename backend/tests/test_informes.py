"""Informe de avance, PDF con logo de la entidad e indexación para el SGDEA (D-47). Todo con datos ficticios."""

import csv
import io
import zipfile

import openpyxl
import pikepdf
from conftest import agregar_usuario
from PIL import Image
from test_entregables import _crear, _formato_entidad, _proyecto_con_fuid, _publicar
from test_flujo import _procesar
from test_historias import CONFIG, _proyecto
from test_m13_ocr import _listo as _listo_ocr
from test_m13_ocr import requiere_tesseract

from arca.modulos.entrega import pdfa


def _logo() -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", (240, 80), (30, 80, 160)).save(salida, "PNG")
    return salida.getvalue()


def test_logo_y_entregable_en_pdfa(cliente, org_a):
    p = _proyecto_con_fuid(cliente, org_a)
    base = f"/api/v1/proyectos/{p['id']}"
    assert cliente.put(f"{base}/logo", files={"archivo": ("logo.pdf", b"%PDF-1.4 no es imagen")}, headers=org_a.admin).status_code == 422
    assert cliente.put(f"{base}/logo", files={"archivo": ("logo.png", _logo())}, headers=org_a.admin).status_code == 201
    assert cliente.get(f"{base}/logo", headers=org_a.admin).content.startswith(b"\x89PNG")
    libro = openpyxl.load_workbook(io.BytesIO(_formato_entidad()))
    libro.active["A2"] = "Proyecto {{codigo_proyecto}}"
    salida = io.BytesIO()
    libro.save(salida)
    _publicar(cliente, org_a, _crear(cliente, org_a, "fuid")["id"], salida.getvalue())
    e = cliente.post(f"{base}/entregables", json={"tipo": "fuid"}, headers=org_a.admin).json()
    r = cliente.get(f"{base}/entregables/{e['id']}/pdf", headers=org_a.admin)
    assert r.status_code == 200 and r.headers["x-pdfa"] == "2b" and r.headers["content-disposition"].endswith('.pdf"')
    assert pdfa.validar(r.content)["conforme"]
    with pikepdf.open(io.BytesIO(r.content)) as pdf:
        assert any("/XObject" in pg.Resources for pg in pdf.pages)  # el logo
        assert str(pdf.docinfo["/Title"]).startswith("FUID") and len(pdf.pages) >= 1


def test_informe_de_avance(cliente, org_a):
    p, base, director, u = _proyecto(cliente, org_a)
    cliente.put(f"{base}/historias/config", json=CONFIG, headers=director)
    cliente.post(f"{base}/historias/expedientes/proponer", headers=org_a.admin)
    cliente.put(f"{base}/alistamiento/plan", json={"actividades": [{"codigo": "foliacion", "nombre": "Foliación", "cantidad": "folios"}], "motivo": "Del pliego ficticio"},
                headers=director)
    cliente.post(f"{base}/alistamiento/registrar", json={"actividad": "foliacion", "unidades": [u["HL-1"]], "cantidades": {u["HL-1"]: 3}}, headers=org_a.admin)
    cliente.put(f"{base}/alistamiento/expedientes/{u['HL-2']}/diagnostico", json={"estado": "malo", "hallazgos": ["biologico"]}, headers=org_a.admin)
    inf = f"{base}/informe-avance"
    assert cliente.get(inf, params={"desde": "2026-12-01", "hasta": "2026-01-01"}, headers=org_a.admin).status_code == 422
    rango = {"desde": "2026-01-01", "hasta": "2026-12-31"}
    d = cliente.get(inf, params=rango | {"formato": "json"}, headers=org_a.admin).json()
    secciones = {s["titulo"]: s for s in d["secciones"]}
    assert {"Proyecto y periodo", "Alistamiento físico", "Diagnóstico de conservación (acumulado)", "Historias laborales", "Evidencia"} <= set(secciones)
    assert secciones["Alistamiento físico"]["tabla"][1][:3] == ["Foliación", 1, 1]
    assert ["Por aislar (deterioro biológico)", 1] in secciones["Diagnóstico de conservación (acumulado)"]["tabla"]
    assert "íntegra" in secciones["Evidencia"]["parrafos"][0]
    x = openpyxl.load_workbook(io.BytesIO(cliente.get(inf, params=rango | {"formato": "xlsx"}, headers=org_a.admin).content)).active
    assert str(x["A1"].value).startswith("Informe de avance")
    cliente.put(f"{base}/logo", files={"archivo": ("logo.png", _logo())}, headers=director)
    r = cliente.get(inf, params=rango, headers=org_a.admin)
    assert r.status_code == 200 and r.headers["x-pdfa"] == "2b" and pdfa.validar(r.content)["conforme"]
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(inf, params=rango | {"formato": "json"}, headers=consulta).status_code == 200


@requiere_tesseract
def test_archivo_de_indexacion_en_el_paquete(cliente, org_a):
    base, director, u = _listo_ocr(cliente, org_a)
    proyecto_id = base.rsplit("/", 1)[-1]
    param = "/api/v1/configuracion/parametros"
    malo = {"clave": "entrega.indexacion", "proyecto_id": proyecto_id, "motivo": "Formato de cargue del SGDEA (ficticio)",
            "valor": {"columnas": [{"nombre": "X", "campo": "unidad.inventado"}]}}
    assert cliente.post(param, json=malo, headers=org_a.admin).status_code == 422
    config = {"por": "expediente", "separador": ";", "nombre_archivo": "indice_sgdea.csv", "columnas": [
        {"nombre": "EXPEDIENTE", "campo": "unidad.identificador"}, {"nombre": "SERIE", "campo": "clasificacion.codigo"},
        {"nombre": "RUTA", "campo": "pdf.ruta"}, {"nombre": "HUELLA", "campo": "pdf.sha256"}, {"nombre": "ORIGEN", "campo": "fijo:ARCA"}]}
    assert cliente.post(param, json=malo | {"valor": config}, headers=org_a.admin).status_code == 201
    assert cliente.get(f"{base}/entrega/indexacion", headers=org_a.admin).json()["config"]["nombre_archivo"] == "indice_sgdea.csv"
    assert cliente.post(f"{base}/entrega/paquetes", json={"solo_listos": False}, headers=org_a.admin).status_code == 202
    _procesar(cliente, base, org_a.admin)
    paquete = cliente.get(f"{base}/entrega/paquetes", headers=org_a.admin).json()[0]
    z = zipfile.ZipFile(io.BytesIO(cliente.get(f"{base}/entrega/paquetes/{paquete['id']}/archivo", headers=org_a.admin).content))
    filas = list(csv.reader(io.StringIO(z.read("indice_sgdea.csv").decode("utf-8-sig")), delimiter=";"))
    assert filas[0] == ["EXPEDIENTE", "SERIE", "RUTA", "HUELLA", "ORIGEN"]
    fila = filas[1]
    assert fila[0] == "CP-1" and fila[2] == "CP-1/expediente.pdf" and fila[4] == "ARCA"
    manifiesto = {f[0]: f[2] for f in csv.reader(io.StringIO(z.read("manifiesto.csv").decode("utf-8-sig")), delimiter=";")}
    assert manifiesto["CP-1/expediente.pdf"] == fila[3] and "indice_sgdea.csv" in manifiesto
