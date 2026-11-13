"""M03 parámetros con vigencia · M25 auditoría inalterable · M28 estado y correlación."""

import uuid
from datetime import UTC, datetime, timedelta

from conftest import proyecto_basico
from sqlalchemy import select, update

from arca.modelos import EventoAuditoria, Organizacion
from arca.modulos.m03_configuracion.servicios import valor_vigente
from arca.modulos.m25_auditoria import servicios as auditoria


def _publicar(cliente, org, **datos):
    return cliente.post("/api/v1/configuracion/parametros", json={"motivo": "Política aprobada"} | datos, headers=org.admin)


def test_parametro_versionado_y_vigencia_futura(cliente, fabrica, org_a):
    assert _publicar(cliente, org_a, clave="captura.dpi_minimo", valor=200).status_code == 201
    futuro = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    r = _publicar(cliente, org_a, clave="captura.dpi_minimo", valor=300, vigente_desde=futuro)
    assert r.status_code == 201 and r.json()["version"] == 2
    # Hoy rige la versión 1; dentro de diez días, la 2.
    assert [p["valor"] for p in cliente.get("/api/v1/configuracion/parametros", headers=org_a.admin).json()] == [200]
    with fabrica() as db:
        assert valor_vigente(db, uuid.UUID(org_a.id), "captura.dpi_minimo", fecha=datetime.now(UTC) + timedelta(days=11)) == 300
    historial = cliente.get("/api/v1/configuracion/parametros/captura.dpi_minimo/historial", headers=org_a.admin).json()
    assert [h["version"] for h in historial] == [1, 2]


def test_no_se_modifica_lo_ya_ocurrido(cliente, org_a):
    pasado = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    r = _publicar(cliente, org_a, clave="captura.dpi_minimo", valor=150, vigente_desde=pasado)
    assert r.status_code == 422 and "pasada" in r.json()["detail"]


def test_parametro_de_proyecto_prevalece(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    _publicar(cliente, org_a, clave="captura.dpi_minimo", valor=200)
    _publicar(cliente, org_a, clave="captura.dpi_minimo", valor=400, proyecto_id=p["id"])
    general = cliente.get("/api/v1/configuracion/parametros", headers=org_a.admin).json()
    del_proyecto = cliente.get(f"/api/v1/configuracion/parametros?proyecto_id={p['id']}", headers=org_a.admin).json()
    assert general[0]["valor"] == 200 and del_proyecto[0]["valor"] == 400


def test_claves_y_valores_validados(cliente, org_a):
    assert _publicar(cliente, org_a, clave="SinPunto", valor=1).status_code == 422
    assert _publicar(cliente, org_a, clave="seguridad.mfa_privilegiados", valor="si").status_code == 422


def test_cadena_de_auditoria_integra(cliente, org_a):
    proyecto_basico(cliente, org_a)
    r = cliente.get("/api/v1/auditoria/verificar", headers=org_a.admin).json()
    assert r["integra"] is True and r["revisados"] >= 2


def test_alterar_un_evento_se_detecta(cliente, fabrica, org_a):
    proyecto_basico(cliente, org_a)
    with fabrica() as db:
        evento = db.scalar(select(EventoAuditoria).where(EventoAuditoria.accion == "CREAR_PROYECTO"))
        db.execute(update(EventoAuditoria).where(EventoAuditoria.id == evento.id).values(detalle="Detalle maquillado"))
        db.commit()
    r = cliente.get("/api/v1/auditoria/verificar", headers=org_a.admin).json()
    assert r["integra"] is False and "modificado" in r["problema"]


def test_borrar_el_ultimo_evento_se_detecta(cliente, fabrica, org_a):
    proyecto_basico(cliente, org_a)
    with fabrica() as db:
        org = db.get(Organizacion, uuid.UUID(org_a.id))
        ultimo = db.scalar(select(EventoAuditoria).where(EventoAuditoria.tenant_id == org.id).order_by(EventoAuditoria.secuencia.desc()))
        db.delete(ultimo)
        db.commit()
        assert auditoria.verificar_integridad(db, org.id)["integra"] is False


def test_sello_detecta_reescritura_completa(cliente, fabrica, org_a, monkeypatch):
    """Quien recalcula todas las huellas tras alterar un evento no puede rehacer el sello sin la clave."""
    from arca.nucleo import config

    monkeypatch.setattr(config.ajustes(), "sellar_cada_eventos", 1)
    proyecto_basico(cliente, org_a)
    tenant = uuid.UUID(org_a.id)
    with fabrica() as db:
        eventos = list(db.scalars(select(EventoAuditoria).where(EventoAuditoria.tenant_id == tenant).order_by(EventoAuditoria.secuencia)))
        eventos[-1].detalle = "Reescrito"
        anterior = eventos[-1].hash_anterior
        eventos[-1].hash_evento = auditoria.huella_evento(eventos[-1])
        assert eventos[-1].hash_anterior == anterior
        db.commit()
        r = auditoria.verificar_integridad(db, tenant)
    assert r["integra"] is False and "sello" in r["problema"]


def test_correlacion_viaja_a_la_auditoria(cliente, org_a):
    r = cliente.post(
        "/api/v1/proyectos",
        json={"codigo": "P-9", "nombre": "Proyecto de prueba", "entidad_cliente": "Entidad Ficticia"},
        headers=org_a.admin | {"X-Correlation-ID": "prueba-correlacion-001"},
    )
    assert r.headers["X-Correlation-ID"] == "prueba-correlacion-001"
    eventos = cliente.get("/api/v1/auditoria/eventos?correlacion_id=prueba-correlacion-001", headers=org_a.admin).json()
    assert [e["accion"] for e in eventos] == ["CREAR_PROYECTO"]


def test_estado_del_servicio(cliente):
    r = cliente.get("/estado")
    assert r.status_code == 200 and r.json()["base_de_datos"] == "disponible" and "X-Correlation-ID" in r.headers
