"""Seguridad de las cuentas (D-46): verificación en dos pasos obligatoria por nivel, correo saliente y recuperación."""

import re

from conftest import CLAVE, agregar_usuario, ingresar, rol_id

from arca.nucleo import correo
from arca.nucleo.config import ajustes


def _politica(cliente, org, nivel):
    return cliente.post("/api/v1/configuracion/parametros", json={"clave": "seguridad.mfa_obligatorio", "valor": nivel, "motivo": "Política de seguridad de la consultora"},
                        headers=org.admin)


def test_mfa_obligatorio_por_nivel(cliente, org_a):
    _, director = agregar_usuario(cliente, org_a, "director@alfa.example.com", "Dirección de proyecto")
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    assert _politica(cliente, org_a, "algunos").status_code == 422
    assert _politica(cliente, org_a, "direccion").status_code == 201
    r = cliente.get("/api/v1/proyectos", headers=director)
    assert r.status_code == 403 and "verificación en dos pasos" in r.text
    assert cliente.get("/api/v1/proyectos", headers=equipo).status_code == 200  # el equipo operativo no está en el nivel «direccion»
    yo = cliente.get("/api/v1/auth/yo", headers=director).json()
    assert yo["organizaciones"][0]["mfa_exigido"] is True and not yo["mfa_activo"]
    assert cliente.post("/api/v1/auth/mfa/iniciar", headers=director).status_code == 200  # puede activarla aunque se le exija
    assert cliente.get("/api/v1/proyectos", headers=org_a.admin).status_code == 403  # la administración también está en «direccion»


def test_mfa_para_todos(cliente, org_a):
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    assert _politica(cliente, org_a, "todos").status_code == 201
    assert cliente.get("/api/v1/proyectos", headers=equipo).status_code == 403


def test_correo_contrasena_temporal_y_recuperacion(cliente, org_a, monkeypatch):
    monkeypatch.setattr(ajustes(), "smtp_host", "memoria")
    correo.BANDEJA.clear()
    r = cliente.post("/api/v1/usuarios", json={"correo": "nueva@alfa.example.com", "nombre_completo": "Persona Nueva", "rol_id": rol_id(cliente, org_a, "Equipo operativo")},
                     headers=org_a.admin).json()
    assert r["clave_temporal"] is None and r["enviada_por_correo"] is True  # ya no se le muestra a quien administra
    mensaje = correo.BANDEJA[-1]
    assert mensaje["para"] == "nueva@alfa.example.com" and "Le crearon una cuenta" in mensaje["asunto"]
    temporal = re.search(r"\n {4}(\S+)\n", mensaje["texto"]).group(1)
    cab = ingresar(cliente, "nueva@alfa.example.com", temporal)
    cliente.post("/api/v1/auth/cambiar-clave", json={"clave_actual": temporal, "clave_nueva": CLAVE}, headers=cab)
    # Recuperación: la respuesta no revela si el correo existe.
    a = cliente.post("/api/v1/auth/recuperar", json={"correo": "nueva@alfa.example.com"}).json()
    b = cliente.post("/api/v1/auth/recuperar", json={"correo": "nadie@alfa.example.com"}).json()
    assert a == b and len(correo.BANDEJA) == 2
    token = re.search(r"token=(\S+)", correo.BANDEJA[-1]["texto"]).group(1)
    cliente.post("/api/v1/auth/recuperar", json={"correo": "nueva@alfa.example.com"})
    assert len(correo.BANDEJA) == 2  # no se reenvía en ráfaga
    assert cliente.post("/api/v1/auth/restablecer", json={"token": token, "clave_nueva": "corta"}).status_code == 422
    assert cliente.post("/api/v1/auth/restablecer", json={"token": token, "clave_nueva": "Otra-clave-segura-2026"}).status_code == 204
    assert cliente.post("/api/v1/auth/restablecer", json={"token": token, "clave_nueva": "Tercera-clave-segura-2026"}).status_code == 422  # un solo uso
    assert cliente.post("/api/v1/auth/ingresar", json={"correo": "nueva@alfa.example.com", "clave": CLAVE}).status_code == 401  # la anterior ya no sirve
    ingresar(cliente, "nueva@alfa.example.com", "Otra-clave-segura-2026")


def test_sin_correo_configurado_se_muestra_la_temporal(cliente, org_a):
    r = cliente.post("/api/v1/usuarios", json={"correo": "otra@alfa.example.com", "nombre_completo": "Persona Otra", "rol_id": rol_id(cliente, org_a, "Equipo operativo")},
                     headers=org_a.admin).json()
    assert r["clave_temporal"] and r["enviada_por_correo"] is False
    assert cliente.post("/api/v1/auth/recuperar", json={"correo": "otra@alfa.example.com"}).status_code == 200  # responde igual, sin enviar
