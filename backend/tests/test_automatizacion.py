"""Toda la automatización (D-40): metadatos desde el OCR, folios contados en el FUID, orientación y legibilidad de las páginas,
productividad contada por ARCA y paquete de entrega para el SGDEA de la entidad. Todo con documentos y personas ficticias."""

import csv
import hashlib
import io
import json
import zipfile

import openpyxl
import pikepdf
from conftest import agregar_usuario
from fabricas import pagina_con_texto, pdf_con_texto
from PIL import Image
from test_flujo import _procesar
from test_hoja_control import _listo as _listo_hoja
from test_m13_ocr import PAGINAS, _pagina, requiere_tesseract
from test_m13_ocr import _listo as _listo_ocr
from test_m24_productividad import _libro

from arca.modulos.entrega import pdfa
from arca.modulos.m13_ocr.propuestas import proponer

OFICIO = ["ENTIDAD FICTICIA NACIONAL", "OFICIO N.º 045", "Ciudad Ficticia, 5 de marzo de 2021", "Señora", "Ana Ficticia Pérez",
          "Asunto: solicitud de transferencia del archivo de gestión", "Cordial saludo. Se remite el inventario.", "Atentamente,",
          "Pedro Inventado Ruiz", "Jefe de la Oficina Ficticia"]


def test_metadatos_desde_el_texto_con_su_evidencia():
    d = proponer([_pagina(1, *OFICIO)], ["Oficio"])[0]
    assert d.metadatos == {"asunto": "solicitud de transferencia del archivo de gestión", "destinatario": "Ana Ficticia Pérez",
                           "firmantes": "Pedro Inventado Ruiz (Jefe de la Oficina Ficticia)", "lugar": "Ciudad Ficticia", "numero": "045"}
    assert d.evidencias["metadatos.asunto"].pagina == 1 and "Asunto:" in d.evidencias["metadatos.asunto"].fragmento
    assert "Asunto: solicitud de transferencia" in d.detalle
    # Lo que no está escrito no se inventa; «Comité directivo» antes de la fecha no es un lugar.
    acta = proponer([_pagina(1, "ACTA N.º 005", "Comité directivo, 10 de febrero de 2020", "Se aprueba el informe.")], ["Acta"])[0]
    assert "lugar" not in acta.metadatos and "asunto" not in acta.metadatos and "firmantes" not in acta.metadatos


def _verificar_hoja(cliente, org, director, hc, uid, metadatos):
    d = cliente.post(f"{hc}/unidades/{uid}", json={}, headers=org.admin).json()
    t = d["tramites"][0]
    r = cliente.patch(f"{hc}/unidades/{uid}/tramites/{t['id']}", json={"tipo_documental": "Acta", "fecha": "1990-05-10", "metadatos": metadatos}, headers=org.admin)
    assert r.status_code == 200, r.text
    assert next(x for x in r.json()["tramites"] if x["id"] == t["id"])["metadatos"]["asunto"] == metadatos["asunto"]
    cliente.post(f"{hc}/unidades/{uid}/enviar", headers=org.admin)
    cliente.post(f"{hc}/unidades/{uid}/tramites/{t['id']}/revisar", json={"conforme": True}, headers=director)
    assert cliente.post(f"{hc}/unidades/{uid}/verificar", headers=director).json()["hoja"]["estado"] == "verificada"


def test_fuid_con_folios_contados_y_productividad_contada_por_arca(cliente, org_a):
    p, base, director, hc, u = _listo_hoja(cliente, org_a)  # CP-1: el FUID dice 10 folios; lo digitalizado tiene 6
    # Productividad: actividades que ARCA cuenta sola a partir de la hoja verificada y del OCR.
    libro = openpyxl.load_workbook(io.BytesIO(_libro()))
    for fila in (["F1-02 · Hojas", "F1", 2, "Hojas de control", "expedientes", "Archivista", "No", "hojas_verificadas"],
                 ["F1-03 · Folios", "F1", 3, "Folios verificados", "folios", "Archivista", "No", "folios_verificados"],
                 ["F1-04 · Documentos", "F1", 4, "Documentos", "documentos", "Archivista", "No", "documentos_hoja"]):
        libro["dActividades"].append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    pr = f"{base}/productividad"
    assert cliente.post(f"{pr}/libro", files={"archivo": ("productividad.xlsx", salida.getvalue())}, headers=org_a.admin).status_code == 200
    _verificar_hoja(cliente, org_a, director, hc, u["CP-1"], {"asunto": "Aprobación del plan ficticio", "remitente": "Oficina ficticia"})
    automaticas = {f["Actividad"]: f["Cantidad"] for f in cliente.get(f"{pr}/tablas/fProduccion", headers=org_a.admin).json() if f["Origen"] == "automatico"}
    assert (automaticas["F1-02 · Hojas"], automaticas["F1-03 · Folios"], automaticas["F1-04 · Documentos"]) == (1, 6, 1)
    # El FUID de salida lleva los folios contados en la hoja verificada y deja constancia de lo que decía el inventario.
    pl = cliente.post("/api/v1/plantillas", json={"tipo": "fuid", "nombre": "FUID de la entidad"}, headers=org_a.admin).json()
    formato = cliente.get("/api/v1/plantillas/tipos/fuid/base", headers=org_a.admin).content
    assert cliente.post(f"/api/v1/plantillas/{pl['id']}/versiones", files={"archivo": ("f.xlsx", formato)}, data={"motivo": "Formato de la entidad"}, headers=org_a.admin).status_code == 201
    e = cliente.post(f"{base}/entregables", json={"tipo": "fuid"}, headers=org_a.admin)
    assert e.status_code == 201, e.text
    hoja = openpyxl.load_workbook(io.BytesIO(cliente.get(f"{base}/entregables/{e.json()['id']}/archivo", headers=org_a.admin).content)).active
    fila = next(f for f in hoja.iter_rows(values_only=True) if "CP-1" in f)
    assert 6 in fila and 10 not in fila
    assert any("Folios contados en la hoja de control: 6; el inventario de origen declaraba 10" in str(x) for x in fila)
    # Los metadatos verificados entran a la consulta.
    r = cliente.get("/api/v1/consulta/buscar", params={"q": "plan ficticio"}, headers=org_a.admin)
    assert r.status_code == 200 and any(x["identificador"] == "CP-1" for x in r.json()["filas"]), r.text


@requiere_tesseract
def test_pagina_girada_se_endereza_antes_del_ocr(cliente, org_a):
    base, _, u = _listo_ocr(cliente, org_a)
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("CP-2.pdf", pdf_con_texto([PAGINAS[2]], giro=90)))], data={"rutas_relativas": ["CP-2.pdf"]}, headers=org_a.admin)
    r = cliente.post(f"{base}/ocr/unidades/{u['CP-2']}/leer", json={}, headers=org_a.admin)
    assert r.status_code == 200 and r.json()["procesadas"] == 1, r.text
    texto = cliente.get(f"{base}/ocr/unidades/{u['CP-2']}", headers=org_a.admin).json()[0]
    assert "ACTA" in texto["texto"] and texto["confianza"] > 60  # se leyó derecha
    img = Image.open(io.BytesIO(cliente.get(f"{base}/hojas-control/unidades/{u['CP-2']}/paginas/1/imagen", headers=org_a.admin).content))
    assert img.height > img.width  # y se muestra derecha


def _zip(contenido):
    return zipfile.ZipFile(io.BytesIO(contenido))


@requiere_tesseract
def test_paquete_de_entrega(cliente, org_a, org_b):
    base, director, u = _listo_ocr(cliente, org_a)  # CP-1 digitalizada (4 páginas), sin hoja verificada
    entrega = f"{base}/entrega/paquetes"
    r = cliente.post(entrega, json={}, headers=org_a.admin)
    assert r.status_code == 422 and "6 pendientes" in r.text  # CP-1 sin hoja verificada (su lote la lleva) y 5 sin digitalizar
    r = cliente.post(entrega, json={"solo_listos": False}, headers=org_a.admin)
    assert r.status_code == 202 and r.json()["unidades"] == 1 and r.json()["estado"] == "en_cola", r.text
    _procesar(cliente, base, org_a.admin)
    paquete = cliente.get(entrega, headers=org_a.admin).json()[0]
    assert paquete["estado"] == "listo" and paquete["numero"] == 1, paquete
    descarga = cliente.get(f"{entrega}/{paquete['id']}/archivo", headers=org_a.admin)
    assert descarga.status_code == 200 and descarga.headers["x-sha256"] == hashlib.sha256(descarga.content).hexdigest()
    z = _zip(descarga.content)
    nombres = set(z.namelist())
    assert {"CP-1/expediente.pdf", "CP-1/metadatos.json", "manifiesto.csv", "originales.csv", "pdfa.csv", "pendientes.csv", "LEAME.txt"} <= nombres
    assert "CP-1/hoja_control.csv" not in nombres  # no tiene hoja verificada
    # El manifiesto trae la huella de cada archivo y coincide.
    manifiesto = list(csv.reader(io.StringIO(z.read("manifiesto.csv").decode("utf-8-sig")), delimiter=";"))[1:]
    assert {f[0] for f in manifiesto} == nombres - {"manifiesto.csv"}
    assert all(hashlib.sha256(z.read(f[0])).hexdigest() == f[2] for f in manifiesto)
    meta = json.loads(z.read("CP-1/metadatos.json"))
    assert meta["unidad"]["identificador"] == "CP-1" and meta["digitalizacion"]["paginas"] == 4 and meta["hoja_control"] is None
    assert meta["clasificacion"] is None or meta["clasificacion"]["codigo"]
    assert len(meta["digitalizacion"]["originales"][0]["sha256"]) == 64
    expediente = z.read("CP-1/expediente.pdf")
    with pikepdf.open(io.BytesIO(expediente)) as pdf:
        assert len(pdf.pages) == 4 and "/Font" in pdf.pages[0].Resources  # con la capa de texto del OCR
        assert pdf.open_metadata().pdfa_status == "2B" and pdf.docinfo["/Title"] == "CP-1 · Actas del comité directivo"
        assert "/OutputIntents" in pdf.Root and "/ID" in pdf.trailer
    assert pdfa.validar(expediente)["conforme"]  # PDF/A-2b validado sobre los bytes entregados
    assert meta["pdf"]["formato"] == "PDF/A-2b" and meta["pdf"]["conforme"] and meta["pdf"]["hallazgos"] == []
    informe = list(csv.reader(io.StringIO(z.read("pdfa.csv").decode("utf-8-sig")), delimiter=";"))
    assert informe[1][:3] == ["CP-1", "PDF/A-2b", "sí"]
    assert paquete["resumen"]["pdfa"] == {"nivel": "PDF/A-2b", "conformes": 1, "total": 1}
    # El validador del proyecto aprueba el PDF/A entregado y rechaza un PDF común, diciendo por qué.
    validar = f"{base}/entrega/validar-pdfa"
    r = cliente.post(validar, files={"archivo": ("expediente.pdf", expediente)}, headers=org_a.admin).json()
    assert r["conforme"] and r["veredicto"] == "conforme" and r["nivel"] == "PDF/A-2b"
    r = cliente.post(validar, files={"archivo": ("escaneo.pdf", pdf_con_texto([PAGINAS[0]]))}, headers=org_a.admin).json()
    assert not r["conforme"] and r["veredicto"] == "no_conforme" and any("Metadata" in h["mensaje"] and h["area"] == "Metadatos del documento (XMP)" for h in r["hallazgos"])
    assert any(h["explicacion"] == "Al archivo le falta su identificador (/ID)." and h["area"] == "Estructura del archivo" for h in r["hallazgos"])
    assert cliente.post(validar, files={"archivo": ("x.pdf", b"no es pdf")}, headers=org_a.admin).status_code == 422
    assert cliente.post(validar, files={"archivo": ("x.pdf", expediente)}, data={"nivel": "4z"}, headers=org_a.admin).status_code == 422
    assert "PDF/A-2b, páginas en orden, con texto buscable" in z.read("LEAME.txt").decode() and "(1 de 1)" in z.read("LEAME.txt").decode()
    pendientes = z.read("pendientes.csv").decode("utf-8-sig")
    assert pendientes.count("sin digitalizar") == 5 and "CP-1" not in pendientes
    eventos = cliente.get("/api/v1/auditoria/eventos?limite=100", headers=org_a.admin).json()
    assert {"SOLICITAR_PAQUETE", "GENERAR_PAQUETE", "DESCARGAR_PAQUETE", "VALIDAR_PDFA"} <= {e["accion"] for e in eventos}
    # Permisos y aislamiento.
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(entrega, headers=consulta).status_code == 200
    assert cliente.post(entrega, json={"solo_listos": False}, headers=consulta).status_code == 403
    assert cliente.get(f"{entrega}/{paquete['id']}/archivo", headers=consulta).status_code == 403
    assert cliente.get(entrega, headers=org_b.admin).status_code == 404


def test_pdfa_sin_ocr_en_grises_y_en_color():
    """La conversión no depende del OCR: un escaneo de solo imágenes también queda en PDF/A-2b validado."""
    for modo in ("L", "RGB"):
        salida = io.BytesIO()
        pagina = pagina_con_texto(PAGINAS[0]).convert(modo)
        pagina.save(salida, "PDF", resolution=200)
        assert not pdfa.validar(salida.getvalue())["conforme"]  # el PDF del escáner no es PDF/A
        r = pdfa.convertir(pikepdf.open(io.BytesIO(salida.getvalue())), "EXP-1 · Expediente ficticio", asunto="Serie ficticia", autor="Entidad Ficticia")
        assert r.conforme and r.hallazgos == [] and r.motor.startswith("pikepdf")
        assert pdfa.validar(r.contenido)["conforme"] and pdfa.validar(r.contenido, "1b")["veredicto"] in ("conforme", "no_conforme", "no_verificado")
        with pikepdf.open(io.BytesIO(r.contenido)) as pdf:
            assert pdf.docinfo["/Author"] == "Entidad Ficticia" and pdf.open_metadata().pdfa_status == "2B"
