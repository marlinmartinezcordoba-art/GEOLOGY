"""Flujo automático (D-39): al cargar, calidad → OCR → hoja de control → descripción, hasta donde decide una persona. Ficticio."""

from conftest import agregar_usuario
from fabricas import imagen, pdf_con_texto
from test_descripcion import _configurar, _listo
from test_m13_ocr import PAGINAS, requiere_tesseract


def _cargar(cliente, base, cab, nombre, contenido):
    r = cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", (nombre.rsplit("/", 1)[-1], contenido))], data={"rutas_relativas": [nombre]}, headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def _procesar(cliente, base, cab):
    r = cliente.post(f"{base}/flujo/procesar", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def _etapa(cliente, base, cab, identificador):
    filas = cliente.get(f"{base}/flujo/unidades", headers=cab).json()["filas"]
    return next((f for f in filas if f["identificador"] == identificador), None)


@requiere_tesseract
def test_lote_con_hoja_y_descripcion_de_punta_a_punta(cliente, org_a):
    p, base, director, u = _listo(cliente, org_a)
    _configurar(cliente, org_a.admin, base, "AMBOS", True, True)
    _cargar(cliente, base, org_a.admin, "Entrega/CP-3.pdf", pdf_con_texto(PAGINAS))
    assert cliente.get(f"{base}/flujo", headers=org_a.admin).json()["cola"]["pendientes"] == 1  # la carga lo puso en cola
    r = _procesar(cliente, base, org_a.admin)
    assert r["procesados"] == 1 and r["cola"]["pendientes"] == 0
    f = _etapa(cliente, base, org_a.admin, "CP-3")
    assert f["etapa"] == "hoja_por_confirmar" and f["espera_persona"]
    assert any("OCR de 4 páginas" in h["que"] and "hoja propuesta desde el OCR: 2 documentos" in h["que"] for h in f["hechos"])
    hc = f"{base}/hojas-control/unidades/{u['CP-3']}"
    d = cliente.get(hc, headers=org_a.admin).json()
    assert [t["tipo_documental"] for t in d["tramites"]] == ["Citación", "Acta"]
    # La persona confirma y envía; otra verifica. El flujo sigue solo con la descripción.
    for t in d["tramites"]:
        cliente.post(f"{hc}/tramites/{t['id']}/confirmar", headers=org_a.admin)
    cliente.post(f"{hc}/enviar", headers=org_a.admin)
    _procesar(cliente, base, org_a.admin)
    assert _etapa(cliente, base, org_a.admin, "CP-3")["etapa"] == "hoja_en_verificacion"
    for t in d["tramites"]:
        cliente.post(f"{hc}/tramites/{t['id']}/revisar", json={"conforme": True}, headers=director)
    cliente.post(f"{hc}/verificar", headers=director)
    _procesar(cliente, base, org_a.admin)
    f = _etapa(cliente, base, org_a.admin, "CP-3")
    assert f["etapa"] == "descripcion_por_confirmar" and any("descripción ISAD(G) propuesta" in h["que"] for h in f["hechos"])
    ds = f"{base}/descripciones/unidades/{u['CP-3']}"
    desc = cliente.get(ds, headers=org_a.admin).json()["descripcion"]
    assert desc["origen"]["fecha_inicial"]["fuente"] == "hoja_control" and desc["campos"]["fecha_inicial"] == "2020-02-03"
    cliente.patch(ds, json={"campos": {"titulo": "Citación y acta de la sesión del comité directivo de febrero de 2020"}}, headers=org_a.admin)
    cliente.post(f"{ds}/confirmar", json={"elemento": "alcance"}, headers=org_a.admin)
    cliente.post(f"{ds}/enviar", headers=org_a.admin)
    _procesar(cliente, base, org_a.admin)
    assert _etapa(cliente, base, org_a.admin, "CP-3")["etapa"] == "descripcion_en_revision"
    cliente.post(f"{ds}/aprobar", headers=director)
    _procesar(cliente, base, org_a.admin)
    assert _etapa(cliente, base, org_a.admin, "CP-3")["etapa"] == "listo"
    tablero = cliente.get(f"{base}/flujo", headers=org_a.admin).json()
    assert {e["clave"]: e["unidades"] for e in tablero["etapas"]}["listo"] == 1
    eventos = cliente.get("/api/v1/auditoria/eventos?limite=200", headers=org_a.admin).json()
    assert any(e["accion"] == "FLUJO_AUTOMATICO" and "OCR de 4 páginas" in (e["detalle"] or "") for e in eventos)


@requiere_tesseract
def test_lote_sin_hoja_describe_desde_el_ocr(cliente, org_a):
    p, base, director, u = _listo(cliente, org_a)
    _configurar(cliente, org_a.admin, base, "HISTORICO", False, True)
    _cargar(cliente, base, org_a.admin, "CP-1.pdf", pdf_con_texto(PAGINAS))
    _procesar(cliente, base, org_a.admin)
    f = _etapa(cliente, base, org_a.admin, "CP-1")
    assert f["etapa"] == "descripcion_por_confirmar"
    assert cliente.get(f"{base}/hojas-control/unidades/{u['CP-1']}", headers=org_a.admin).json()["hoja"] is None  # el lote no lleva hoja
    desc = cliente.get(f"{base}/descripciones/unidades/{u['CP-1']}", headers=org_a.admin).json()["descripcion"]
    assert desc["origen"]["fecha_inicial"]["fuente"] == "ocr"


def test_espera_la_calidad_y_continua_al_decidir(cliente, org_a):
    p, base, director, u = _listo(cliente, org_a)
    _cargar(cliente, base, org_a.admin, "CP-5/0001.tif", imagen(en_blanco=True))
    _procesar(cliente, base, org_a.admin)
    f = _etapa(cliente, base, org_a.admin, "CP-5")
    assert f["etapa"] == "esperando_calidad" and "1 archivos" in f["detalle"]
    assert cliente.get(f"{base}/hojas-control/unidades/{u['CP-5']}", headers=org_a.admin).json()["hoja"] is None  # no avanza sin calidad
    _, revisor = agregar_usuario(cliente, org_a, "calidad@alfa.example.com", "Equipo operativo", [p["id"]])
    recurso = cliente.get(f"{base}/digitalizacion/archivos?estado=en_revision", headers=org_a.admin).json()["recursos"][0]
    cliente.post(f"{base}/digitalizacion/archivos/{recurso['id']}/decidir", json={"decision": "aprobar", "motivo": "Es el reverso en blanco, se conserva"}, headers=revisor)
    assert cliente.get(f"{base}/flujo", headers=org_a.admin).json()["cola"]["pendientes"] == 1  # la decisión lo puso en cola
    _procesar(cliente, base, org_a.admin)
    f = _etapa(cliente, base, org_a.admin, "CP-5")
    assert f["etapa"] == "hoja_por_confirmar"  # el lote del proyecto lleva hoja: ARCA la creó
    assert cliente.get(f"{base}/hojas-control/unidades/{u['CP-5']}", headers=org_a.admin).json()["hoja"]["estado"] == "borrador"


def test_cola_sin_duplicados_iniciar_y_permisos(cliente, org_a, org_b):
    p, base, director, u = _listo(cliente, org_a)
    _cargar(cliente, base, org_a.admin, "CP-5/0001.tif", imagen())
    _cargar(cliente, base, org_a.admin, "CP-5/0002.tif", imagen())
    assert cliente.get(f"{base}/flujo", headers=org_a.admin).json()["cola"]["pendientes"] == 1  # una unidad, un trabajo pendiente
    _procesar(cliente, base, org_a.admin)
    assert cliente.post(f"{base}/flujo/iniciar", headers=org_a.admin).json() == {"encoladas": 1}  # CP-5 no está lista: vuelve a la cola
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(f"{base}/flujo", headers=consulta).status_code == 200
    assert cliente.post(f"{base}/flujo/procesar", headers=consulta).status_code == 403
    assert cliente.get(f"{base}/flujo", headers=org_b.admin).status_code == 404
