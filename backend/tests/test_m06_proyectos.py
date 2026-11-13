"""M06 · Proyectos: creación, versionado del alcance, activación, cierre y reapertura controlada."""

from conftest import proyecto_basico


def _completar(cliente, org, p):
    yo = cliente.get("/api/v1/auth/yo", headers=org.admin).json()["id"]
    r = cliente.patch(
        f"/api/v1/proyectos/{p['id']}",
        json={
            "fecha_inicio": "2026-12-01",
            "fecha_fin": "2027-06-30",
            "metas": {"cajas": 1200, "imagenes": 450000},
            "responsable_id": yo,
            "motivo": "Alcance contratado",
        },
        headers=org.admin,
    )
    assert r.status_code == 200, r.text
    assert cliente.post(f"/api/v1/proyectos/{p['id']}/sedes", json={"nombre": "Archivo central", "ciudad": "Bogotá"}, headers=org.admin).status_code == 201
    return r.json()


def test_codigo_unico_y_valido(cliente, org_a):
    proyecto_basico(cliente, org_a, "P-001")
    assert (
        cliente.post(
            "/api/v1/proyectos", json={"codigo": "p-001", "nombre": "Proyecto repetido", "entidad_cliente": "Entidad Ficticia"}, headers=org_a.admin
        ).status_code
        == 409
    )
    assert (
        cliente.post(
            "/api/v1/proyectos", json={"codigo": "con espacio", "nombre": "Proyecto malo", "entidad_cliente": "Entidad Ficticia"}, headers=org_a.admin
        ).status_code
        == 422
    )


def test_metas_por_unidad_sin_mezclar(cliente, org_a):
    r = cliente.post(
        "/api/v1/proyectos",
        json={"codigo": "P-1", "nombre": "Proyecto de prueba", "entidad_cliente": "Entidad Ficticia", "metas": {"paginas_o_folios": 10}},
        headers=org_a.admin,
    )
    assert r.status_code == 422
    r = cliente.post(
        "/api/v1/proyectos",
        json={"codigo": "P-2", "nombre": "Proyecto de prueba", "entidad_cliente": "Entidad Ficticia", "metas": {"folios": 10.5}},
        headers=org_a.admin,
    )
    assert r.status_code == 422
    r = cliente.post(
        "/api/v1/proyectos",
        json={"codigo": "P-3", "nombre": "Proyecto de prueba", "entidad_cliente": "Entidad Ficticia", "metas": {"metros_lineales": 12.5, "folios": 3000}},
        headers=org_a.admin,
    )
    assert r.status_code == 201 and r.json()["metas"] == {"metros_lineales": 12.5, "folios": 3000}


def test_fechas_coherentes(cliente, org_a):
    r = cliente.post(
        "/api/v1/proyectos",
        json={"codigo": "P-1", "nombre": "Proyecto de prueba", "entidad_cliente": "Entidad Ficticia", "fecha_inicio": "2027-01-01", "fecha_fin": "2026-01-01"},
        headers=org_a.admin,
    )
    assert r.status_code == 422


def test_activar_exige_alcance_completo(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    r = cliente.post(f"/api/v1/proyectos/{p['id']}/activar", json={"motivo": "Inicio de ejecución"}, headers=org_a.admin)
    assert r.status_code == 422 and "fecha de inicio" in r.json()["detail"] and "sede" in r.json()["detail"]
    _completar(cliente, org_a, p)
    r = cliente.post(f"/api/v1/proyectos/{p['id']}/activar", json={"motivo": "Inicio de ejecución"}, headers=org_a.admin)
    assert r.status_code == 200 and r.json()["estado"] == "activo"
    r = cliente.patch(f"/api/v1/proyectos/{p['id']}", json={"metas": {}, "motivo": "Quitar metas"}, headers=org_a.admin)
    assert r.status_code == 422  # un proyecto activo no puede quedar sin metas


def test_alcance_versionado(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    _completar(cliente, org_a, p)
    r = cliente.patch(f"/api/v1/proyectos/{p['id']}", json={"metas": {"cajas": 1500, "imagenes": 450000}, "motivo": "Otrosí No. 1"}, headers=org_a.admin)
    assert r.json()["version"] == 3
    versiones = cliente.get(f"/api/v1/proyectos/{p['id']}/versiones", headers=org_a.admin).json()
    assert [v["version"] for v in versiones] == [1, 2, 3]
    assert versiones[1]["instantanea"]["metas"]["cajas"] == 1200 and versiones[2]["instantanea"]["metas"]["cajas"] == 1500
    assert versiones[2]["motivo"] == "Otrosí No. 1"
    # Un cambio sin diferencias no crea versión.
    r = cliente.patch(f"/api/v1/proyectos/{p['id']}", json={"metas": {"cajas": 1500, "imagenes": 450000}, "motivo": "Sin cambios"}, headers=org_a.admin)
    assert r.json()["version"] == 3


def test_cerrar_y_reabrir_con_motivo(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    _completar(cliente, org_a, p)
    url = f"/api/v1/proyectos/{p['id']}"
    assert cliente.post(f"{url}/cerrar", json={"motivo": "Borrador"}, headers=org_a.admin).status_code == 422  # un borrador no se cierra
    cliente.post(f"{url}/activar", json={"motivo": "Inicio de ejecución"}, headers=org_a.admin)
    assert cliente.post(f"{url}/cerrar", json={"motivo": "Acta de liquidación"}, headers=org_a.admin).json()["estado"] == "cerrado"
    assert cliente.patch(url, json={"nombre": "Cambio", "motivo": "Tras el cierre"}, headers=org_a.admin).status_code == 422
    assert cliente.post(f"{url}/sedes", json={"nombre": "Otra"}, headers=org_a.admin).status_code == 422
    assert cliente.post(f"{url}/activar", json={"motivo": "Por la puerta de atrás"}, headers=org_a.admin).status_code == 422
    assert cliente.post(f"{url}/reabrir", json={"motivo": "Requerimiento de la interventoría"}, headers=org_a.admin).json()["estado"] == "activo"
    acciones = [e["accion"] for e in cliente.get(f"/api/v1/auditoria/eventos?objeto_id={p['id']}", headers=org_a.admin).json()]
    assert {"CREAR_PROYECTO", "ACTIVAR_PROYECTO", "CERRAR_PROYECTO", "REABRIR_PROYECTO"} <= set(acciones)
