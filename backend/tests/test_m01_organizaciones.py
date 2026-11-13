"""M01 · Crear, editar, suspender y reactivar organizaciones; límites del plan; el operador no ve contenido."""

from conftest import NIT_A, crear_org, ingresar, proyecto_basico

from arca.nucleo.seguridad import digito_verificacion_nit, normalizar_nit


def test_digito_verificacion_nit():
    assert digito_verificacion_nit("800197268") == 4
    assert digito_verificacion_nit("900123456") == 8
    assert normalizar_nit("900.123.456-8") == "900123456-8"


def test_crear_organizacion_siembra_roles_y_administrador(cliente, operador, org_a):
    r = cliente.get("/api/v1/roles", headers=org_a.admin)
    nombres = {x["nombre"] for x in r.json()}
    assert {"Administrador de la organización", "Dirección de proyecto", "Equipo operativo", "Consulta y auditoría", "Entidad cliente"} <= nombres
    perfil = cliente.get("/api/v1/organizacion", headers=org_a.admin).json()
    assert perfil["identificacion"] == NIT_A and perfil["estado"] == "activa" and perfil["uso"]["usuarios"] == 1


def test_identificacion_invalida_o_duplicada(cliente, operador, org_a):
    base = {"nombre": "X", "razon_social": "X S.A.S.", "administrador": {"correo": "x@x.example.com", "nombre_completo": "Equis"}}
    r = cliente.post("/api/v1/plataforma/organizaciones", json=base | {"nombre": "Xx", "identificacion": "900123456-1"}, headers=operador)
    assert r.status_code == 422 and "dígito de verificación" in r.json()["detail"]
    r = cliente.post("/api/v1/plataforma/organizaciones", json=base | {"nombre": "Xx", "identificacion": NIT_A}, headers=operador)
    assert r.status_code == 409


def test_solo_el_operador_administra_organizaciones(cliente, org_a):
    assert cliente.get("/api/v1/plataforma/organizaciones", headers=org_a.admin).status_code == 403


def test_operador_no_accede_al_contenido_de_las_organizaciones(cliente, operador, org_a):
    proyecto_basico(cliente, org_a)
    r = cliente.get("/api/v1/proyectos", headers=operador | {"X-Organizacion": org_a.id})
    assert r.status_code == 403


def test_suspender_exige_motivo_y_bloquea_a_los_usuarios(cliente, operador, org_a):
    url = f"/api/v1/plataforma/organizaciones/{org_a.id}"
    assert cliente.post(f"{url}/suspender", json={}, headers=operador).status_code == 422
    assert cliente.post(f"{url}/suspender", json={"motivo": "Mora en el pago del plan"}, headers=operador).status_code == 200
    assert cliente.get("/api/v1/organizacion", headers=org_a.admin).status_code == 403
    assert cliente.post(f"{url}/suspender", json={"motivo": "Otra vez"}, headers=operador).status_code == 422
    assert cliente.post(f"{url}/reactivar", json={"motivo": "Pago recibido"}, headers=operador).status_code == 200
    assert cliente.get("/api/v1/organizacion", headers=org_a.admin).status_code == 200


def test_limites_del_plan(cliente, operador):
    org = crear_org(cliente, operador, "Pequeña", "900123457-5", "admin@peq.example.com", limites={"usuarios": 1, "proyectos": 1})
    proyecto_basico(cliente, org, "P-1")
    r = cliente.post("/api/v1/proyectos", json={"codigo": "P-2", "nombre": "Segundo", "entidad_cliente": "Entidad Ficticia"}, headers=org.admin)
    assert r.status_code == 409 and "límite" in r.json()["detail"]
    roles = cliente.get("/api/v1/roles", headers=org.admin).json()
    r = cliente.post("/api/v1/usuarios", json={"correo": "otro@peq.example.com", "nombre_completo": "Otro", "rol_id": roles[0]["id"]}, headers=org.admin)
    assert r.status_code == 409
    r = cliente.patch(f"/api/v1/plataforma/organizaciones/{org.id}", json={"limites": {"almacenamiento_gb": 5}, "motivo": "Ampliación"}, headers=operador)
    assert r.status_code == 422


def test_editar_organizacion_queda_auditado(cliente, operador, org_a):
    r = cliente.patch(f"/api/v1/plataforma/organizaciones/{org_a.id}", json={"nombre": "Alfa Renombrada", "motivo": "Cambio de marca"}, headers=operador)
    assert r.status_code == 200 and r.json()["nombre"] == "Alfa Renombrada"
    eventos = cliente.get("/api/v1/auditoria/eventos?accion=EDITAR_ORGANIZACION", headers=org_a.admin).json()
    assert eventos[0]["cambios"]["nombre"] == ["Consultora Alfa", "Alfa Renombrada"] and eventos[0]["motivo"] == "Cambio de marca"


def test_administrador_existente_se_reutiliza(cliente, operador, org_a):
    """Una misma persona puede administrar dos organizaciones con una sola cuenta."""
    r = cliente.post(
        "/api/v1/plataforma/organizaciones",
        json={
            "nombre": "Gamma",
            "razon_social": "Gamma S.A.S.",
            "identificacion": "900123458-2",
            "administrador": {"correo": org_a.admin_correo, "nombre_completo": "Admin"},
        },
        headers=operador,
    )
    assert r.status_code == 201 and r.json()["clave_temporal"] is None
    sin_cabecera = ingresar(cliente, org_a.admin_correo)
    assert cliente.get("/api/v1/organizacion", headers=sin_cabecera).status_code == 400
