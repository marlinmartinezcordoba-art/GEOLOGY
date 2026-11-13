"""Plantillas de la entidad versionadas y expedición de FUID de salida, rótulos de caja y de carpeta (D-27)."""

import io
from datetime import UTC, datetime, timedelta

import openpyxl
from conftest import agregar_usuario, proyecto_basico
from fabricas import fuid_xlsx

FILAS = [
    [1, "CP-1", "100.01", "Expediente ficticio uno", "1990-01-01", "1990-12-31", "C-1", "1", "", "", 10, "Papel", ""],
    [2, "CP-2", "100.01", "Expediente ficticio dos", "1991-01-01", "1992-06-30", "C-1", "2", "", "", 20, "Papel", ""],
    [3, "CP-3", "100.02", "Expediente ficticio tres", "1985-03-01", "1986-01-01", "C-2", "1", "", "", 30, "Papel", ""],
    [4, "CP-4", "100.02", "Expediente ficticio cuatro", "1985-03-01", "1986-01-01", "C-10", "1", "", "", 5, "Papel", ""],
]


def _proyecto_con_fuid(cliente, org):
    p = proyecto_basico(cliente, org)
    inv = f"/api/v1/proyectos/{p['id']}/inventario"
    lote = cliente.post(f"{inv}/lotes", files={"archivo": ("fuid.xlsx", fuid_xlsx(FILAS))}, headers=org.admin).json()
    cliente.post(f"{inv}/lotes/{lote['id']}/integrar", json={}, headers=org.admin)
    return p


def _formato_entidad() -> bytes:
    """Un formato «propio de la entidad»: membrete, encabezado con texto mixto, fila modelo y firmas combinadas."""
    libro = openpyxl.Workbook()
    h = libro.active
    h["A1"] = "ENTIDAD FICTICIA · Inventario documental"
    h.merge_cells("A1:E1")
    h["A2"] = "Jefe de archivo: {{jefe_de_archivo}} · Proyecto {{codigo_proyecto}}"
    h["A3"], h["B3"] = "Fecha", "{{fecha}}"
    h.append(["Orden", "Código", "Asunto", "Desde", "Folios"])
    h.append(["{{fila.numero_orden}}", "{{fila.identificador}}", "{{fila.nombre}}", "{{fila.fecha_inicial}}", "{{fila.folios}}"])
    h["A7"] = "Total folios: {{total_folios}}"
    h["A9"] = "Elaboró"
    h.merge_cells("A9:C9")
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _crear(cliente, org, tipo, nombre="Formato de la entidad", proyecto_id=None):
    r = cliente.post("/api/v1/plantillas", json={"tipo": tipo, "nombre": nombre, "proyecto_id": proyecto_id}, headers=org.admin)
    assert r.status_code == 201, r.text
    return r.json()


def _publicar(cliente, org, plantilla_id, contenido, motivo="Formato aprobado por la entidad", **extra):
    datos = {"motivo": motivo} | {k: v for k, v in extra.items()}
    return cliente.post(f"/api/v1/plantillas/{plantilla_id}/versiones", files={"archivo": ("formato.xlsx", contenido)}, data=datos, headers=org.admin)


def _abrir(cliente, org, proyecto_id, expedicion_id):
    r = cliente.get(f"/api/v1/proyectos/{proyecto_id}/entregables/{expedicion_id}/archivo", headers=org.admin)
    assert r.status_code == 200
    return openpyxl.load_workbook(io.BytesIO(r.content))


def test_formatos_base_sin_datos(cliente, org_a):
    for tipo in ("fuid", "rotulo_caja", "rotulo_carpeta"):
        r = cliente.get(f"/api/v1/plantillas/tipos/{tipo}/base", headers=org_a.admin)
        textos = " ".join(str(c.value) for f in openpyxl.load_workbook(io.BytesIO(r.content)).active.iter_rows() for c in f if c.value)
        assert "{{" in textos
    tipos = cliente.get("/api/v1/plantillas/tipos", headers=org_a.admin).json()
    assert "fecha_inicial" in tipos["fuid"]["fila"] and "carpetas" in tipos["rotulo_caja"]["encabezado"]


def test_expedir_fuid_sobre_el_formato_de_la_entidad(cliente, org_a):
    p = _proyecto_con_fuid(cliente, org_a)
    pl = _crear(cliente, org_a, "fuid")
    r = _publicar(cliente, org_a, pl["id"], _formato_entidad(), codigo_formato="FOR-INV-01", valores_fijos='{"entidad": "Entidad Ficticia S.A.S."}')
    assert r.status_code == 422 and "jefe_de_archivo" in r.text  # la entidad pidió un dato que ARCA no conoce: se dice
    libro = openpyxl.load_workbook(io.BytesIO(_formato_entidad()))
    libro.active["A2"] = "Proyecto {{codigo_proyecto}} · {{entidad}}"
    salida = io.BytesIO()
    libro.save(salida)
    r = _publicar(cliente, org_a, pl["id"], salida.getvalue(), codigo_formato="FOR-INV-01", valores_fijos='{"entidad": "Entidad Ficticia S.A.S."}')
    assert r.status_code == 201, r.text
    assert r.json()["versiones"][0]["estado"] == "vigente" and "fila.identificador" in r.json()["versiones"][0]["campos"]
    e = cliente.post(f"/api/v1/proyectos/{p['id']}/entregables", json={"tipo": "fuid"}, headers=org_a.admin)
    assert e.status_code == 201, e.text
    assert e.json()["elementos"] == 4 and e.json()["plantilla_version"] == 1 and e.json()["codigo_formato"] == "FOR-INV-01"
    h = _abrir(cliente, org_a, p["id"], e.json()["id"]).active
    assert h["A2"].value == f"Proyecto {p['codigo']} · Entidad Ficticia S.A.S."  # el valor fijo de la versión manda
    assert [h.cell(r, 2).value for r in (5, 6, 7, 8)] == ["CP-1", "CP-2", "CP-3", "CP-4"]
    assert h["E7"].value == 30 and isinstance(h["D5"].value, datetime)  # números y fechas conservan su tipo
    assert h["A10"].value == "Total folios: 65" and h["A12"].value == "Elaboró"  # lo de abajo bajó con la tabla
    assert "A12:C12" in {str(r) for r in h.merged_cells.ranges}


def test_versiones_reemplazo_y_evidencia(cliente, org_a):
    p = _proyecto_con_fuid(cliente, org_a)
    pl = _crear(cliente, org_a, "fuid")
    base = cliente.get("/api/v1/plantillas/tipos/fuid/base", headers=org_a.admin).content
    _publicar(cliente, org_a, pl["id"], base, codigo_formato="FOR-01")
    primera = cliente.post(f"/api/v1/proyectos/{p['id']}/entregables", json={"tipo": "fuid"}, headers=org_a.admin).json()
    pasada = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert _publicar(cliente, org_a, pl["id"], base, vigente_desde=pasada).status_code == 422
    futura = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    r = _publicar(cliente, org_a, pl["id"], base, codigo_formato="FOR-03", vigente_desde=futura).json()
    assert [v["estado"] for v in r["versiones"]] == ["vigente", "programada"]
    r = _publicar(cliente, org_a, pl["id"], base, codigo_formato="FOR-02", motivo="La entidad cambió el formato").json()
    assert [v["estado"] for v in r["versiones"]] == ["reemplazada", "programada", "vigente"]
    segunda = cliente.post(f"/api/v1/proyectos/{p['id']}/entregables", json={"tipo": "fuid"}, headers=org_a.admin).json()
    assert segunda["codigo_formato"] == "FOR-02"
    historial = {x["id"]: x for x in cliente.get(f"/api/v1/proyectos/{p['id']}/entregables", headers=org_a.admin).json()}
    assert historial[primera["id"]]["codigo_formato"] == "FOR-01" and historial[primera["id"]]["plantilla_version"] == 1


def test_la_del_proyecto_prevalece_sobre_la_de_la_organizacion(cliente, org_a):
    p = _proyecto_con_fuid(cliente, org_a)
    base = cliente.get("/api/v1/plantillas/tipos/fuid/base", headers=org_a.admin).content
    _publicar(cliente, org_a, _crear(cliente, org_a, "fuid", "General")["id"], base, codigo_formato="ORG")
    _publicar(cliente, org_a, _crear(cliente, org_a, "fuid", "Del contrato", p["id"])["id"], base, codigo_formato="PROYECTO")
    assert cliente.post(f"/api/v1/proyectos/{p['id']}/entregables", json={"tipo": "fuid"}, headers=org_a.admin).json()["codigo_formato"] == "PROYECTO"


def test_rotulos_de_caja_y_de_carpeta(cliente, org_a):
    p = _proyecto_con_fuid(cliente, org_a)
    for tipo in ("rotulo_caja", "rotulo_carpeta"):
        base = cliente.get(f"/api/v1/plantillas/tipos/{tipo}/base", headers=org_a.admin).content
        _publicar(cliente, org_a, _crear(cliente, org_a, tipo)["id"], base)
    cajas = cliente.post(f"/api/v1/proyectos/{p['id']}/entregables", json={"tipo": "rotulo_caja"}, headers=org_a.admin).json()
    libro = _abrir(cliente, org_a, p["id"], cajas["id"])
    assert cajas["elementos"] == 3 and libro.sheetnames == ["Caja C-1", "Caja C-2", "Caja C-10"]  # orden natural
    textos = [str(c.value) for f in libro["Caja C-1"].iter_rows() for c in f if c.value is not None]
    assert "CP-1" in textos and "CP-2" in textos and "CP-3" not in textos  # cada caja lista sus carpetas
    assert "2" in textos  # carpetas de la caja
    carpetas = cliente.post(f"/api/v1/proyectos/{p['id']}/entregables", json={"tipo": "rotulo_carpeta", "cajas": ["C-2"]}, headers=org_a.admin).json()
    assert carpetas["elementos"] == 1 and _abrir(cliente, org_a, p["id"], carpetas["id"]).sheetnames == ["CP-3"]


def test_sin_plantilla_vigente_se_dice(cliente, org_a):
    p = _proyecto_con_fuid(cliente, org_a)
    r = cliente.post(f"/api/v1/proyectos/{p['id']}/entregables", json={"tipo": "rotulo_caja"}, headers=org_a.admin)
    assert r.status_code == 422 and "No hay una plantilla vigente" in r.json()["detail"]


def test_permisos_y_aislamiento(cliente, org_a, org_b):
    p = _proyecto_con_fuid(cliente, org_a)
    pl = _crear(cliente, org_a, "fuid")
    _publicar(cliente, org_a, pl["id"], cliente.get("/api/v1/plantillas/tipos/fuid/base", headers=org_a.admin).content)
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    assert cliente.post("/api/v1/plantillas", json={"tipo": "fuid", "nombre": "No permitida"}, headers=equipo).status_code == 403
    assert cliente.post(f"/api/v1/proyectos/{p['id']}/entregables", json={"tipo": "fuid"}, headers=equipo).status_code == 201
    assert cliente.get("/api/v1/plantillas", headers=org_b.admin).json() == []
    assert _publicar(cliente, org_b, pl["id"], b"x").status_code == 404
    proyecto_b = proyecto_basico(cliente, org_b, "B-1")
    r = cliente.post(f"/api/v1/proyectos/{proyecto_b['id']}/entregables", json={"tipo": "fuid", "plantilla_id": pl["id"]}, headers=org_b.admin)
    assert r.status_code == 404
