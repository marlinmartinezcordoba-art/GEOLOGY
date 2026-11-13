"""Pruebas negativas de aislamiento entre organizaciones (criterio de aceptación de M01 y RNF-04).

Una organización nunca ve, modifica ni intuye datos de otra: por cabecera, por identificador directo,
por listados, por auditoría ni por configuración.
"""

from conftest import agregar_usuario, proyecto_basico


def test_cabecera_de_otra_organizacion_es_rechazada(cliente, org_a, org_b):
    cab = org_a.admin | {"X-Organizacion": org_b.id}
    assert cliente.get("/api/v1/proyectos", headers=cab).status_code == 403
    assert cliente.get("/api/v1/organizacion", headers=cab).status_code == 403


def test_identificador_de_otra_organizacion_responde_404(cliente, org_a, org_b):
    ajeno = proyecto_basico(cliente, org_b, "B-001")
    for metodo, ruta, cuerpo in (
        ("get", f"/api/v1/proyectos/{ajeno['id']}", None),
        ("patch", f"/api/v1/proyectos/{ajeno['id']}", {"nombre": "Robado", "motivo": "Intento cruzado"}),
        ("post", f"/api/v1/proyectos/{ajeno['id']}/sedes", {"nombre": "Sede", "ciudad": "Bogotá"}),
        ("get", f"/api/v1/proyectos/{ajeno['id']}/versiones", None),
        ("post", f"/api/v1/proyectos/{ajeno['id']}/cerrar", {"motivo": "Intento cruzado"}),
    ):
        r = getattr(cliente, metodo)(ruta, headers=org_a.admin, **({"json": cuerpo} if cuerpo else {}))
        assert r.status_code == 404, (ruta, r.status_code)
    assert cliente.get(f"/api/v1/proyectos/{ajeno['id']}", headers=org_b.admin).json()["nombre"] != "Robado"


def test_listados_solo_traen_lo_propio(cliente, org_a, org_b):
    proyecto_basico(cliente, org_a, "A-001")
    proyecto_basico(cliente, org_b, "B-001")
    assert [p["codigo"] for p in cliente.get("/api/v1/proyectos", headers=org_a.admin).json()] == ["A-001"]
    correos = {u["correo"] for u in cliente.get("/api/v1/usuarios", headers=org_a.admin).json()}
    assert correos == {org_a.admin_correo}


def test_roles_y_usuarios_de_otra_organizacion_no_se_pueden_usar(cliente, org_a, org_b):
    rol_ajeno = cliente.get("/api/v1/roles", headers=org_b.admin).json()[0]["id"]
    r = cliente.post("/api/v1/usuarios", json={"correo": "x@alfa.example.com", "nombre_completo": "Equis", "rol_id": rol_ajeno}, headers=org_a.admin)
    assert r.status_code == 404
    usuario_b, _ = agregar_usuario(cliente, org_b, "persona@beta.example.com", "Equipo operativo")
    assert cliente.patch(f"/api/v1/usuarios/{usuario_b}", json={"rol_id": rol_ajeno, "motivo": "Intento cruzado"}, headers=org_a.admin).status_code == 404
    p = proyecto_basico(cliente, org_a, "A-001")
    assert cliente.post(f"/api/v1/proyectos/{p['id']}/equipo", json={"usuario_id": usuario_b}, headers=org_a.admin).status_code == 404
    r = cliente.patch(f"/api/v1/proyectos/{p['id']}", json={"responsable_id": usuario_b, "motivo": "Intento cruzado"}, headers=org_a.admin)
    assert r.status_code == 404


def test_auditoria_y_configuracion_separadas(cliente, org_a, org_b):
    proyecto_basico(cliente, org_b, "B-001")
    cliente.post("/api/v1/configuracion/parametros", json={"clave": "captura.dpi_minimo", "valor": 300, "motivo": "Política de captura"}, headers=org_b.admin)
    eventos_a = cliente.get("/api/v1/auditoria/eventos", headers=org_a.admin).json()
    assert all(e["accion"] != "CREAR_PROYECTO" for e in eventos_a)
    assert cliente.get("/api/v1/configuracion/parametros", headers=org_a.admin).json() == []
    ajeno = proyecto_basico(cliente, org_b, "B-002")
    r = cliente.post(
        "/api/v1/configuracion/parametros",
        json={"clave": "captura.dpi_minimo", "valor": 200, "proyecto_id": ajeno["id"], "motivo": "Intento cruzado"},
        headers=org_a.admin,
    )
    assert r.status_code == 404


def test_alcance_por_proyecto_dentro_de_la_misma_organizacion(cliente, org_a):
    visible = proyecto_basico(cliente, org_a, "A-001")
    oculto = proyecto_basico(cliente, org_a, "A-002")
    _, cab = agregar_usuario(cliente, org_a, "cliente@entidad.example.com", "Entidad cliente", proyectos=[visible["id"]])
    assert [p["codigo"] for p in cliente.get("/api/v1/proyectos", headers=cab).json()] == ["A-001"]
    assert cliente.get(f"/api/v1/proyectos/{oculto['id']}", headers=cab).status_code == 404
