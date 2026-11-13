"""M04 · TRD, TVD y CCD del proyecto: importar, validar, aprobar con acto administrativo, versionar y comparar.

Todos los datos son ficticios.
"""

import io
from datetime import UTC, date, datetime, timedelta

import openpyxl
from conftest import agregar_usuario, proyecto_basico
from fabricas import fuid_xlsx

ENCABEZADO = ["Código dependencia", "Dependencia", "Código serie", "Serie", "Código subserie", "Subserie", "Tipos documentales", "AG", "AC", "CT", "E", "S", "M/D", "Soporte"]
BASE = [
    ["100", "Dirección general", "100-02", "Actas", "100-02.01", "Actas de comité directivo", "Citación; Acta", 2, 18, "X", "", "", "", "F"],
    ["100", "Dirección general", "100-05", "Decretos", "", "", "Decreto; Soportes", 2, 18, "X", "", "", "", "F"],
    ["110", "Oficina jurídica", "110-05", "Acciones constitucionales", "110-05.01", "Acciones de tutela", "Tutela; Fallo", 2, 8, "", "", "X", "", "E"],
]


def _libro(filas, encabezado=ENCABEZADO) -> bytes:
    libro = openpyxl.Workbook()
    h = libro.active
    h.append(encabezado)
    for f in filas:
        h.append(f)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _base(cliente, org):
    p = proyecto_basico(cliente, org)
    url = f"/api/v1/proyectos/{p['id']}/instrumentos"
    r = cliente.post(url, json={"tipo": "TRD", "nombre": "TRD de la entidad"}, headers=org.admin)
    assert r.status_code == 201, r.text
    return p, url, r.json()


def _importar(cliente, cab, url, instrumento_id, contenido, motivo="Instrumento entregado por la entidad"):
    return cliente.post(f"{url}/{instrumento_id}/versiones", files={"archivo": ("trd.xlsx", contenido)}, data={"motivo": motivo}, headers=cab)


def _aprobar(cliente, cab, url, instrumento_id, version_id, **extra):
    cuerpo = {"acto_administrativo": "Resolución 001 (ficticia)", "fecha_acto": date.today().isoformat(), "motivo": "Aprobada por el comité"} | extra
    return cliente.post(f"{url}/{instrumento_id}/versiones/{version_id}/aprobar", json=cuerpo, headers=cab)


def test_plantilla_e_importacion(cliente, org_a):
    p, url, inst = _base(cliente, org_a)
    libro = openpyxl.load_workbook(io.BytesIO(cliente.get(f"{url}/plantilla?tipo=TRD", headers=org_a.admin).content))
    assert libro.sheetnames == ["TRD", "Instrucciones"]
    r = _importar(cliente, org_a.admin, url, inst["id"], _libro(BASE))
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["estado"] == "borrador" and v["version"] == 1 and v["errores"] == []
    assert v["totales"] == {"dependencias": 2, "series": 3, "subseries": 2, "tipos_documentales": 6}
    d = cliente.get(f"{url}/{inst['id']}/versiones/{v['id']}", headers=org_a.admin).json()
    tutela = next(e for e in d["elementos"] if e["codigo"] == "110-05.01")
    assert tutela["nivel"] == "subserie" and tutela["padre"] == "110-05" and tutela["retencion_central"] == 8 and tutela["disposicion"] == "S"
    assert tutela["tipos_documentales"] == ["Tutela", "Fallo"] and tutela["fila"] is not None  # de dónde salió cada dato
    assert [e["nivel"] for e in d["elementos"][:1]] == ["dependencia"]
    fuente = cliente.get(f"{url}/{inst['id']}/versiones/{v['id']}/archivo", headers=org_a.admin)
    assert fuente.status_code == 200 and fuente.headers["x-content-sha256"] == d["sha256"]


def test_lo_que_falta_es_error_y_bloquea(cliente, org_a):
    _, url, inst = _base(cliente, org_a)
    _, director = agregar_usuario(cliente, org_a, "director@alfa.example.com", "Dirección de proyecto")
    malas = [BASE[0], ["100", "Dirección general", "100-05", "Decretos", "", "", "Decreto", "", 18, "X", "", "", "", "F"]]
    v = _importar(cliente, org_a.admin, url, inst["id"], _libro(malas)).json()
    assert v["errores"] and any("AG" in e for e in v["errores"])  # no se inventa la retención
    r = _aprobar(cliente, director, url, inst["id"], v["id"])
    assert r.status_code == 422 and "errores" in r.json()["detail"]
    assert _importar(cliente, org_a.admin, url, inst["id"], _libro(BASE)).status_code == 409  # un borrador a la vez
    r = cliente.post(f"{url}/{inst['id']}/versiones/{v['id']}/descartar", json={"motivo": "Archivo con errores"}, headers=org_a.admin)
    assert r.json()["versiones"][0]["estado"] == "descartada"
    assert _importar(cliente, org_a.admin, url, inst["id"], _libro(BASE)).json()["version"] == 2


def test_aprobacion_segregada_versiones_y_reemplazo(cliente, org_a):
    _, url, inst = _base(cliente, org_a)
    _, director = agregar_usuario(cliente, org_a, "director@alfa.example.com", "Dirección de proyecto")
    v1 = _importar(cliente, org_a.admin, url, inst["id"], _libro(BASE)).json()
    assert _aprobar(cliente, org_a.admin, url, inst["id"], v1["id"]).status_code == 403  # quien importa no aprueba
    futura = date.today() + timedelta(days=3)
    assert _aprobar(cliente, director, url, inst["id"], v1["id"], fecha_acto=futura.isoformat()).status_code == 422
    pasada = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert _aprobar(cliente, director, url, inst["id"], v1["id"], vigente_desde=pasada).status_code == 422
    r = _aprobar(cliente, director, url, inst["id"], v1["id"], convalidacion="Concepto de convalidación ficticio")
    assert r.status_code == 200, r.text
    assert [x["estado"] for x in r.json()["versiones"]] == ["vigente"] and r.json()["versiones"][0]["acto_administrativo"] == "Resolución 001 (ficticia)"
    # Versión 2 programada para dentro de un mes: la 1 sigue vigente.
    v2 = _importar(cliente, org_a.admin, url, inst["id"], _libro(BASE[:2])).json()
    programada = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    r = _aprobar(cliente, director, url, inst["id"], v2["id"], vigente_desde=programada)
    assert [x["estado"] for x in r.json()["versiones"]] == ["vigente", "programada"]
    # Versión 3 desde ahora: reemplaza a la 1, que queda como evidencia; la 2 sigue programada.
    cambiada = [BASE[0], BASE[1], ["110", "Oficina jurídica", "110-05", "Acciones constitucionales", "110-05.01", "Acciones de tutela", "Tutela; Fallo", 3, 7, "", "", "X", "", "E"],
                ["110", "Oficina jurídica", "110-08", "Conceptos", "", "", "Concepto", 2, 3, "", "X", "", "", "F"]]
    v3 = _importar(cliente, org_a.admin, url, inst["id"], _libro(cambiada)).json()
    r = _aprobar(cliente, director, url, inst["id"], v3["id"], acto_administrativo="Resolución 002 (ficticia)")
    assert [x["estado"] for x in r.json()["versiones"]] == ["reemplazada", "programada", "vigente"]
    assert cliente.post(f"{url}/{inst['id']}/versiones/{v1['id']}/descartar", json={"motivo": "No aplica"}, headers=org_a.admin).status_code == 422
    c = cliente.get(f"{url}/{inst['id']}/comparar?desde={v1['id']}&hasta={v3['id']}", headers=org_a.admin).json()
    assert [x["codigo"] for x in c["nuevas"]] == ["110-08"] and c["retiradas"] == []
    tutela = next(x for x in c["modificadas"] if x["codigo"] == "110-05.01")
    assert tutela["cambios"]["retencion_gestion"] == [2, 3] and tutela["cambios"]["retencion_central"] == [8, 7]
    eventos = {e["accion"] for e in cliente.get("/api/v1/auditoria/eventos?limite=200", headers=org_a.admin).json()}
    assert {"CREAR_INSTRUMENTO", "IMPORTAR_INSTRUMENTO", "APROBAR_INSTRUMENTO"} <= eventos


def test_tvd_y_ccd(cliente, org_a):
    p, url, _ = _base(cliente, org_a)
    tvd = cliente.post(url, json={"tipo": "TVD", "nombre": "TVD fondo acumulado", "periodo_desde": "1970-01-01", "periodo_hasta": "1999-12-31"}, headers=org_a.admin).json()
    v = _importar(cliente, org_a.admin, url, tvd["id"], _libro(BASE)).json()
    assert v["errores"] == [] and v["totales"]["series"] == 3
    ccd = cliente.post(url, json={"tipo": "CCD", "nombre": "Cuadro de clasificación"}, headers=org_a.admin).json()
    sin_retencion = [f[:7] for f in BASE]
    v = _importar(cliente, org_a.admin, url, ccd["id"], _libro(sin_retencion, ENCABEZADO[:7])).json()
    assert v["errores"] == [], v["errores"]  # el CCD clasifica: no exige retención ni disposición
    assert cliente.post(url, json={"tipo": "OTRO", "nombre": "No existe"}, headers=org_a.admin).status_code == 422
    assert cliente.post(url, json={"tipo": "TRD", "nombre": "TRD de la entidad"}, headers=org_a.admin).status_code == 409
    tipos = [i["tipo"] for i in cliente.get(url, headers=org_a.admin).json()]
    assert tipos == ["CCD", "TRD", "TVD"]


def test_el_fuid_avisa_codigos_fuera_de_la_trd_vigente(cliente, org_a):
    p, url, inst = _base(cliente, org_a)
    _, director = agregar_usuario(cliente, org_a, "director@alfa.example.com", "Dirección de proyecto")
    v = _importar(cliente, org_a.admin, url, inst["id"], _libro(BASE)).json()
    _aprobar(cliente, director, url, inst["id"], v["id"])
    filas = [[1, "CP-1", "100-02.01", "Expediente ficticio", "1990-01-01", "1990-12-31", "C-1", "1", "", "", 10, "Papel", ""],
             [2, "CP-2", "999-99", "Expediente ficticio dos", "1990-01-01", "1990-12-31", "C-1", "2", "", "", 10, "Papel", ""]]
    inv = f"/api/v1/proyectos/{p['id']}/inventario"
    lote = cliente.post(f"{inv}/lotes", files={"archivo": ("fuid.xlsx", fuid_xlsx(filas))}, headers=org_a.admin).json()
    resultado = {f["normalizado"]["identificador"]: f["avisos"] for f in cliente.get(f"{inv}/lotes/{lote['id']}/filas", headers=org_a.admin).json()}
    assert not any("TRD" in a for a in resultado["CP-1"]) and any("999-99" in a for a in resultado["CP-2"])


def test_permisos_y_aislamiento(cliente, org_a, org_b):
    p, url, inst = _base(cliente, org_a)
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo", [p["id"]])
    assert cliente.get(url, headers=equipo).status_code == 200
    assert cliente.post(url, json={"tipo": "TVD", "nombre": "No permitida"}, headers=equipo).status_code == 403
    v = _importar(cliente, org_a.admin, url, inst["id"], _libro(BASE)).json()
    assert _aprobar(cliente, equipo, url, inst["id"], v["id"]).status_code == 403
    assert cliente.get(url, headers=org_b.admin).status_code == 404
    pb = proyecto_basico(cliente, org_b, "B-1")
    assert cliente.get(f"/api/v1/proyectos/{pb['id']}/instrumentos/{inst['id']}/versiones/{v['id']}", headers=org_b.admin).status_code == 404
