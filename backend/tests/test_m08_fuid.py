"""M08 · Importar, mapear, validar e integrar el FUID; conservar la fila original; aislamiento entre proyectos."""

from conftest import agregar_usuario, proyecto_basico
from fabricas import fuid_xlsx

FILAS = [
    [1, "CP-00374", "100.01", "Expediente ficticio uno", "1956-03-01", "1958-12-31", "CJ-0012", "1", "", "", 120, "Papel", ""],
    [2, "CP-00375", "100.01", "Expediente ficticio dos", "1960", "1961", "CJ-0012", "2", "", "", 85, "Papel", ""],
    [3, "CP-00376", "100.02", "Correspondencia", "s.f.", "", "CJ-0013", "1", "", "", "", "Papel", "Sin fechas"],
]


def _importar(cliente, org, proyecto_id, contenido, nombre="fuid.xlsx"):
    return cliente.post(f"/api/v1/proyectos/{proyecto_id}/inventario/lotes", files={"archivo": (nombre, contenido)}, headers=org.admin)


def test_importa_fuid_del_agn_con_encabezado_de_dos_niveles(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    r = _importar(cliente, org_a, p["id"], fuid_xlsx(FILAS))
    assert r.status_code == 201, r.text
    lote = r.json()
    assert lote["estado"] == "validado" and lote["total_filas"] == 3 and lote["filas_con_error"] == 0
    assert {"orden", "identificador", "nombre", "fecha_inicial", "fecha_final", "caja", "carpeta", "folios"} <= set(lote["mapeo"])
    filas = cliente.get(f"/api/v1/proyectos/{p['id']}/inventario/lotes/{lote['id']}/filas", headers=org_a.admin).json()
    assert filas[0]["original"][1] == "CP-00374" and filas[0]["normalizado"]["fecha_inicial"] == "1956-03-01"
    assert filas[1]["normalizado"]["fecha_final"] == "1961-12-31"  # el año solo se toma como fin de año
    assert "sin fechas extremas (s.f.)" in filas[2]["avisos"] and "sin número de folios" in filas[2]["avisos"]


def test_integrar_crea_unidades_y_no_pisa_existentes(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    lote = _importar(cliente, org_a, p["id"], fuid_xlsx(FILAS)).json()
    r = cliente.post(f"/api/v1/proyectos/{p['id']}/inventario/lotes/{lote['id']}/integrar", json={}, headers=org_a.admin)
    assert r.status_code == 200 and r.json()["filas_integradas"] == 3
    unidades = cliente.get(f"/api/v1/proyectos/{p['id']}/inventario/unidades", headers=org_a.admin).json()
    assert unidades["total"] == 3 and unidades["unidades"][0]["identificador"] == "CP-00374" and unidades["unidades"][0]["folios"] == 120
    # El mismo inventario otra vez: todas sus filas chocan con lo ya integrado.
    otra = _importar(cliente, org_a, p["id"], fuid_xlsx(FILAS)).json()
    assert otra["estado"] == "con_errores" and otra["filas_con_error"] == 3
    # Buscar por identificador escrito de otra forma.
    assert cliente.get(f"/api/v1/proyectos/{p['id']}/inventario/unidades?q=cp 374", headers=org_a.admin).json()["total"] == 1


def test_errores_por_fila_y_conciliacion_con_motivo(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    malas = FILAS + [
        [4, "CP-00374", "100.01", "Repetida en el archivo", "1950", "1951", "", "", "", "", 10, "", ""],
        [5, "CP-00380", "100.01", "Fechas al revés", "1990-01-01", "1980-01-01", "", "", "", "", "doce", "", ""],
    ]
    lote = _importar(cliente, org_a, p["id"], fuid_xlsx(malas)).json()
    assert lote["estado"] == "con_errores" and lote["filas_validas"] == 3 and lote["filas_con_error"] == 2
    errores = cliente.get(f"/api/v1/proyectos/{p['id']}/inventario/lotes/{lote['id']}/filas?solo_errores=true", headers=org_a.admin).json()
    assert [f["numero_fila"] for f in errores] == [9, 10]
    assert any("repetido" in e for e in errores[0]["errores"])
    assert any("posterior" in e for e in errores[1]["errores"]) and any("folios" in e for e in errores[1]["errores"])
    url = f"/api/v1/proyectos/{p['id']}/inventario/lotes/{lote['id']}/integrar"
    assert cliente.post(url, json={}, headers=org_a.admin).status_code == 422  # sin motivo no se integra a medias
    r = cliente.post(url, json={"motivo": "Las dos filas se corrigen en un FUID complementario"}, headers=org_a.admin)
    assert r.json()["filas_integradas"] == 3 and r.json()["filas_con_error"] == 2


def test_mapeo_manual_cuando_no_hay_identificador(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    sin_id = [[f[0], *f[2:]] for f in FILAS]
    lote = _importar(cliente, org_a, p["id"], fuid_xlsx(sin_id, con_identificador=False)).json()
    assert lote["estado"] == "validado" and "identificador" not in lote["mapeo"]  # usa el número de orden
    mapeo = dict(lote["mapeo"])
    mapeo["identificador"] = mapeo.pop("codigo_serie")
    r = cliente.put(f"/api/v1/proyectos/{p['id']}/inventario/lotes/{lote['id']}/mapeo", json={"mapeo": mapeo}, headers=org_a.admin)
    assert r.status_code == 200 and r.json()["estado"] == "con_errores"  # los códigos de serie se repiten: no sirven de identificador
    r = cliente.put(f"/api/v1/proyectos/{p['id']}/inventario/lotes/{lote['id']}/mapeo", json={"mapeo": {"nombre": 99}}, headers=org_a.admin)
    assert r.status_code == 422


def test_archivo_que_no_es_fuid(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    assert _importar(cliente, org_a, p["id"], b"%PDF-1.4 falso", "fuid.xlsx").status_code == 422
    assert _importar(cliente, org_a, p["id"], b"a;b;c\n1;2;3\n", "fuid.csv").status_code == 422


def test_permisos_y_aislamiento_del_inventario(cliente, org_a, org_b):
    p = proyecto_basico(cliente, org_a)
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    assert _importar(cliente, org_a, p["id"], fuid_xlsx(FILAS)).status_code == 201
    r = cliente.post(f"/api/v1/proyectos/{p['id']}/inventario/lotes", files={"archivo": ("f.xlsx", fuid_xlsx(FILAS))}, headers=equipo)
    assert r.status_code == 403  # el equipo operativo consulta el inventario pero no lo importa
    assert cliente.get(f"/api/v1/proyectos/{p['id']}/inventario/lotes", headers=equipo).status_code == 200
    _, entidad = agregar_usuario(cliente, org_a, "cliente@entidad.example.com", "Entidad cliente")
    assert cliente.get(f"/api/v1/proyectos/{p['id']}/inventario/lotes", headers=entidad).status_code == 403
    assert cliente.get(f"/api/v1/proyectos/{p['id']}/inventario/lotes", headers=org_b.admin).status_code == 404
