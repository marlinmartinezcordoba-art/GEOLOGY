"""M23 · Consulta: búsqueda sin tildes en metadatos, OCR, hoja verificada y descripción aprobada; acceso reservado; alcance. Datos ficticios."""

import io

import openpyxl
from conftest import agregar_usuario, proyecto_basico
from fabricas import fuid_xlsx, pdf_con_texto, pdf_escaneado
from test_m04_instrumentos import ENCABEZADO, _libro
from test_m13_ocr import requiere_tesseract

TRD = [
    ["100", "Dirección general", "100-02", "Actas", "100-02.01", "Actas de comité directivo", "Citación; Acta", 2, 18, "X", "", "", "", "F", "", "Pública"],
    ["110", "Oficina jurídica", "110-05", "Acciones constitucionales", "110-05.01", "Acciones de tutela", "Tutela; Fallo", 2, 8, "", "", "X", "", "E", "Muestreo", "Reservada"],
]
FILAS = [
    [1, "EXP-1", "100-02.01", "Actas del comité directivo de planeación", "2019-01-01", "2019-12-31", "C-1", "1", "", "", 10, "Papel", ""],
    [2, "EXP-2", "100-02.01", "Actas del comité de convivencia", "2021-01-01", "2021-12-31", "C-1", "2", "", "", 12, "Papel", ""],
    [3, "EXP-3", "110-05.01", "Acción de tutela de un ciudadano ficticio", "2020-01-01", "2020-12-31", "C-2", "1", "", "", 30, "Papel", ""],
]


def _proyecto(cliente, org, codigo="P-001"):
    p = proyecto_basico(cliente, org, codigo)
    base = f"/api/v1/proyectos/{p['id']}"
    lote = cliente.post(f"{base}/inventario/lotes", files={"archivo": ("fuid.xlsx", fuid_xlsx(FILAS))}, headers=org.admin).json()
    cliente.post(f"{base}/inventario/lotes/{lote['id']}/integrar", json={}, headers=org.admin)
    _, director = agregar_usuario(cliente, org, f"director.{codigo.lower()}@alfa.example.com", "Dirección de proyecto")
    inst = cliente.post(f"{base}/instrumentos", json={"tipo": "TRD", "nombre": "TRD ficticia"}, headers=org.admin).json()
    v = cliente.post(f"{base}/instrumentos/{inst['id']}/versiones", files={"archivo": ("t.xlsx", _libro(TRD, ENCABEZADO + ["Procedimiento", "Acceso"]))},
                     data={"motivo": "Entrega ficticia"}, headers=org.admin).json()
    assert v["errores"] == [], v["errores"]
    cliente.post(f"{base}/instrumentos/{inst['id']}/versiones/{v['id']}/aprobar", json={"acto_administrativo": "Resolución ficticia", "fecha_acto": "2026-01-01", "motivo": "Aprobada"}, headers=director)
    assert cliente.post(f"{base}/clasificacion/proponer", headers=org.admin).json()["confirmadas"] == 3
    ids = {u["identificador"]: u["id"] for u in cliente.get(f"{base}/inventario/unidades", headers=org.admin).json()["unidades"]}
    return p, base, director, ids


def _buscar(cliente, cab, **params):
    r = cliente.get("/api/v1/consulta/buscar", params=params, headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def test_busca_sin_tildes_en_los_metadatos_y_filtra(cliente, org_a):
    p, base, director, ids = _proyecto(cliente, org_a)
    r = _buscar(cliente, org_a.admin, q="COMITE planeacion")  # sin tildes ni mayúsculas, todas las palabras
    assert [x["identificador"] for x in r["filas"]] == ["EXP-1"] and r["indice"]["reindexadas"] == 3
    assert r["filas"][0]["coincidencias"][0]["fuente"] == "metadatos" and "comité" in r["filas"][0]["coincidencias"][0]["fragmento"]
    assert _buscar(cliente, org_a.admin, q="comité")["total"] == 2
    assert _buscar(cliente, org_a.admin, q='"comité de convivencia"')["total"] == 1  # la frase exacta
    assert _buscar(cliente, org_a.admin, q="Dirección general")["total"] == 2  # la dependencia de la clasificación también cuenta
    assert _buscar(cliente, org_a.admin, codigo="110")["total"] == 1
    assert _buscar(cliente, org_a.admin, desde="2020-06-01", hasta="2021-06-01")["total"] == 2  # se cruzan con el rango
    assert _buscar(cliente, org_a.admin, caja="c-1")["total"] == 2
    assert _buscar(cliente, org_a.admin, fase="central")["total"] == 0
    assert _buscar(cliente, org_a.admin, q="100%")["total"] == 2  # el comodín de SQL no se interpreta
    assert _buscar(cliente, org_a.admin, digitalizadas=True)["total"] == 0
    # El índice se pone al día solo cuando cambia una unidad.
    assert _buscar(cliente, org_a.admin, q="comité")["indice"]["reindexadas"] == 0
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("EXP-2.pdf", pdf_escaneado(2)))], data={"rutas_relativas": ["EXP-2.pdf"]}, headers=org_a.admin)
    r = _buscar(cliente, org_a.admin, digitalizadas=True)
    assert r["total"] == 1 and r["filas"][0]["imagenes"] == 2


@requiere_tesseract
def test_busca_en_el_texto_ocr_y_en_lo_validado(cliente, org_a):
    p, base, director, ids = _proyecto(cliente, org_a)
    paginas = [["ENTIDAD FICTICIA NACIONAL", "ACTA N.º 005", "Comité directivo, 10 de febrero de 2020", "Se aprueba el presupuesto de la vigencia"]]
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("EXP-1.pdf", pdf_con_texto(paginas)))], data={"rutas_relativas": ["EXP-1.pdf"]}, headers=org_a.admin)
    cliente.post(f"{base}/ocr/unidades/{ids['EXP-1']}/leer", json={}, headers=org_a.admin)
    r = _buscar(cliente, org_a.admin, q="presupuesto vigencia")
    assert [x["identificador"] for x in r["filas"]] == ["EXP-1"]
    c = r["filas"][0]["coincidencias"][0]
    assert (c["fuente"], c["donde"], c["pagina"]) == ("ocr", "página 1", 1) and "presupuesto" in c["fragmento"]
    assert _buscar(cliente, org_a.admin, q="presupuesto", fuentes=["metadatos"])["total"] == 0  # se puede buscar solo en una fuente
    # La hoja de control cuenta cuando está verificada, no antes.
    hc = f"{base}/hojas-control/unidades/{ids['EXP-1']}"
    t = cliente.post(hc, json={}, headers=org_a.admin).json()["tramites"][0]
    cliente.patch(f"{hc}/tramites/{t['id']}", json={"tipo_documental": "Acta", "detalle": "Acta de aprobación del plan de compras", "fecha": "2020-02-10"}, headers=org_a.admin)
    assert _buscar(cliente, org_a.admin, q="plan de compras")["total"] == 0
    cliente.post(f"{hc}/enviar", headers=org_a.admin)
    cliente.post(f"{hc}/tramites/{t['id']}/revisar", json={"conforme": True}, headers=director)
    cliente.post(f"{hc}/verificar", headers=director)
    r = _buscar(cliente, org_a.admin, q='"plan de compras"')
    assert r["total"] == 1 and r["filas"][0]["coincidencias"][0]["fuente"] == "hoja" and r["filas"][0]["hoja_verificada"]


def test_acceso_reservado_segun_la_trd(cliente, org_a):
    p, base, director, ids = _proyecto(cliente, org_a)
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("EXP-3.pdf", pdf_escaneado(1)))], data={"rutas_relativas": ["EXP-3.pdf"]}, headers=org_a.admin)
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    r = _buscar(cliente, consulta, q="tutela")
    fila = r["filas"][0]
    assert fila["reservada"] and not fila["contenido_visible"] and fila["acceso"] == "reservada"  # los metadatos sí se ven
    f = cliente.get(f"/api/v1/consulta/proyectos/{p['id']}/unidades/{ids['EXP-3']}", headers=consulta).json()
    assert f["unidad"]["nombre"].startswith("Acción de tutela") and f["paginas"] == [] and not f["contenido_visible"]
    assert cliente.get(f"/api/v1/consulta/proyectos/{p['id']}/unidades/{ids['EXP-3']}/paginas/1/imagen", headers=consulta).status_code == 403
    # La dirección tiene el permiso de consulta reservada.
    f = cliente.get(f"/api/v1/consulta/proyectos/{p['id']}/unidades/{ids['EXP-3']}", headers=director).json()
    assert f["contenido_visible"] and len(f["paginas"]) == 1 and f["clasificacion"]["acceso"] == "reservada"
    img = cliente.get(f"/api/v1/consulta/proyectos/{p['id']}/unidades/{ids['EXP-3']}/paginas/1/imagen", headers=director)
    assert img.status_code == 200 and img.content[:4] == b"\x89PNG"
    eventos = cliente.get("/api/v1/auditoria/eventos?limite=200", headers=org_a.admin).json()
    assert any(e["accion"] == "CONSULTAR_UNIDAD" and "solo metadatos" in (e["detalle"] or "") for e in eventos)


def test_la_entidad_cliente_solo_consulta_su_proyecto_y_exporta(cliente, org_a, org_b):
    p1, _, _, ids = _proyecto(cliente, org_a, "P-001")
    p2, _, _, _ = _proyecto(cliente, org_a, "P-002")
    _, entidad = agregar_usuario(cliente, org_a, "entidad@cliente.example.com", "Entidad cliente", [p1["id"]])
    assert [x["codigo"] for x in cliente.get("/api/v1/consulta/proyectos", headers=entidad).json()] == ["P-001"]
    r = _buscar(cliente, entidad, q="comité")
    assert {x["proyecto"] for x in r["filas"]} == {"P-001"} and r["total"] == 2
    assert _buscar(cliente, org_a.admin, q="comité")["total"] == 4  # la administración ve los dos proyectos
    assert cliente.get("/api/v1/consulta/buscar", params={"proyecto_id": p2["id"]}, headers=entidad).status_code == 404
    assert cliente.get(f"/api/v1/consulta/proyectos/{p2['id']}/unidades/{ids['EXP-1']}", headers=entidad).status_code == 404
    x = cliente.get("/api/v1/consulta/exportar", params={"q": "comité"}, headers=entidad)
    hoja = openpyxl.load_workbook(io.BytesIO(x.content)).active
    filas = [[c.value for c in f] for f in hoja.iter_rows()]
    assert filas[2][:2] == ["Resultados", 2] and {f[1] for f in filas[5:]} == {"EXP-1", "EXP-2"}
    assert cliente.get("/api/v1/consulta/buscar", headers=org_b.admin).json()["total"] == 0
    assert cliente.get("/api/v1/consulta/buscar", params={"fase": "otra"}, headers=org_a.admin).status_code == 422
