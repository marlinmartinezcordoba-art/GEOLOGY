"""Transferencias documentales primaria y secundaria, recepción por unidad y fase de partida. Datos ficticios."""

import io

import openpyxl
from conftest import agregar_usuario
from test_m04_clasificacion import FILAS, _escenario, _filas, _trd

RECIENTE = [7, "CP-7", "100-05", "Decretos recientes", "2025-01-01", "2025-12-31", "C-4", "1", "", "", 12, "Papel", ""]


def _listo(cliente, org, filas=FILAS + [RECIENTE]):
    """Proyecto con FUID, TRD vigente y todo lo proponible clasificado y confirmado (CP-5 queda sin clasificar)."""
    p, url, director, cla = _escenario(cliente, org, filas)
    _trd(cliente, org, director, url)
    cliente.post(f"{cla}/proponer", headers=org.admin)
    propuestas = [f["clasificacion"]["id"] for f in _filas(cliente, org.admin, cla, situacion="propuesta").values()]
    if propuestas:
        cliente.post(f"{cla}/confirmar", json={"clasificaciones": propuestas}, headers=org.admin)
    ids = {k: f["unidad"]["id"] for k, f in _filas(cliente, org.admin, cla).items()}
    return p, director, f"/api/v1/proyectos/{p['id']}/transferencias", ids


def _crear(cliente, cab, tr, tipo="primaria", **extra):
    r = cliente.post(tr, json={"tipo": tipo} | extra, headers=cab)
    assert r.status_code == 201, r.text
    return r.json()


def _unidades(cliente, cab, tr, t):
    return {u["identificador"]: u for u in cliente.get(f"{tr}/{t['id']}", headers=cab).json()["unidades"]}


def test_plan_y_transferencia_primaria(cliente, org_a):
    p, director, tr, ids = _listo(cliente, org_a)
    plan = cliente.get(f"{tr}/plan", headers=org_a.admin).json()
    assert plan["fases"] == {"gestion": 7, "central": 0, "historico": 0, "eliminada": 0} and plan["sin_clasificar"] == 1
    primaria = plan["tipos"]["primaria"]
    assert (primaria["elegibles"], primaria["anticipables"]) == (5, 1)
    assert {d["codigo"]: d["elegibles"] for d in primaria["por_dependencia"]} == {"100": 3, "110": 2}
    t = _crear(cliente, org_a.admin, tr)
    assert t["numero"] == 1 and t["estado"] == "borrador" and t["resumen"]["unidades"] == 5
    # Una unidad no va en dos transferencias abiertas; lo no clasificado no se transfiere; lo anticipado va con aviso.
    otra = _crear(cliente, org_a.admin, tr)
    assert otra["resumen"]["unidades"] == 0
    r = cliente.post(f"{tr}/{otra['id']}/agregar", json={"unidades": [ids["CP-1"]]}, headers=org_a.admin).json()
    assert r["agregadas"] == 0 and "transferencia n.º 1" in r["rechazadas"][0]
    assert cliente.post(f"{tr}/{otra['id']}/anular", json={"motivo": "Creada por error"}, headers=org_a.admin).json()["estado"] == "anulada"
    r = cliente.post(f"{tr}/{t['id']}/agregar", json={"unidades": [ids["CP-7"], ids["CP-5"]]}, headers=org_a.admin).json()
    assert r["agregadas"] == 1 and "no está clasificada" in r["rechazadas"][0]
    u = _unidades(cliente, org_a.admin, tr, t)
    assert not u["CP-7"]["elegible"] and "anticipada" in u["CP-7"]["aviso"]
    candidatas = cliente.get(f"{tr}/{t['id']}/candidatas", headers=org_a.admin).json()
    assert candidatas == []  # todo lo que podía ir ya va
    # Enviar; quien envía no recibe; se recibe unidad por unidad.
    assert cliente.post(f"{tr}/{t['id']}/enviar", headers=org_a.admin).json()["estado"] == "enviada"
    assert cliente.post(f"{tr}/{t['id']}/agregar", json={"unidades": [ids["CP-7"]]}, headers=org_a.admin).status_code == 422
    assert cliente.post(f"{tr}/{t['id']}/recibir", json={}, headers=org_a.admin).status_code == 403
    devuelta = [{"unidad_id": ids["CP-4"], "observacion": "Faltan folios 3 a 5"}]
    r = cliente.post(f"{tr}/{t['id']}/recibir", json={"devueltas": devuelta, "motivo": "Recibida con una novedad"}, headers=director)
    assert r.json() == {"recibidas": 5, "devueltas": 1}, r.text
    u = _unidades(cliente, org_a.admin, tr, t)
    assert u["CP-1"]["fase"] == "central" and u["CP-1"]["estado"] == "recibida"
    assert u["CP-4"]["fase"] == "gestion" and u["CP-4"]["observacion"] == "Faltan folios 3 a 5"
    historial = cliente.get(f"{tr}/unidades/{ids['CP-1']}/historial", headers=org_a.admin).json()
    assert [(h["desde"], h["hasta"]) for h in historial] == [("Archivo de gestión", "Archivo central")]
    # Lo devuelto queda libre para otra transferencia.
    assert _crear(cliente, org_a.admin, tr)["resumen"]["unidades"] == 1


def test_transferencia_secundaria_solo_conservacion_y_seleccion(cliente, org_a):
    p, director, tr, ids = _listo(cliente, org_a)
    t = _crear(cliente, org_a.admin, tr)
    cliente.post(f"{tr}/{t['id']}/enviar", headers=org_a.admin)
    cliente.post(f"{tr}/{t['id']}/recibir", json={}, headers=director)
    plan = cliente.get(f"{tr}/plan", headers=org_a.admin).json()
    assert plan["fases"]["central"] == 5 and plan["tipos"]["secundaria"]["elegibles"] == 3
    s = _crear(cliente, org_a.admin, tr, "secundaria")
    u = _unidades(cliente, org_a.admin, tr, s)
    assert set(u) == {"CP-1", "CP-2", "CP-6"}  # CP-3 y CP-4 (110-05.01, selección) esperan el muestreo
    r = cliente.post(f"{tr}/{s['id']}/agregar", json={"unidades": [ids["CP-3"]]}, headers=org_a.admin).json()
    assert "selección pendiente" in r["rechazadas"][0]
    cliente.post(f"{tr}/{s['id']}/enviar", headers=org_a.admin)
    assert cliente.post(f"{tr}/{s['id']}/recibir", json={}, headers=director).json()["recibidas"] == 3
    fases = cliente.get(f"{tr}/plan", headers=org_a.admin).json()["fases"]
    assert (fases["gestion"], fases["central"], fases["historico"]) == (2, 2, 3)


def test_eliminacion_no_va_al_historico(cliente, org_a):
    filas = [[1, "CP-1", "200-01", "Inventarios de entrega", "1990-01-01", "1990-12-31", "C-1", "1", "", "", 10, "Papel", ""]]
    p, url, director, cla = _escenario(cliente, org_a, filas)
    trd = [["200", "Gestión documental", "200-01", "Inventarios", "", "", "FUID", 2, 8, "", "X", "", "", "F", "Eliminación por picado"]]
    from test_m04_instrumentos import ENCABEZADO
    from test_m04_instrumentos import _libro as libro

    inst = cliente.post(url, json={"tipo": "TRD", "nombre": "TRD con eliminación"}, headers=org_a.admin).json()
    v = cliente.post(f"{url}/{inst['id']}/versiones", files={"archivo": ("t.xlsx", libro(trd, ENCABEZADO + ["Procedimiento"]))}, data={"motivo": "Entrega ficticia"}, headers=org_a.admin).json()
    cliente.post(f"{url}/{inst['id']}/versiones/{v['id']}/aprobar", json={"acto_administrativo": "Resolución ficticia", "fecha_acto": "2026-01-01", "motivo": "Aprobada"}, headers=director)
    cliente.post(f"{cla}/proponer", headers=org_a.admin)
    tr = f"/api/v1/proyectos/{p['id']}/transferencias"
    unidad = next(iter(_filas(cliente, org_a.admin, cla).values()))["unidad"]["id"]
    cliente.post(f"{tr}/fase-de-partida", json={"unidades": [unidad], "fase": "central", "motivo": "El fondo ya está en el archivo central"}, headers=org_a.admin)
    s = _crear(cliente, org_a.admin, tr, "secundaria")
    assert s["resumen"]["unidades"] == 0
    r = cliente.post(f"{tr}/{s['id']}/agregar", json={"unidades": [unidad]}, headers=org_a.admin).json()
    assert "no va al archivo histórico" in r["rechazadas"][0]


def test_devolver_corregir_y_reenviar(cliente, org_a):
    p, director, tr, ids = _listo(cliente, org_a)
    t = _crear(cliente, org_a.admin, tr, codigo_dependencia="110")
    assert t["dependencia"] == "Oficina jurídica" and t["resumen"]["unidades"] == 2
    r = cliente.post(f"{tr}/{t['id']}/agregar", json={"unidades": [ids["CP-1"]]}, headers=org_a.admin).json()
    assert "dependencia 100" in r["rechazadas"][0]
    cliente.post(f"{tr}/{t['id']}/enviar", headers=org_a.admin)
    assert cliente.post(f"{tr}/{t['id']}/devolver", json={"motivo": "Cajas sin rotular"}, headers=director).json()["estado"] == "devuelta"
    assert cliente.post(f"{tr}/{t['id']}/quitar", json={"unidades": [ids["CP-4"]]}, headers=org_a.admin).json() == {"quitadas": 1}
    assert cliente.post(f"{tr}/{t['id']}/enviar", headers=org_a.admin).json()["resumen"]["unidades"] == 1
    assert cliente.post(f"{tr}/{t['id']}/recibir", json={}, headers=director).json() == {"recibidas": 1, "devueltas": 0}
    assert cliente.post(f"{tr}/{t['id']}/anular", json={"motivo": "Ya no aplica"}, headers=org_a.admin).status_code == 422


def test_inventario_de_la_transferencia_en_el_fuid_de_la_entidad(cliente, org_a):
    p, director, tr, ids = _listo(cliente, org_a)
    libro = openpyxl.Workbook()
    h = libro.active
    h["A1"] = "{{objeto}} n.º {{numero_transferencia}} · {{oficina_productora}} · corte {{fecha_corte}}"
    h.append(["Identificador", "Clasificación", "Serie", "Subserie", "Folios"])
    h.append(["{{fila.identificador}}", "{{fila.codigo_clasificacion}}", "{{fila.serie}}", "{{fila.subserie}}", "{{fila.folios}}"])
    salida = io.BytesIO()
    libro.save(salida)
    pl = cliente.post("/api/v1/plantillas", json={"tipo": "fuid", "nombre": "FUID de transferencias"}, headers=org_a.admin).json()
    r = cliente.post(f"/api/v1/plantillas/{pl['id']}/versiones", files={"archivo": ("f.xlsx", salida.getvalue())}, data={"motivo": "Formato de la entidad"}, headers=org_a.admin)
    assert r.status_code == 201, r.text
    t = _crear(cliente, org_a.admin, tr, codigo_dependencia="100")
    e = cliente.post(f"{tr}/{t['id']}/inventario", headers=org_a.admin)
    assert e.status_code == 201 and e.json()["elementos"] == 3
    hoja = openpyxl.load_workbook(io.BytesIO(cliente.get(f"/api/v1/proyectos/{p['id']}/entregables/{e.json()['expedicion_id']}/archivo", headers=org_a.admin).content)).active
    assert hoja["A1"].value.startswith("Transferencia primaria n.º 1 · Dirección general · corte")
    filas = {hoja.cell(r, 1).value: [hoja.cell(r, c).value for c in (2, 3, 4)] for r in range(3, 6)}
    assert filas["CP-1"] == ["100-02.01", "Actas", "Actas de comité directivo"]
    assert filas["CP-2"] == ["100-05", "Decretos", None]
    historial = cliente.get(f"/api/v1/proyectos/{p['id']}/entregables", headers=org_a.admin).json()
    assert historial[0]["filtro"]["transferencia"] == 1


def test_fase_de_partida_permisos_y_aislamiento(cliente, org_a, org_b):
    p, director, tr, ids = _listo(cliente, org_a)
    r = cliente.post(f"{tr}/fase-de-partida", json={"unidades": [ids["CP-5"]], "fase": "historico", "motivo": "Fondo histórico recibido"}, headers=org_a.admin)
    assert r.json() == {"registradas": 1}
    assert cliente.post(f"{tr}/fase-de-partida", json={"unidades": [ids["CP-5"]], "fase": "central", "motivo": "Otra vez"}, headers=org_a.admin).status_code == 422
    r = cliente.post(f"{tr}/fase-de-partida", json={"cajas": ["c-4"], "fase": "central", "motivo": "La caja ya está en el archivo central"}, headers=org_a.admin)
    assert r.json() == {"registradas": 1}  # CP-7, por su caja
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo", [p["id"]])
    assert cliente.get(f"{tr}/plan", headers=consulta).status_code == 200
    assert cliente.post(tr, json={"tipo": "primaria"}, headers=consulta).status_code == 403
    t = _crear(cliente, equipo, tr)
    cliente.post(f"{tr}/{t['id']}/enviar", headers=equipo)
    assert cliente.post(f"{tr}/{t['id']}/recibir", json={}, headers=equipo).status_code == 403  # recibir es otro permiso
    assert cliente.get(tr, headers=org_b.admin).status_code == 404
    assert cliente.post(tr, json={"tipo": "terciaria"}, headers=org_a.admin).status_code == 422
