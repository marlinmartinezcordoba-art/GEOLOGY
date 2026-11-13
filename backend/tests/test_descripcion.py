"""Procesos por lote (hoja de control, ISAD(G) o ambas) y descripción ISAD(G) sobre lo digitalizado. Datos ficticios."""

import io

import openpyxl
from conftest import agregar_usuario
from fabricas import pdf_con_texto, pdf_escaneado
from test_m04_clasificacion import FILAS, _escenario, _trd
from test_m13_ocr import PAGINAS, requiere_tesseract


def _listo(cliente, org):
    """FUID (cajas C-1, C-2, C-3), TRD vigente, clasificación confirmada y base de cajas con lotes."""
    p, url, director, cla = _escenario(cliente, org, FILAS)
    _trd(cliente, org, director, url)
    cliente.post(f"{cla}/proponer", headers=org.admin)
    propuestas = [f["clasificacion"]["id"] for f in cliente.get(cla, params={"situacion": "propuesta", "limite": 500}, headers=org.admin).json()["filas"]]
    cliente.post(f"{cla}/confirmar", json={"clasificaciones": propuestas}, headers=org.admin)
    base = f"/api/v1/proyectos/{p['id']}"
    listado = "Caja;Lote\nC-1;HISTORICO\nC-2;AMBOS\n"
    r = cliente.post(f"{base}/productividad/cajas/listado", files={"archivo": ("cajas.csv", listado.encode())}, headers=org.admin)
    assert r.status_code == 200, r.text
    unidades = {u["identificador"]: u["id"] for u in cliente.get(f"{base}/inventario/unidades", headers=org.admin).json()["unidades"]}
    return p, base, director, unidades


def _configurar(cliente, cab, base, lote, hoja, isadg):
    return cliente.put(f"{base}/procesos-por-lote", json={"lote": lote, "hoja_control": hoja, "isadg": isadg, "motivo": "Lo pidió la entidad (ficticio)"}, headers=cab)


def test_procesos_por_lote(cliente, org_a):
    p, base, director, u = _listo(cliente, org_a)
    lotes = {x["lote"]: x for x in cliente.get(f"{base}/procesos-por-lote", headers=org_a.admin).json()}
    assert set(lotes) == {"", "HISTORICO", "AMBOS"} and (lotes[""]["hoja_control"], lotes[""]["isadg"]) == (True, False)
    assert (lotes["HISTORICO"]["unidades"], lotes["AMBOS"]["unidades"], lotes[""]["unidades"]) == (2, 2, 2)
    assert _configurar(cliente, org_a.admin, base, "HISTORICO", False, False).status_code == 422  # al menos uno
    r = _configurar(cliente, org_a.admin, base, "HISTORICO", False, True).json()
    assert {x["lote"]: (x["hoja_control"], x["isadg"]) for x in r}["HISTORICO"] == (False, True)
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo", [p["id"]])
    assert _configurar(cliente, equipo, base, "AMBOS", True, True).status_code == 403  # lo decide la dirección
    # El lote HISTORICO no lleva hoja de control: no se crea y la bandeja lo dice.
    r = cliente.post(f"{base}/hojas-control/unidades/{u['CP-1']}", json={}, headers=org_a.admin)
    assert r.status_code == 422 and "HISTORICO" in r.json()["detail"]
    bandeja = {f["identificador"]: f for f in cliente.get(f"{base}/hojas-control", headers=org_a.admin).json()["filas"]}
    assert bandeja["CP-1"]["estado"] == "no_aplica" and bandeja["CP-3"]["estado"] == "sin_hoja"
    # Y el lote del proyecto (sin ISAD(G)) no se describe.
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("CP-5.pdf", pdf_escaneado(1)))], data={"rutas_relativas": ["CP-5.pdf"]}, headers=org_a.admin)
    r = cliente.post(f"{base}/descripciones/unidades/{u['CP-5']}", headers=org_a.admin)
    assert r.status_code == 422 and "configuración" in r.json()["detail"]
    d = {f["identificador"]: f["estado"] for f in cliente.get(f"{base}/descripciones", headers=org_a.admin).json()["filas"]}
    assert (d["CP-1"], d["CP-5"]) == ("sin_descripcion", "no_aplica")


def test_descripcion_desde_la_hoja_de_control_verificada(cliente, org_a):
    p, base, director, u = _listo(cliente, org_a)
    _configurar(cliente, org_a.admin, base, "AMBOS", True, True)
    assert cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}", headers=org_a.admin).status_code == 422  # sin digitalizar no se describe
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("CP-3.pdf", pdf_escaneado(3)))], data={"rutas_relativas": ["CP-3.pdf"]}, headers=org_a.admin)
    hc = f"{base}/hojas-control/unidades/{u['CP-3']}"
    t = cliente.post(hc, json={}, headers=org_a.admin).json()["tramites"][0]
    cliente.patch(f"{hc}/tramites/{t['id']}", json={"tipo_documental": "Tutela", "fecha": "1992-03-05", "detalle": "Tutela de un ciudadano ficticio"}, headers=org_a.admin)
    d = cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}", headers=org_a.admin).json()
    assert any("no está verificada" in a for a in d["avisos"])
    cliente.post(f"{hc}/enviar", headers=org_a.admin)
    cliente.post(f"{hc}/tramites/{t['id']}/revisar", json={"conforme": True}, headers=director)
    cliente.post(f"{hc}/verificar", headers=director)
    d = cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/recalcular", headers=org_a.admin).json()
    c, o = d["descripcion"]["campos"], d["descripcion"]["origen"]
    assert (c["fecha_inicial"], o["fecha_inicial"]["fuente"]) == ("1992-03-05", "hoja_control")
    assert c["codigo_referencia"] == f"CO.{p['codigo']}.110-05.01.CP-3" and c["nivel"] == "Expediente"
    assert c["productor"] == "Entidad Ficticia. Oficina jurídica" and o["productor"]["fuente"] == "clasificacion"
    assert c["valoracion"].startswith("Selección según la TRD") and "8 en archivo central" in c["valoracion"]
    assert c["volumen"].startswith("3 folios en papel") and "3 imágenes digitales" in c["volumen"]
    assert c["titulo"].startswith("Tutela de la Oficina jurídica") and o["titulo"]["fuente"] == "propuesta"
    assert "Tutela de un ciudadano ficticio" in c["alcance"]
    # Lo propuesto se confirma o se escribe; lo genérico lo devuelve la revisión.
    assert cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/enviar", headers=org_a.admin).status_code == 422
    d = cliente.patch(f"{base}/descripciones/unidades/{u['CP-3']}", json={"campos": {"titulo": "Tutelas"}}, headers=org_a.admin).json()
    assert any(h["gravedad"] == "DEVUELVE" and "3.1.2" in h["regla"] for h in d["revision"]["hallazgos"])
    cliente.patch(f"{base}/descripciones/unidades/{u['CP-3']}", json={"campos": {"titulo": "Acción de tutela de un ciudadano ficticio contra la Oficina jurídica, 1992"}}, headers=org_a.admin)
    d = cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/confirmar", json={"elemento": "alcance"}, headers=org_a.admin).json()
    assert d["revision"]["por_confirmar"] == [] and d["revision"]["devuelve"] == 0
    assert cliente.patch(f"{base}/descripciones/unidades/{u['CP-3']}", json={"campos": {"valoracion": "Lo que yo diga"}}, headers=org_a.admin).status_code == 422
    # Recalcular no pisa lo que escribió la persona.
    d = cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/recalcular", headers=org_a.admin).json()
    assert d["descripcion"]["campos"]["titulo"].startswith("Acción de tutela")
    # La aprueba otra persona.
    d = cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/enviar", headers=org_a.admin).json()
    assert d["descripcion"]["estado"] == "en_revision"
    assert cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/aprobar", headers=org_a.admin).status_code == 403
    d = cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/devolver", json={"motivo": "Precisar el alcance", "observaciones": {"alcance": "Diga qué se decidió"}}, headers=director).json()
    assert d["descripcion"]["estado"] == "devuelta" and d["descripcion"]["observaciones"]["alcance"] == "Diga qué se decidió"
    cliente.patch(f"{base}/descripciones/unidades/{u['CP-3']}", json={"campos": {"alcance": "Acción de tutela con su fallo, que niega el amparo solicitado. No aparece la impugnación."}}, headers=org_a.admin)
    cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/enviar", headers=org_a.admin)
    d = cliente.post(f"{base}/descripciones/unidades/{u['CP-3']}/aprobar", headers=director).json()
    assert d["descripcion"]["estado"] == "aprobada" and "revisada por Persona director@alfa.example.com" in d["descripcion"]["campos"]["nota_archivero"]
    # La base de descripción sale en la plantilla de la entidad.
    assert cliente.post(f"{base}/descripciones/expedir", headers=org_a.admin).status_code == 422
    pl = cliente.post("/api/v1/plantillas", json={"tipo": "descripcion_isadg", "nombre": "Base ISAD(G) de la entidad"}, headers=org_a.admin).json()
    formato = cliente.get("/api/v1/plantillas/tipos/descripcion_isadg/base", headers=org_a.admin).content
    cliente.post(f"/api/v1/plantillas/{pl['id']}/versiones", files={"archivo": ("b.xlsx", formato)}, data={"motivo": "Formato de la entidad"}, headers=org_a.admin)
    e = cliente.post(f"{base}/descripciones/expedir", headers=org_a.admin)
    assert e.status_code == 201 and e.json()["elementos"] == 1
    hoja = openpyxl.load_workbook(io.BytesIO(cliente.get(f"{base}/entregables/{e.json()['expedicion_id']}/archivo", headers=org_a.admin).content)).active
    textos = [str(x.value) for f in hoja.iter_rows() for x in f if x.value is not None]
    assert "Acción de tutela de un ciudadano ficticio contra la Oficina jurídica, 1992" in textos and f"CO.{p['codigo']}.110-05.01.CP-3" in textos


@requiere_tesseract
def test_descripcion_desde_el_ocr_cuando_el_lote_no_lleva_hoja(cliente, org_a):
    p, base, director, u = _listo(cliente, org_a)
    _configurar(cliente, org_a.admin, base, "HISTORICO", False, True)
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("CP-1.pdf", pdf_con_texto(PAGINAS)))], data={"rutas_relativas": ["CP-1.pdf"]}, headers=org_a.admin)
    cliente.post(f"{base}/ocr/unidades/{u['CP-1']}/leer", json={}, headers=org_a.admin)
    d = cliente.post(f"{base}/descripciones/unidades/{u['CP-1']}", headers=org_a.admin).json()
    c, o = d["descripcion"]["campos"], d["descripcion"]["origen"]
    assert (c["fecha_inicial"], c["fecha_final"], o["fecha_inicial"]["fuente"]) == ("2020-02-03", "2020-02-10", "ocr")
    assert o["alcance"]["fuente"] == "propuesta" and "Citación" in c["alcance"] and "Acta" in c["alcance"]
    assert c["titulo"].startswith(("Citación", "Acta")) and "Dirección general" in c["titulo"]
    assert "hoja de control" not in c["instrumentos"]


def test_permisos_y_aislamiento(cliente, org_a, org_b):
    p, base, director, u = _listo(cliente, org_a)
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(f"{base}/descripciones", headers=consulta).status_code == 200
    assert cliente.post(f"{base}/descripciones/unidades/{u['CP-1']}", headers=consulta).status_code == 403
    assert cliente.get(f"{base}/procesos-por-lote", headers=org_b.admin).status_code == 404


