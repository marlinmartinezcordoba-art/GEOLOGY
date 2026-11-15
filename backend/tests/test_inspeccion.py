"""Inspección de calidad por lote con muestreo de aceptación (D-42). Lotes, expedientes y personas ficticias."""

import io

import openpyxl
from conftest import agregar_usuario
from fabricas import pdf_escaneado
from test_descripcion import _listo

PLAN = {"unidad": "expedientes", "metodo": "porcentaje", "porcentaje": 100, "minimo": 1, "aceptacion": {"critico": 0, "mayor": 0, "menor": 1},
        "defectos": [{"codigo": "faltante", "nombre": "Página faltante", "severidad": "critico"},
                     {"codigo": "orden", "nombre": "Páginas fuera de orden", "severidad": "mayor"},
                     {"codigo": "inclinada", "nombre": "Imagen inclinada", "severidad": "menor"},
                     {"codigo": "deterioro", "nombre": "Deterioro del original", "severidad": "limitacion"}],
        "frente": "F1", "exigir_para_entrega": True, "motivo": "Plan del pliego ficticio"}


def _escenario(cliente, org):
    """C-1 (lote HISTORICO): CP-1 con 2 páginas y CP-2 con 1; C-2 (lote AMBOS): CP-3 con 1. Lo cargó la administración."""
    p, base, director, u = _listo(cliente, org)
    for nombre, paginas in (("CP-1.pdf", 2), ("CP-2.pdf", 1), ("CP-3.pdf", 1)):
        r = cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", (nombre, pdf_escaneado(paginas)))], data={"rutas_relativas": [nombre]}, headers=org.admin)
        assert r.status_code == 200, r.text
    _, inspector = agregar_usuario(cliente, org, "calidad@alfa.example.com", "Equipo operativo", [p["id"]])
    return p, f"{base}/inspeccion", director, inspector, u


def _plan(cliente, insp, cab, **cambios):
    return cliente.put(f"{insp}/plan", json=PLAN | cambios, headers=cab)


def _revisar(cliente, insp, cab, d, orden, *codigos):
    item = next(x for x in d["items"] if x["orden"] == orden)
    r = cliente.put(f"{insp}/inspecciones/{d['id']}/items/{item['id']}", json={"defectos": [{"codigo": c, "nota": "ficticia"} for c in codigos]}, headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def test_plan_lo_fija_la_direccion(cliente, org_a):
    p, insp, director, inspector, _ = _escenario(cliente, org_a)
    v = cliente.get(f"{insp}/plan", headers=inspector).json()
    assert not v["vigente"] and v["plan"]["aceptacion"] == {"critico": 0, "mayor": 1, "menor": 3} and "pliego" in v["aviso"]
    r = cliente.post(f"{insp}/inspecciones", json={"lote": "HISTORICO"}, headers=inspector)
    assert r.status_code == 422 and "plan de muestreo" in r.text  # sin plan no se inspecciona
    assert _plan(cliente, insp, inspector).status_code == 403  # lo fija la dirección
    r = _plan(cliente, insp, director, aceptacion={"critico": 0}, metodo="tabla", tabla=[{"desde": 1, "hasta": 10, "muestra": 2}, {"desde": 5, "hasta": 20, "muestra": 3}])
    assert r.status_code == 422 and "se cruza" in r.text and "mayores" in r.text
    v = _plan(cliente, insp, director).json()
    assert v["vigente"] and v["plan"]["version"] == 1 and v["motivo"] == "Plan del pliego ficticio"
    lotes = {x["lote"]: x for x in cliente.get(f"{insp}/lotes", headers=inspector).json()}
    assert (lotes["HISTORICO"]["expedientes"], lotes["HISTORICO"]["imagenes"], lotes["AMBOS"]["expedientes"]) == (2, 3, 1)


def test_muestra_revision_decision_acta_y_productividad(cliente, org_a):
    p, insp, director, inspector, _ = _escenario(cliente, org_a)
    _plan(cliente, insp, director)
    d = cliente.post(f"{insp}/inspecciones", json={"lote": "HISTORICO", "semilla": 42}, headers=inspector).json()
    assert (d["tamano"], d["muestra"], d["semilla"], d["estado"]) == (2, 2, 42, "abierta")
    assert {x["identificador"] for x in d["items"]} == {"CP-1", "CP-2"}
    assert cliente.post(f"{insp}/inspecciones", json={"lote": "HISTORICO"}, headers=inspector).status_code == 422  # una abierta por lote
    item = d["items"][0]
    r = cliente.put(f"{insp}/inspecciones/{d['id']}/items/{item['id']}", json={"defectos": []}, headers=org_a.admin)
    assert r.status_code == 403 and "otra persona" in r.text  # quien cargó no inspecciona
    r = cliente.put(f"{insp}/inspecciones/{d['id']}/items/{item['id']}", json={"defectos": [{"codigo": "inventado"}]}, headers=inspector)
    assert r.status_code == 422  # solo el catálogo del plan
    assert cliente.post(f"{insp}/inspecciones/{d['id']}/cerrar", json={}, headers=inspector).status_code == 422  # falta revisar
    _revisar(cliente, insp, inspector, d, 1, "inclinada")
    d = _revisar(cliente, insp, inspector, d, 2, "deterioro")
    assert d["conteo"] == {"critico": 0, "mayor": 0, "menor": 1, "limitacion": 1} and d["resultado_previsto"] == "aceptada"
    d = cliente.post(f"{insp}/inspecciones/{d['id']}/cerrar", json={"observaciones": "Sin novedad mayor"}, headers=inspector).json()
    assert d["estado"] == "aceptada" and d["cerrada_por"] == "Persona calidad@alfa.example.com"
    assert cliente.post(f"{insp}/inspecciones/{d['id']}/anular", json={"motivo": "Se abrió por error"}, headers=director).status_code == 422  # cerrada = evidencia
    # El acta y el registro de calidad de productividad.
    acta = openpyxl.load_workbook(io.BytesIO(cliente.get(f"{insp}/inspecciones/{d['id']}/acta", headers=inspector).content)).active
    textos = [str(c.value) for f in acta.iter_rows() for c in f if c.value is not None]
    assert "LOTE ACEPTADO" in textos and "42" in textos and "Imagen inclinada" in textos and any("1 limitaciones del original (no cuentan)" in t for t in textos)
    calidad = cliente.get(f"/api/v1/proyectos/{p['id']}/productividad/tablas/fCalidad", headers=director).json()
    assert [(c["Lote"], c["Muestra"], c["Menores"], c["Limitaciones_Original"], c["Resultado"], c["Cod_Frente"]) for c in calidad] == [("HISTORICO", 2, 1, 1, "Aprobado", "F1")]
    eventos = {e["accion"] for e in cliente.get("/api/v1/auditoria/eventos?limite=200", headers=org_a.admin).json()}
    assert {"PLAN_MUESTREO", "INICIAR_INSPECCION", "REVISAR_MUESTRA", "CERRAR_INSPECCION", "EXPEDIR_ACTA_INSPECCION"} <= eventos


def test_rechazo_reinspeccion_y_paquete_de_entrega(cliente, org_a):
    p, insp, director, inspector, _ = _escenario(cliente, org_a)
    _plan(cliente, insp, director)
    d = cliente.post(f"{insp}/inspecciones", json={"lote": "AMBOS"}, headers=inspector).json()
    d = _revisar(cliente, insp, inspector, d, 1, "faltante", "orden")
    assert d["resultado_previsto"] == "rechazada" and any("1 defectos críticos (se aceptan 0)" in x for x in d["razones"])
    primera = cliente.post(f"{insp}/inspecciones/{d['id']}/cerrar", json={}, headers=inspector).json()
    assert primera["estado"] == "rechazada"
    # El paquete de entrega dice por qué no entra cada expediente.
    r = cliente.post(f"/api/v1/proyectos/{p['id']}/entrega/paquetes", json={}, headers=org_a.admin)
    assert r.status_code == 422 and "fue rechazado en la inspección de calidad" in r.text and "no ha pasado la inspección de calidad" in r.text
    # Reinspección con muestra nueva, ligada a la rechazada.
    d = cliente.post(f"{insp}/inspecciones", json={"lote": "AMBOS"}, headers=inspector).json()
    assert d["reinspeccion_de"] == primera["id"] and d["items"][0]["defectos"] == []
    assert [i["estado"] for i in cliente.get(f"{insp}/inspecciones", headers=inspector).json()] == ["abierta", "rechazada"]


def test_imagenes_por_tabla_y_semilla_reproducible(cliente, org_a, org_b):
    p, insp, director, inspector, _ = _escenario(cliente, org_a)
    _plan(cliente, insp, director, unidad="imagenes", metodo="tabla", tabla=[{"desde": 1, "hasta": 2, "muestra": 1}])
    r = cliente.post(f"{insp}/inspecciones", json={"lote": "HISTORICO"}, headers=inspector)
    assert r.status_code == 422 and "lote de 3" in r.text  # la tabla no cubre el lote: se dice
    _plan(cliente, insp, director, unidad="imagenes", metodo="tabla", tabla=[{"desde": 1, "hasta": 2, "muestra": 1}, {"desde": 3, "hasta": 50, "muestra": 2}])
    d = cliente.post(f"{insp}/inspecciones", json={"lote": "HISTORICO", "semilla": 7}, headers=inspector).json()
    assert (d["tamano"], d["muestra"]) == (3, 2) and all(x["pagina"] for x in d["items"])
    muestra = [(x["identificador"], x["pagina"]) for x in d["items"]]
    assert cliente.post(f"{insp}/inspecciones/{d['id']}/anular", json={"motivo": "Prueba de reproducibilidad"}, headers=inspector).status_code == 403
    cliente.post(f"{insp}/inspecciones/{d['id']}/anular", json={"motivo": "Prueba de reproducibilidad"}, headers=director)
    otra = cliente.post(f"{insp}/inspecciones", json={"lote": "HISTORICO", "semilla": 7}, headers=inspector).json()
    assert [(x["identificador"], x["pagina"]) for x in otra["items"]] == muestra  # la misma semilla da la misma muestra
    # Permisos y aislamiento.
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(f"{insp}/inspecciones/{otra['id']}", headers=consulta).status_code == 200
    assert cliente.post(f"{insp}/inspecciones", json={"lote": "AMBOS"}, headers=consulta).status_code == 403
    assert cliente.get(f"{insp}/inspecciones", headers=org_b.admin).status_code == 404
