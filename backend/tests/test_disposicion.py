"""Disposición final: eliminación (comité, publicación, acta), selección por muestreo y digitalización. Datos ficticios."""

import io
from datetime import date, timedelta

import openpyxl
from conftest import agregar_usuario, proyecto_basico
from fabricas import fuid_xlsx, pdf_escaneado
from test_m04_instrumentos import ENCABEZADO, _libro

TRD = [
    ["200", "Gestión documental", "200-01", "Inventarios", "", "", "FUID", 2, 3, "", "X", "", "", "F", "Eliminación por picado"],
    ["200", "Gestión documental", "200-02", "Consecutivos de comunicaciones", "", "", "Oficio", 2, 8, "", "", "X", "", "F", "Selección del 20 % por muestreo"],
    ["200", "Gestión documental", "200-03", "Historias de proveedores", "", "", "Contrato", 2, 8, "", "", "", "X", "F", "Digitalizar y eliminar el físico"],
    ["200", "Gestión documental", "200-04", "Actas", "", "", "Acta", 2, 18, "X", "", "", "", "F", "Conservación total"],
]


def _fila(n, ident, codigo, nombre, anio=1990, caja="C-1"):
    return [n, ident, codigo, nombre, f"{anio}-01-01", f"{anio}-12-31", caja, str(n), "", "", 10, "Papel", ""]


FILAS = (
    [_fila(i, f"CP-0010{i}", "200-01", f"Inventario ficticio {i}") for i in (1, 2, 3)]
    + [_fila(4, "CP-00104", "200-01", "Inventario reciente", 2025)]
    + [_fila(10 + i, f"CP-002{i:02d}", "200-02", f"Consecutivo ficticio {i}", caja="C-2") for i in range(1, 11)]
    + [_fila(30 + i, f"CP-0030{i}", "200-03", f"Historia de proveedor {i}", caja="C-3") for i in (1, 2)]
    + [_fila(41, "CP-00401", "200-04", "Actas ficticias")]
)


def _proyecto(cliente, org):
    p = proyecto_basico(cliente, org)
    base = f"/api/v1/proyectos/{p['id']}"
    lote = cliente.post(f"{base}/inventario/lotes", files={"archivo": ("fuid.xlsx", fuid_xlsx(FILAS))}, headers=org.admin).json()
    cliente.post(f"{base}/inventario/lotes/{lote['id']}/integrar", json={}, headers=org.admin)
    _, director = agregar_usuario(cliente, org, "director@alfa.example.com", "Dirección de proyecto")
    inst = cliente.post(f"{base}/instrumentos", json={"tipo": "TRD", "nombre": "TRD ficticia"}, headers=org.admin).json()
    v = cliente.post(f"{base}/instrumentos/{inst['id']}/versiones", files={"archivo": ("t.xlsx", _libro(TRD, ENCABEZADO + ["Procedimiento"]))},
                     data={"motivo": "Entrega ficticia"}, headers=org.admin).json()
    assert v["errores"] == [], v["errores"]
    cliente.post(f"{base}/instrumentos/{inst['id']}/versiones/{v['id']}/aprobar", json={"acto_administrativo": "Resolución ficticia", "fecha_acto": "2026-01-01", "motivo": "Aprobada"}, headers=director)
    assert cliente.post(f"{base}/clasificacion/proponer", headers=org.admin).json()["confirmadas"] == len(FILAS)
    filas = cliente.get(f"{base}/clasificacion", params={"limite": 500}, headers=org.admin).json()["filas"]
    ids = {f["unidad"]["identificador"]: f["unidad"]["id"] for f in filas}
    return p, base, director, f"{base}/disposicion", ids


def _crear(cliente, cab, url, tipo, **extra):
    r = cliente.post(url, json={"tipo": tipo} | extra, headers=cab)
    assert r.status_code == 201, r.text
    return r.json()


def _aprobar(cliente, cab, url, proceso):
    return cliente.post(f"{url}/{proceso['id']}/aprobar", json={"acta_comite": "Acta 05 del comité (ficticia)", "fecha_acta": date.today().isoformat(), "motivo": "Aprobada en sesión"}, headers=cab)


def _unidades(cliente, cab, url, proceso):
    return {u["identificador"]: u for u in cliente.get(f"{url}/{proceso['id']}", headers=cab).json()["unidades"]}


def test_plan_por_disposicion(cliente, org_a):
    _, _, _, url, _ = _proyecto(cliente, org_a)
    plan = cliente.get(f"{url}/plan", headers=org_a.admin).json()["tipos"]
    assert (plan["eliminacion"]["elegibles"], plan["eliminacion"]["por_cumplir"]) == (3, 1)
    assert plan["seleccion"]["elegibles"] == 10 and plan["digitalizacion"]["elegibles"] == 2
    assert plan["eliminacion"]["por_serie"][0]["procedimiento"] == "Eliminación por picado"


def test_eliminacion_con_comite_publicacion_y_acta(cliente, org_a):
    p, base, director, url, ids = _proyecto(cliente, org_a)
    e = _crear(cliente, org_a.admin, url, "eliminacion")
    assert e["resumen"]["unidades"] == 3 and e["estado"] == "borrador"
    assert cliente.post(url, json={"tipo": "eliminacion"}, headers=org_a.admin).status_code == 422  # ya van en el proceso n.º 1
    # Lo que va a eliminarse no se puede transferir.
    t = cliente.post(f"{base}/transferencias", json={"tipo": "primaria"}, headers=org_a.admin).json()
    assert cliente.post(f"{base}/transferencias/{t['id']}/agregar", json={"unidades": [ids["CP-00101"]]}, headers=org_a.admin).json()["rechazadas"][0].endswith("proceso de disposición n.º 1")
    cliente.post(f"{base}/transferencias/{t['id']}/anular", json={"motivo": "Solo era una prueba"}, headers=org_a.admin)
    # Comité: lo registra otra persona; nada se ejecuta sin publicar.
    assert _aprobar(cliente, org_a.admin, url, e).status_code == 403
    assert _aprobar(cliente, director, url, e).json()["estado"] == "aprobado"
    assert cliente.post(f"{url}/{e['id']}/ejecutar", json={"acta_numero": "AE-1", "metodo": "Picado"}, headers=org_a.admin).status_code == 422
    futura = {"inicio": (date.today() + timedelta(days=1)).isoformat(), "dias": 60, "enlace": "https://entidad.example.com/eliminacion"}
    assert cliente.post(f"{url}/{e['id']}/publicar", json=futura, headers=org_a.admin).status_code == 422
    hoy = {"inicio": date.today().isoformat(), "dias": 60, "enlace": "https://entidad.example.com/eliminacion"}
    r = cliente.post(f"{url}/{e['id']}/publicar", json=hoy, headers=org_a.admin).json()
    assert r["estado"] == "publicado" and r["publicacion_fin"] == (date.today() + timedelta(days=60)).isoformat()
    r = cliente.post(f"{url}/{e['id']}/ejecutar", json={"acta_numero": "AE-1", "metodo": "Picado"}, headers=org_a.admin)
    assert r.status_code == 422 and "observaciones" in r.json()["detail"]  # el plazo sigue corriendo
    # Durante la publicación llega una observación: la unidad se retira con motivo.
    assert cliente.post(f"{url}/{e['id']}/retirar", json={"unidades": [ids["CP-00102"]], "motivo": "Observación ciudadana: se conserva"}, headers=org_a.admin).json() == {"retiradas": 1}


def test_ejecutar_la_eliminacion_y_expedir_el_acta(cliente, org_a):
    p, base, director, url, ids = _proyecto(cliente, org_a)
    e = _crear(cliente, org_a.admin, url, "eliminacion")
    _aprobar(cliente, director, url, e)
    pasada = {"inicio": (date.today() - timedelta(days=61)).isoformat(), "dias": 60, "enlace": "https://entidad.example.com/eliminacion"}
    cliente.post(f"{url}/{e['id']}/publicar", json=pasada, headers=org_a.admin)
    assert cliente.post(f"{url}/{e['id']}/ejecutar", json={}, headers=org_a.admin).status_code == 422  # sin acta ni método
    r = cliente.post(f"{url}/{e['id']}/ejecutar", json={"acta_numero": "AE-2026-01", "metodo": "Picado y reciclaje"}, headers=org_a.admin)
    assert r.json() == {"ejecutadas": 3, "nuevo_proceso": None}, r.text
    u = _unidades(cliente, org_a.admin, url, e)
    assert all(x["fase"] == "eliminada" and x["estado"] == "ejecutada" for x in u.values())
    historial = cliente.get(f"{base}/transferencias/unidades/{ids['CP-00101']}/historial", headers=org_a.admin).json()
    assert historial[-1]["hasta"] == "Eliminada" and "AE-2026-01" in historial[-1]["motivo"]
    assert cliente.get(f"{url}/plan", headers=org_a.admin).json()["eliminadas"] == 3
    # El acta sale sobre la plantilla de la entidad; sin plantilla vigente se dice.
    assert cliente.post(f"{url}/{e['id']}/documentos/acta", headers=org_a.admin).status_code == 422
    pl = cliente.post("/api/v1/plantillas", json={"tipo": "acta_eliminacion", "nombre": "Acta de la entidad"}, headers=org_a.admin).json()
    base_acta = cliente.get("/api/v1/plantillas/tipos/acta_eliminacion/base", headers=org_a.admin).content
    assert cliente.post(f"/api/v1/plantillas/{pl['id']}/versiones", files={"archivo": ("a.xlsx", base_acta)}, data={"motivo": "Formato de la entidad"}, headers=org_a.admin).status_code == 201
    d = cliente.post(f"{url}/{e['id']}/documentos/acta", headers=org_a.admin)
    assert d.status_code == 201 and d.json()["elementos"] == 3
    hoja = openpyxl.load_workbook(io.BytesIO(cliente.get(f"{base}/entregables/{d.json()['expedicion_id']}/archivo", headers=org_a.admin).content)).active
    textos = [str(c.value) for f in hoja.iter_rows() for c in f if c.value is not None]
    assert "AE-2026-01" in textos and "Acta 05 del comité (ficticia)" in textos and "Picado y reciclaje" in textos
    assert any("200-01 Inventarios" in t for t in textos) and any("Total de unidades: 3" in t for t in textos)
    assert "200 Gestión documental" in textos
    # El acta no se expide por la ruta general de entregables.
    assert cliente.post(f"{base}/entregables", json={"tipo": "acta_eliminacion"}, headers=org_a.admin).status_code == 422
    assert cliente.post(f"{url}/{e['id']}/anular", json={"motivo": "Ya no aplica"}, headers=org_a.admin).status_code == 422


def test_seleccion_por_muestreo_y_eliminacion_del_resto(cliente, org_a):
    p, base, director, url, ids = _proyecto(cliente, org_a)
    cliente.post(f"{base}/transferencias/fase-de-partida", json={"cajas": ["C-2"], "fase": "central", "motivo": "Las cajas ya están en el central"}, headers=org_a.admin)
    s = _crear(cliente, org_a.admin, url, "seleccion")
    assert s["resumen"]["unidades"] == 10
    assert _aprobar(cliente, director, url, s).status_code == 422  # primero el muestreo
    m1 = cliente.post(f"{url}/{s['id']}/muestrear", json={"porcentaje": 20, "semilla": 42, "criterio": "Aleatorio"}, headers=org_a.admin).json()
    sel1 = {k for k, u in _unidades(cliente, org_a.admin, url, s).items() if u["estado"] == "seleccionada"}
    cliente.post(f"{url}/{s['id']}/muestrear", json={"porcentaje": 20, "semilla": 42}, headers=org_a.admin)
    sel2 = {k for k, u in _unidades(cliente, org_a.admin, url, s).items() if u["estado"] == "seleccionada"}
    assert m1["propuestas"] == 2 and m1["semilla"] == 42 and sel1 == sel2  # la misma semilla da la misma muestra
    otra = next(k for k in ids if k.startswith("CP-002") and k not in sel1)
    assert cliente.post(f"{url}/{s['id']}/marcar", json={"unidades": [ids[otra]], "seleccionada": True}, headers=org_a.admin).json() == {"marcadas": 1}
    assert _aprobar(cliente, director, url, s).status_code == 200
    r = cliente.post(f"{url}/{s['id']}/ejecutar", json={}, headers=org_a.admin).json()
    assert r["ejecutadas"] == 10 and r["nuevo_proceso"]["unidades"] == 7
    nuevo = next(x for x in cliente.get(url, headers=org_a.admin).json() if x["id"] == r["nuevo_proceso"]["id"])
    assert nuevo["tipo"] == "eliminacion" and nuevo["estado"] == "borrador" and nuevo["origen_id"] == s["id"]
    # Solo lo seleccionado va al histórico.
    t = cliente.post(f"{base}/transferencias", json={"tipo": "secundaria"}, headers=org_a.admin).json()
    en_t = {u["identificador"] for u in cliente.get(f"{base}/transferencias/{t['id']}", headers=org_a.admin).json()["unidades"]}
    assert en_t == sel1 | {otra}


def test_digitalizacion_exige_lo_digitalizado_y_decide_el_fisico(cliente, org_a):
    p, base, director, url, ids = _proyecto(cliente, org_a)
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("CP-00301.pdf", pdf_escaneado(2)))], data={"rutas_relativas": ["CP-00301.pdf"]}, headers=org_a.admin)
    d = _crear(cliente, org_a.admin, url, "digitalizacion")
    u = _unidades(cliente, org_a.admin, url, d)
    assert u["CP-00301"]["aviso"] == "" and "no tiene imágenes" in u["CP-00302"]["aviso"]
    r = _aprobar(cliente, director, url, d)
    assert r.status_code == 422 and "digitalización completa" in r.json()["detail"]
    cliente.post(f"{url}/{d['id']}/retirar", json={"unidades": [ids["CP-00302"]], "motivo": "Se digitaliza en el siguiente lote"}, headers=org_a.admin)
    assert _aprobar(cliente, director, url, d).status_code == 200
    assert cliente.post(f"{url}/{d['id']}/ejecutar", json={}, headers=org_a.admin).status_code == 422  # ¿qué pasa con el físico?
    r = cliente.post(f"{url}/{d['id']}/ejecutar", json={"destino_fisico": "eliminar"}, headers=org_a.admin).json()
    assert r["ejecutadas"] == 1 and r["nuevo_proceso"]["unidades"] == 1


def test_permisos_y_aislamiento(cliente, org_a, org_b):
    p, base, director, url, ids = _proyecto(cliente, org_a)
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo", [p["id"]])
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    e = _crear(cliente, equipo, url, "eliminacion")
    assert _aprobar(cliente, equipo, url, e).status_code == 403  # aprobar es otro permiso
    assert cliente.get(f"{url}/plan", headers=consulta).status_code == 200
    assert cliente.post(url, json={"tipo": "seleccion"}, headers=consulta).status_code == 403
    assert cliente.get(url, headers=org_b.admin).status_code == 404
    assert cliente.post(url, json={"tipo": "quemar"}, headers=org_a.admin).status_code == 422
