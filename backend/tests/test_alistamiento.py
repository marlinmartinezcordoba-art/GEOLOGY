"""Alistamiento físico por expediente (D-44). Cajas, expedientes y personas ficticias."""

import io

import openpyxl
from conftest import agregar_usuario
from fabricas import pdf_escaneado
from test_historias import _proyecto
from test_m24_productividad import _libro

ACTIVIDADES = [
    {"codigo": "ordenacion", "nombre": "Ordenación cronológica", "cantidad": "ninguna", "obligatoria": True},
    {"codigo": "foliacion", "nombre": "Foliación", "cantidad": "folios", "obligatoria": True},
    {"codigo": "carpeta", "nombre": "Cambio de carpeta", "cantidad": "unidades", "obligatoria": False},
]


def _plan(cliente, al, cab, actividades=ACTIVIDADES):
    return cliente.put(f"{al}/plan", json={"actividades": actividades, "exigir_para_entrega": True, "motivo": "Actividades del pliego ficticio"}, headers=cab)


def test_plan_registro_por_caja_avance_y_controles(cliente, org_a, org_b):
    p, base, director, u = _proyecto(cliente, org_a)  # C-1: HL-1, HL-2 · C-2: HL-3, HL-4
    al = f"{base}/alistamiento"
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo", [p["id"]])
    v = cliente.get(f"{al}/plan", headers=equipo).json()
    assert not v["vigente"] and {a["codigo"] for a in v["actividades"]} >= {"foliacion", "ordenacion", "material"}
    r = cliente.post(f"{al}/registrar", json={"actividad": "ordenacion", "cajas": ["C-1"]}, headers=equipo)
    assert r.status_code == 422 and "actividades de alistamiento" in r.text  # sin plan no se registra
    assert _plan(cliente, al, equipo).status_code == 403  # lo fija la dirección
    assert _plan(cliente, al, director, [{"codigo": "x", "nombre": "Medir", "cantidad": "metros"}]).status_code == 422
    assert _plan(cliente, al, director).json()["version"] == 1
    # Por caja entera; la foliación pide los folios de cada expediente.
    assert cliente.post(f"{al}/registrar", json={"actividad": "ordenacion", "cajas": ["c-1"]}, headers=equipo).json() == {"registrados": 2}
    r = cliente.post(f"{al}/registrar", json={"actividad": "foliacion", "cajas": ["C-1"]}, headers=equipo)
    assert r.status_code == 422 and "HL-1" in r.text
    r = cliente.post(f"{al}/registrar", json={"actividad": "foliacion", "cajas": ["C-1"], "cantidades": {u["HL-1"]: 3, u["HL-2"]: 5}, "observacion": "Sin novedad"}, headers=equipo)
    assert r.json() == {"registrados": 2}
    avance = cliente.get(f"{al}/cajas", headers=equipo).json()
    cajas = {c["caja"]: c for c in avance["cajas"]}
    assert (cajas["C-1"]["completos"], cajas["C-2"]["completos"], avance["resumen"]["por_actividad"]["foliacion"]) == (2, 0, 2)  # el cambio de carpeta no es obligatorio
    exp = {e["identificador"]: e for e in cliente.get(f"{al}/expedientes", params={"caja": "C-1"}, headers=equipo).json()}
    assert exp["HL-1"]["hechas"]["foliacion"]["cantidad"] == 3 and exp["HL-1"]["hechas"]["foliacion"]["hecho_por"] == "Persona equipo@alfa.example.com"
    # La hoja de control avisa lo que falta y si la foliación no coincide.
    hc = f"{base}/hojas-control/unidades"
    cliente.post(f"{hc}/{u['HL-3']}", json={}, headers=equipo)
    avisos = cliente.get(f"{hc}/{u['HL-3']}", headers=equipo).json()["validacion"]["avisos"]
    assert "alistamiento físico pendiente: Ordenación cronológica, Foliación" in avisos
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("HL-1.pdf", pdf_escaneado(2)))], data={"rutas_relativas": ["HL-1.pdf"]}, headers=org_a.admin)
    cliente.post(f"{hc}/{u['HL-1']}", json={}, headers=equipo)
    avisos = cliente.get(f"{hc}/{u['HL-1']}", headers=equipo).json()["validacion"]["avisos"]
    assert "la foliación del alistamiento registró 3 folios y la hoja de control suma 2" in avisos
    # Productividad cuenta sola los folios foliados.
    libro = openpyxl.load_workbook(io.BytesIO(_libro()))
    libro["dActividades"].append(["F1-05 · Foliación", "F1", 5, "Foliación", "folios", "Auxiliar", "No", "alistamiento.foliacion.cantidad"])
    salida = io.BytesIO()
    libro.save(salida)
    assert cliente.post(f"{base}/productividad/libro", files={"archivo": ("p.xlsx", salida.getvalue())}, headers=director).status_code == 200
    automaticas = [f for f in cliente.get(f"{base}/productividad/tablas/fProduccion", headers=director).json() if f["Actividad"] == "F1-05 · Foliación"]
    assert sum(f["Cantidad"] for f in automaticas) == 8
    # Deshacer exige motivo; el paquete de entrega dice qué alistamiento falta.
    deshacer = f"{al}/expedientes/{u['HL-1']}/foliacion/deshacer"
    assert cliente.post(deshacer, json={"motivo": "x"}, headers=equipo).status_code == 422
    assert cliente.post(deshacer, json={"motivo": "Se refolia por error en el conteo"}, headers=equipo).status_code == 200
    assert {c["caja"]: c for c in cliente.get(f"{al}/cajas", headers=equipo).json()["cajas"]}["C-1"]["completos"] == 1
    r = cliente.post(f"{base}/entrega/paquetes", json={}, headers=org_a.admin)
    assert r.status_code == 422 and "falta el alistamiento: Foliación" in r.text
    eventos = {e["accion"] for e in cliente.get("/api/v1/auditoria/eventos?limite=200", headers=org_a.admin).json()}
    assert {"PLAN_ALISTAMIENTO", "REGISTRAR_ALISTAMIENTO", "DESHACER_ALISTAMIENTO"} <= eventos
    # Permisos y aislamiento.
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(f"{al}/cajas", headers=consulta).status_code == 200
    assert cliente.post(f"{al}/registrar", json={"actividad": "ordenacion", "cajas": ["C-2"]}, headers=consulta).status_code == 403
    assert cliente.get(f"{al}/cajas", headers=org_b.admin).status_code == 404


def test_diagnostico_de_conservacion(cliente, org_a):
    p, base, director, u = _proyecto(cliente, org_a)
    al = f"{base}/alistamiento"
    cat = cliente.get(f"{al}/diagnostico/catalogo", headers=org_a.admin).json()
    assert cat["hallazgos"]["biologico"]["aislar"] is True and "malo" in cat["estados"]
    d = f"{al}/expedientes/{u['HL-3']}/diagnostico"
    assert cliente.put(d, json={"estado": "pésimo"}, headers=org_a.admin).status_code == 422
    assert cliente.put(d, json={"estado": "bueno", "hallazgos": ["humedad"]}, headers=org_a.admin).status_code == 422
    assert cliente.put(d, json={"estado": "malo", "hallazgos": ["otro"]}, headers=org_a.admin).status_code == 422  # «otro» pide observación
    r = cliente.put(d, json={"estado": "malo", "hallazgos": ["biologico", "humedad"], "folios_afectados": 4, "observacion": "Hongos en los folios 3 a 6"}, headers=org_a.admin)
    assert r.status_code == 200 and r.json()["aislar"] is True
    cliente.put(f"{al}/expedientes/{u['HL-4']}/diagnostico", json={"estado": "bueno"}, headers=org_a.admin)
    resumen = cliente.get(f"{al}/cajas", headers=org_a.admin).json()["resumen"]["diagnostico"]
    assert resumen == {"registrados": 2, "bueno": 1, "regular": 0, "malo": 1, "aislar": 1}
    exp = {e["identificador"]: e for e in cliente.get(f"{al}/expedientes", params={"caja": "C-2"}, headers=org_a.admin).json()}
    assert exp["HL-3"]["diagnostico"]["folios_afectados"] == 4 and exp["HL-4"]["diagnostico"]["estado"] == "bueno"
    hc = f"{base}/hojas-control/unidades/{u['HL-3']}"
    cliente.post(hc, json={}, headers=org_a.admin)
    avisos = cliente.get(hc, headers=org_a.admin).json()["validacion"]["avisos"]
    assert any("conservación malo" in a and "AISLAR" in a for a in avisos)  # aunque no haya plan de alistamiento
