"""M02 · Ingreso, bloqueo, verificación en dos pasos, permisos por rol, revocación y segregación de funciones."""

import time

from conftest import CLAVE, agregar_usuario, ingresar, proyecto_basico, rol_id

from arca.nucleo.seguridad import codigo_totp


def test_ingreso_no_revela_si_el_correo_existe(cliente, org_a):
    r1 = cliente.post("/api/v1/auth/ingresar", json={"correo": "nadie@alfa.example.com", "clave": "x"})
    r2 = cliente.post("/api/v1/auth/ingresar", json={"correo": org_a.admin_correo, "clave": "incorrecta"})
    assert r1.status_code == r2.status_code == 401 and r1.json()["detail"] == r2.json()["detail"]


def test_bloqueo_por_intentos_fallidos(cliente, org_a):
    for _ in range(5):
        cliente.post("/api/v1/auth/ingresar", json={"correo": org_a.admin_correo, "clave": "incorrecta"})
    r = cliente.post("/api/v1/auth/ingresar", json={"correo": org_a.admin_correo, "clave": CLAVE})
    assert r.status_code == 401 and "bloqueada" in r.json()["detail"]
    assert cliente.get("/api/v1/organizacion", headers=org_a.admin).status_code == 401


def test_clave_temporal_obliga_a_cambiarla(cliente, org_a):
    r = cliente.post(
        "/api/v1/usuarios",
        json={"correo": "nuevo@alfa.example.com", "nombre_completo": "Persona Nueva", "rol_id": rol_id(cliente, org_a, "Equipo operativo")},
        headers=org_a.admin,
    )
    temporal = r.json()["clave_temporal"]
    cab = ingresar(cliente, "nuevo@alfa.example.com", temporal) | {"X-Organizacion": org_a.id}
    assert cliente.get("/api/v1/proyectos", headers=cab).status_code == 403
    r = cliente.post("/api/v1/auth/cambiar-clave", json={"clave_actual": temporal, "clave_nueva": "corta"}, headers=cab)
    assert r.status_code == 422


def test_denegar_por_defecto_segun_rol(cliente, org_a):
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    assert cliente.get("/api/v1/proyectos", headers=equipo).status_code == 200
    assert (
        cliente.post("/api/v1/proyectos", json={"codigo": "X-1", "nombre": "No permitido", "entidad_cliente": "Entidad Ficticia"}, headers=equipo).status_code
        == 403
    )
    assert cliente.get("/api/v1/usuarios", headers=equipo).status_code == 403
    assert cliente.get("/api/v1/auditoria/eventos", headers=equipo).status_code == 403
    assert cliente.post("/api/v1/configuracion/parametros", json={"clave": "a.b", "valor": 1, "motivo": "Prueba"}, headers=equipo).status_code == 403
    _, consulta = agregar_usuario(cliente, org_a, "auditor@alfa.example.com", "Consulta y auditoría")
    assert cliente.get("/api/v1/auditoria/eventos", headers=consulta).status_code == 200
    assert (
        cliente.post("/api/v1/proyectos", json={"codigo": "X-2", "nombre": "No permitido", "entidad_cliente": "Entidad Ficticia"}, headers=consulta).status_code
        == 403
    )


def test_revocar_sesiones_invalida_el_token(cliente, org_a):
    usuario, cab = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    assert cliente.get("/api/v1/proyectos", headers=cab).status_code == 200
    assert cliente.post(f"/api/v1/usuarios/{usuario}/revocar-sesiones", json={"motivo": "Equipo extraviado"}, headers=org_a.admin).status_code == 204
    assert cliente.get("/api/v1/proyectos", headers=cab).status_code == 401


def test_desactivar_membresia_quita_el_acceso(cliente, org_a):
    usuario, cab = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    assert cliente.post(f"/api/v1/usuarios/{usuario}/desactivar", json={"motivo": "Terminó su contrato"}, headers=org_a.admin).status_code == 200
    assert cliente.get("/api/v1/proyectos", headers=cab).status_code == 403


def test_segregacion_de_funciones(cliente, org_a):
    yo = cliente.get("/api/v1/auth/yo", headers=org_a.admin).json()["id"]
    r = cliente.patch(f"/api/v1/usuarios/{yo}", json={"rol_id": rol_id(cliente, org_a, "Equipo operativo"), "motivo": "Autocambio"}, headers=org_a.admin)
    assert r.status_code == 403
    assert cliente.post(f"/api/v1/usuarios/{yo}/desactivar", json={"motivo": "Autocambio"}, headers=org_a.admin).status_code == 403
    r = cliente.patch(
        f"/api/v1/roles/{rol_id(cliente, org_a, 'Administrador de la organización')}", json={"permisos": [], "motivo": "Editar base"}, headers=org_a.admin
    )
    assert r.status_code == 409


def test_la_organizacion_no_se_queda_sin_administrador(cliente, org_a):
    otro, cab_otro = agregar_usuario(cliente, org_a, "admin2@alfa.example.com", "Administrador de la organización")
    yo = cliente.get("/api/v1/auth/yo", headers=org_a.admin).json()["id"]
    assert cliente.post(f"/api/v1/usuarios/{yo}/desactivar", json={"motivo": "Rotación del cargo"}, headers=cab_otro).status_code == 200
    equipo = next(x["id"] for x in cliente.get("/api/v1/roles", headers=cab_otro).json() if x["nombre"] == "Equipo operativo")
    r = cliente.patch(f"/api/v1/usuarios/{otro}", json={"rol_id": equipo, "motivo": "Quitarse"}, headers=cab_otro)
    assert r.status_code == 403  # tampoco puede degradarse a sí mismo


def test_rol_propio_con_permisos_validados(cliente, org_a):
    r = cliente.post("/api/v1/roles", json={"nombre": "Coordinación QA", "permisos": ["proyectos:leer", "inventado:hacer"]}, headers=org_a.admin)
    assert r.status_code == 422
    r = cliente.post("/api/v1/roles", json={"nombre": "Coordinación QA", "permisos": ["proyectos:leer", "auditoria:leer"]}, headers=org_a.admin)
    assert r.status_code == 201
    rol = r.json()["id"]
    r = cliente.patch(f"/api/v1/roles/{rol}", json={"permisos": ["proyectos:leer"], "motivo": "Ajuste de matriz"}, headers=org_a.admin)
    assert r.status_code == 200 and r.json()["permisos"] == ["proyectos:leer"]


def test_verificacion_en_dos_pasos(cliente, org_a):
    secreto = cliente.post("/api/v1/auth/mfa/iniciar", headers=org_a.admin).json()["secreto"]
    assert (
        cliente.post("/api/v1/auth/mfa/confirmar", json={"codigo": "000000" if codigo_totp(secreto) != "000000" else "111111"}, headers=org_a.admin).status_code
        == 422
    )
    assert cliente.post("/api/v1/auth/mfa/confirmar", json={"codigo": codigo_totp(secreto)}, headers=org_a.admin).status_code == 204
    assert cliente.get("/api/v1/organizacion", headers=org_a.admin).status_code == 401  # se cerraron las sesiones
    r = cliente.post("/api/v1/auth/ingresar", json={"correo": org_a.admin_correo, "clave": CLAVE})
    assert r.status_code == 401 and r.headers.get("X-ARCA-MFA") == "requerido"
    cab = ingresar(cliente, org_a.admin_correo, codigo=codigo_totp(secreto, time.time()))
    assert cliente.get("/api/v1/organizacion", headers=cab | {"X-Organizacion": org_a.id}).status_code == 200


def test_politica_mfa_para_roles_privilegiados(cliente, org_a):
    _, director = agregar_usuario(cliente, org_a, "director@alfa.example.com", "Dirección de proyecto")
    r = cliente.post(
        "/api/v1/configuracion/parametros", json={"clave": "seguridad.mfa_privilegiados", "valor": True, "motivo": "Política ISO 27001"}, headers=org_a.admin
    )
    assert r.status_code == 201
    # El administrador (privilegiado y sin MFA) queda detenido; la dirección de proyecto no es privilegiada.
    assert cliente.get("/api/v1/organizacion", headers=org_a.admin).status_code == 403
    assert cliente.get("/api/v1/proyectos", headers=director).status_code == 200


def test_alcance_limitado_al_asignar_equipo(cliente, org_a):
    p1 = proyecto_basico(cliente, org_a, "A-001")
    p2 = proyecto_basico(cliente, org_a, "A-002")
    usuario, _ = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo", proyectos=[p1["id"]])
    assert cliente.post(f"/api/v1/proyectos/{p2['id']}/equipo", json={"usuario_id": usuario}, headers=org_a.admin).status_code == 409
    assert (
        cliente.post(f"/api/v1/proyectos/{p1['id']}/equipo", json={"usuario_id": usuario, "funcion": "Hoja de control"}, headers=org_a.admin).status_code == 201
    )


def test_directorio_para_quien_dirige_proyectos(cliente, org_a):
    _, director = agregar_usuario(cliente, org_a, "director@alfa.example.com", "Dirección de proyecto")
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    correos = {p["correo"] for p in cliente.get("/api/v1/usuarios/directorio", headers=director).json()}
    assert {"director@alfa.example.com", "equipo@alfa.example.com", org_a.admin_correo} <= correos
    assert cliente.get("/api/v1/usuarios/directorio", headers=equipo).status_code == 403
