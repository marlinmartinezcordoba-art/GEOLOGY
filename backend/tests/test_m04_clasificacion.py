"""M04 · Clasificación de las unidades del FUID con la TRD o TVD vigente. Datos ficticios."""


from conftest import agregar_usuario, proyecto_basico
from fabricas import fuid_xlsx
from test_m04_instrumentos import BASE, _aprobar, _importar, _libro

FILAS = [
    [1, "CP-1", "100-02.01", "Actas del comité directivo", "1990-01-01", "1990-12-31", "C-1", "1", "", "", 10, "Papel", ""],
    [2, "CP-2", "100-05", "Decretos de la dirección", "1991-01-01", "1991-12-31", "C-1", "2", "", "", 20, "Papel", ""],
    [3, "CP-3", "110-05", "Expediente jurídico", "1992-01-01", "1992-12-31", "C-2", "1", "", "", 30, "Papel", ""],
    [4, "CP-4", "", "Acciones de tutela de un ciudadano ficticio", "1993-01-01", "1993-12-31", "C-2", "2", "", "", 5, "Papel", ""],
    [5, "CP-5", "", "Carpeta sin pistas", "1994-01-01", "1994-12-31", "C-3", "1", "", "", 5, "Papel", ""],
    [6, "CP-6", "", "Actas del comité de un fondo anterior", "1980-01-01", "1981-06-30", "C-3", "2", "", "", 5, "Papel", ""],
]
# Códigos escritos de otra forma: no clasifican solos.
OTRA_FORMA = [
    [1, "CP-1", "100.05", "Decretos de la dirección", "1991-01-01", "1991-12-31", "C-1", "1", "", "", 20, "Papel", ""],
    [2, "CP-2", "100.02", "Correspondencia", "1991-01-01", "1991-12-31", "C-1", "2", "", "", 20, "Papel", ""],
]


def _escenario(cliente, org, filas=FILAS):
    p = proyecto_basico(cliente, org)
    inv = f"/api/v1/proyectos/{p['id']}/inventario"
    lote = cliente.post(f"{inv}/lotes", files={"archivo": ("fuid.xlsx", fuid_xlsx(filas))}, headers=org.admin).json()
    assert cliente.post(f"{inv}/lotes/{lote['id']}/integrar", json={}, headers=org.admin).status_code == 200
    _, director = agregar_usuario(cliente, org, "director@alfa.example.com", "Dirección de proyecto")
    url = f"/api/v1/proyectos/{p['id']}/instrumentos"
    return p, url, director, f"/api/v1/proyectos/{p['id']}/clasificacion"


def _trd(cliente, org, director, url, filas=BASE, nombre="TRD de la entidad"):
    inst = cliente.post(url, json={"tipo": "TRD", "nombre": nombre}, headers=org.admin).json()
    v = _importar(cliente, org.admin, url, inst["id"], _libro(filas)).json()
    assert _aprobar(cliente, director, url, inst["id"], v["id"]).status_code == 200
    return inst


def _filas(cliente, cab, cla, **consulta):
    return {f["unidad"]["identificador"]: f for f in cliente.get(cla, params={"limite": 500} | consulta, headers=cab).json()["filas"]}


def test_sin_instrumento_vigente_no_se_clasifica(cliente, org_a):
    _, _, _, cla = _escenario(cliente, org_a)
    r = cliente.post(f"{cla}/proponer", headers=org_a.admin)
    assert r.status_code == 422 and "TRD" in r.json()["detail"]
    assert cliente.get(f"{cla}/resumen", headers=org_a.admin).json()["pendiente"] == 6


def test_propuesta_automatica_por_fuid_y_por_nombre(cliente, org_a):
    p, url, director, cla = _escenario(cliente, org_a)
    _trd(cliente, org_a, director, url)
    r = cliente.post(f"{cla}/proponer", headers=org_a.admin).json()
    assert r == {"confirmadas": 2, "propuestas": 3, "sin_propuesta": 1, "sin_instrumento": 0}
    f = _filas(cliente, org_a.admin, cla)
    assert f["CP-1"]["clasificacion"]["codigo"] == "100-02.01" and f["CP-1"]["situacion"] == "confirmada" and f["CP-1"]["clasificacion"]["origen"] == "inventario"
    assert f["CP-2"]["clasificacion"]["codigo"] == "100-05"  # serie sin subseries
    assert f["CP-3"]["clasificacion"]["codigo"] == "110-05.01" and f["CP-3"]["situacion"] == "propuesta" and f["CP-3"]["clasificacion"]["origen"] == "codigo"  # la serie tiene una sola subserie
    assert f["CP-4"]["clasificacion"]["codigo"] == "110-05.01" and f["CP-4"]["clasificacion"]["origen"] == "motor" and "nombre" in f["CP-4"]["clasificacion"]["porque"]
    assert f["CP-5"]["situacion"] == "pendiente"  # nada coincide: no se inventa
    # El calendario sale de la fecha final y de la retención: 1990-12-31 + 2 años de gestión + 18 de central.
    cal = f["CP-1"]["clasificacion"]["calendario"]
    assert (cal["fin_gestion"], cal["fin_central"], cal["fase"], cal["disposicion"]) == ("1992-12-31", "2010-12-31", "cumplida", "conservación total")
    # Una segunda pasada no toca lo ya clasificado.
    assert cliente.post(f"{cla}/proponer", headers=org_a.admin).json()["confirmadas"] == 0


def test_codigo_escrito_de_otra_forma_y_nombre_que_no_coincide(cliente, org_a):
    _, url, director, cla = _escenario(cliente, org_a, OTRA_FORMA)
    _trd(cliente, org_a, director, url)
    assert cliente.post(f"{cla}/proponer", headers=org_a.admin).json()["confirmadas"] == 0
    f = _filas(cliente, org_a.admin, cla)
    c1, c2 = f["CP-1"]["clasificacion"], f["CP-2"]["clasificacion"]
    assert (c1["codigo"], c1["origen"], c1["confianza"], f["CP-1"]["situacion"]) == ("100-05", "codigo", "media", "propuesta")
    assert "100-05" in c1["porque"]
    # «Correspondencia» no se parece a «Actas de comité directivo»: la propuesta baja y lo dice.
    assert (c2["codigo"], c2["confianza"]) == ("100-02.01", "baja") and "no se parece" in c2["porque"]


def test_confirmar_rechazar_y_asignar(cliente, org_a):
    p, url, director, cla = _escenario(cliente, org_a)
    _trd(cliente, org_a, director, url)
    cliente.post(f"{cla}/proponer", headers=org_a.admin)
    f = _filas(cliente, org_a.admin, cla)
    assert cliente.post(f"{cla}/confirmar", json={"clasificaciones": [f["CP-3"]["clasificacion"]["id"]]}, headers=org_a.admin).json() == {"confirmadas": 1}
    assert cliente.post(f"{cla}/rechazar", json={"clasificaciones": [f["CP-4"]["clasificacion"]["id"]]}, headers=org_a.admin).status_code == 422  # sin motivo
    r = cliente.post(f"{cla}/rechazar", json={"clasificaciones": [f["CP-4"]["clasificacion"]["id"]], "motivo": "No es una tutela"}, headers=org_a.admin)
    assert r.json() == {"rechazadas": 1}
    assert cliente.post(f"{cla}/confirmar", json={"clasificaciones": [f["CP-1"]["clasificacion"]["id"]]}, headers=org_a.admin).status_code == 422  # ya confirmada
    opciones = cliente.get(f"{cla}/opciones", headers=org_a.admin).json()[0]["elementos"]
    codigos = {e["codigo"]: e["id"] for e in opciones}
    assert "100-02" not in codigos and {"100-02.01", "100-05", "110-05.01"} <= set(codigos)  # la serie con subseries no se ofrece
    unidades = [f["CP-4"]["unidad"]["id"], f["CP-5"]["unidad"]["id"]]
    assert cliente.post(f"{cla}/asignar", json={"unidades": unidades, "elemento_id": codigos["100-05"]}, headers=org_a.admin).json() == {"clasificadas": 2}
    # Reclasificar lo confirmado exige motivo; la anterior queda reemplazada y aparece la alerta contra el FUID.
    cp1 = [f["CP-1"]["unidad"]["id"]]
    assert cliente.post(f"{cla}/asignar", json={"unidades": cp1, "elemento_id": codigos["110-05.01"]}, headers=org_a.admin).status_code == 422
    r = cliente.post(f"{cla}/asignar", json={"unidades": cp1, "elemento_id": codigos["110-05.01"], "motivo": "Revisado el contenido"}, headers=org_a.admin)
    assert r.status_code == 200
    f = _filas(cliente, org_a.admin, cla)
    assert f["CP-1"]["clasificacion"]["codigo"] == "110-05.01" and any("100-02.01" in a for a in f["CP-1"]["alertas"])
    assert set(_filas(cliente, org_a.admin, cla, alertas=True)) == {"CP-1"}
    resumen = cliente.get(f"{cla}/resumen", headers=org_a.admin).json()
    assert resumen["confirmada"] == 5 and resumen["propuesta"] == 1 and resumen["pendiente"] == 0 and resumen["con_alertas"] == 1


def test_lo_clasificado_conserva_su_version(cliente, org_a):
    p, url, director, cla = _escenario(cliente, org_a)
    inst = _trd(cliente, org_a, director, url)
    cliente.post(f"{cla}/proponer", headers=org_a.admin)
    # La v2 cambia el código de los decretos: 100-05 deja de existir y aparece 100-06.
    nueva = [BASE[0], ["100", "Dirección general", "100-06", "Decretos", "", "", "Decreto", 2, 18, "X", "", "", "", "F"], BASE[2]]
    v2 = _importar(cliente, org_a.admin, url, inst["id"], _libro(nueva)).json()
    _aprobar(cliente, director, url, inst["id"], v2["id"], acto_administrativo="Resolución 002 (ficticia)")
    f = _filas(cliente, org_a.admin, cla)
    assert f["CP-1"]["situacion"] == "version_anterior" and f["CP-1"]["clasificacion"]["version"] == 1  # no se movió sola
    assert any("v1" in a for a in f["CP-1"]["alertas"])
    propuesta = f["CP-3"]["clasificacion"]["id"]
    assert cliente.post(f"{cla}/confirmar", json={"clasificaciones": [propuesta]}, headers=org_a.admin).status_code == 422  # propuesta con versión vieja
    r = cliente.post(f"{cla}/actualizar-version", json={"motivo": "Adopción de la TRD v2"}, headers=org_a.admin).json()
    assert r == {"actualizadas": 4, "sin_equivalente": 1}  # CP-2 (100-05) no tiene equivalente en la v2
    f = _filas(cliente, org_a.admin, cla)
    assert f["CP-1"]["clasificacion"]["version"] == 2 and f["CP-1"]["situacion"] == "confirmada"
    assert f["CP-2"]["situacion"] == "version_anterior"


def test_tvd_para_el_fondo_acumulado(cliente, org_a):
    p, url, director, cla = _escenario(cliente, org_a)
    _trd(cliente, org_a, director, url)
    tvd = cliente.post(url, json={"tipo": "TVD", "nombre": "TVD periodo 1970-1989", "periodo_desde": "1970-01-01", "periodo_hasta": "1989-12-31"}, headers=org_a.admin).json()
    filas_tvd = [["900", "Junta directiva", "900-01", "Actas", "900-01.01", "Actas de junta del comité", "Acta", None, None, "X", "", "", "", "F"]]
    v = _importar(cliente, org_a.admin, url, tvd["id"], _libro(filas_tvd)).json()
    assert v["errores"] == [], v["errores"]
    assert _aprobar(cliente, director, url, tvd["id"], v["id"]).status_code == 200
    cliente.post(f"{cla}/proponer", headers=org_a.admin)
    f = _filas(cliente, org_a.admin, cla)
    assert f["CP-6"]["clasificacion"]["instrumento"].startswith("TVD") and f["CP-6"]["clasificacion"]["codigo"] == "900-01.01"  # 1980-1981
    assert f["CP-1"]["clasificacion"]["instrumento"].startswith("TRD")
    assert f["CP-6"]["clasificacion"]["calendario"]["fase"] is None  # la TVD no trae tiempos: solo disposición
    assert f["CP-6"]["clasificacion"]["calendario"]["disposicion"] == "conservación total"


def test_permisos_y_aislamiento(cliente, org_a, org_b):
    p, url, director, cla = _escenario(cliente, org_a)
    _trd(cliente, org_a, director, url)
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(f"{cla}/resumen", headers=consulta).status_code == 200
    assert cliente.post(f"{cla}/proponer", headers=consulta).status_code == 403
    assert cliente.get(cla, headers=org_b.admin).status_code == 404
    pb = proyecto_basico(cliente, org_b, "B-1")
    f = _filas(cliente, org_a.admin, cla)
    otro = cliente.get(f"{cla}/opciones", headers=org_a.admin).json()[0]["elementos"][0]["id"]
    r = cliente.post(f"/api/v1/proyectos/{pb['id']}/clasificacion/asignar", json={"unidades": [f["CP-1"]["unidad"]["id"]], "elemento_id": otro}, headers=org_b.admin)
    assert r.status_code == 422  # el elemento no es de un instrumento de ese proyecto
