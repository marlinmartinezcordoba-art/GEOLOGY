"""M10 y M11 · Carga desde carpeta, identificación de expedientes, control de calidad, perfil y bandeja de revisión."""

from conftest import agregar_usuario, proyecto_basico
from fabricas import fuid_xlsx, imagen, pdf_escaneado
from test_m08_fuid import FILAS

from arca.modulos.m10_digitalizacion.identificacion import analizar, saltos


def _proyecto_con_inventario(cliente, org):
    p = proyecto_basico(cliente, org)
    base = f"/api/v1/proyectos/{p['id']}"
    lote = cliente.post(f"{base}/inventario/lotes", files={"archivo": ("fuid.xlsx", fuid_xlsx(FILAS))}, headers=org.admin).json()
    cliente.post(f"{base}/inventario/lotes/{lote['id']}/integrar", json={}, headers=org.admin)
    return p, base


def _cargar(cliente, base, cabeceras, archivos: dict[str, bytes]):
    files = [("archivos", (ruta.rsplit("/", 1)[-1], datos)) for ruta, datos in archivos.items()]
    return cliente.post(f"{base}/digitalizacion/archivos", files=files, data={"rutas_relativas": list(archivos)}, headers=cabeceras)


def test_identificacion_por_nombre_y_por_carpeta():
    assert analizar("CARPETA_00374-2.pdf").opciones[0] == ("CARPETA374", 2)
    assert analizar("lote/CP-00375/0003.tif").opciones[0] == ("CP375", 0) and analizar("lote/CP-00375/0003.tif").pagina == 3
    assert analizar("CP-00376_0001.jpg").opciones[0] == ("CP376", 0)
    assert analizar("leame.txt") is None
    assert saltos([1, 2, 4, 6]) == [3, 5]


def test_carga_de_carpeta_con_pdf_e_imagenes(cliente, org_a):
    _, base = _proyecto_con_inventario(cliente, org_a)
    r = _cargar(cliente, base, org_a.admin, {
        "Entrega 1/CP-00374.pdf": pdf_escaneado(2),
        "Entrega 1/CARPETA_00375-1.pdf": pdf_escaneado(1),
        "Entrega 1/CP-00376/0001.tif": imagen(),
        "Entrega 1/CP-00376/0002.tif": imagen(),
        "Entrega 1/OTRA-99999.pdf": pdf_escaneado(1),
        "Entrega 1/Thumbs.db": b"basura",
    })
    assert r.status_code == 200, r.text
    reporte = {x["ruta"].split("/")[-1]: x for x in r.json()}
    assert reporte["CP-00374.pdf"]["unidad"] == "CP-00374" and reporte["CP-00374.pdf"]["estado"] == "aprobado"
    assert reporte["CARPETA_00375-1.pdf"]["unidad"] == "CP-00375"  # otro prefijo, mismo número: se reconoce
    assert reporte["0002.tif"]["unidad"] == "CP-00376"
    assert reporte["OTRA-99999.pdf"]["estado"] == "sin_identificar"
    assert reporte["Thumbs.db"]["resultado"] == "ignorado"
    resumen = cliente.get(f"{base}/digitalizacion/resumen", headers=org_a.admin).json()
    assert resumen["unidades"] == 3 and resumen["unidades_con_imagenes"] == 3 and resumen["imagenes"] == 5


def test_duplicados_por_huella(cliente, org_a):
    _, base = _proyecto_con_inventario(cliente, org_a)
    pdf = pdf_escaneado(1)
    _cargar(cliente, base, org_a.admin, {"CP-00374.pdf": pdf})
    r = _cargar(cliente, base, org_a.admin, {"copia/CP-00374 (copia).pdf": pdf})
    assert r.json()[0]["resultado"] == "duplicado"


def test_calidad_segun_el_perfil_del_proyecto(cliente, org_a):
    p, base = _proyecto_con_inventario(cliente, org_a)
    r = cliente.put(f"{base}/digitalizacion/perfil", json={"perfil": {"dpi_minimo": 300, "rechazo_automatico": ["ilegible", "duplicado", "resolucion_baja"]}, "motivo": "Perfil de preservación del contrato"}, headers=org_a.admin)
    assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["perfil"]["dpi_minimo"] == 300
    reporte = _cargar(cliente, base, org_a.admin, {
        "CP-00374/0001.tif": imagen(dpi=200),
        "CP-00375/0001.tif": imagen(en_blanco=True),
        "CP-00376.pdf": b"%PDF-1.4 truncado",
    }).json()
    estados = {x["ruta"]: x["estado"] for x in reporte}
    assert estados["CP-00374/0001.tif"] == "rechazado"  # 200 ppp con mínimo 300 y regla de rechazo automático
    assert estados["CP-00375/0001.tif"] == "en_revision"  # en blanco: lo decide una persona
    assert estados["CP-00376.pdf"] == "rechazado"  # ilegible
    lista = cliente.get(f"{base}/digitalizacion/archivos?estado=rechazado", headers=org_a.admin).json()
    assert lista["total"] == 2 and all(x["perfil_version"] == 1 for x in lista["recursos"])
    assert cliente.put(f"{base}/digitalizacion/perfil", json={"perfil": {"dpi_minimo": "alto"}, "motivo": "Valor inválido"}, headers=org_a.admin).status_code == 422


def test_saltos_de_secuencia_y_folios(cliente, org_a):
    _, base = _proyecto_con_inventario(cliente, org_a)
    reporte = _cargar(cliente, base, org_a.admin, {"CP-00374/0001.tif": imagen(), "CP-00374/0003.tif": imagen()}).json()
    assert all(x["unidad"] == "CP-00374" for x in reporte)
    assert all(x["estado"] == "aprobado" for x in reporte)  # cada imagen está bien; lo incompleto es el expediente
    unidades = cliente.get(f"{base}/digitalizacion/unidades?filtro=con_alertas", headers=org_a.admin).json()["unidades"]
    assert [u["identificador"] for u in unidades] == ["CP-00374"]
    mensajes = " ".join(a["mensaje"] for a in unidades[0]["alertas"])
    assert "faltan las páginas 2" in mensajes and "120 folios" in mensajes
    assert cliente.get(f"{base}/digitalizacion/unidades?filtro=sin_imagenes", headers=org_a.admin).json()["total"] == 2


def test_bandeja_recaptura_y_reemplazo(cliente, org_a):
    _, base = _proyecto_con_inventario(cliente, org_a)
    _, revisor = agregar_usuario(cliente, org_a, "calidad@alfa.example.com", "Equipo operativo")
    _cargar(cliente, base, org_a.admin, {"CP-00375/0001.tif": imagen(en_blanco=True)})
    recurso = cliente.get(f"{base}/digitalizacion/archivos?estado=en_revision", headers=org_a.admin).json()["recursos"][0]
    url = f"{base}/digitalizacion/archivos/{recurso['id']}/decidir"
    # Quien cargó no aprueba sus propias alertas.
    assert cliente.post(url, json={"decision": "aprobar", "motivo": "Se ve bien"}, headers=org_a.admin).status_code == 409
    r = cliente.post(url, json={"decision": "recaptura", "motivo": "Página en blanco: escanear de nuevo"}, headers=revisor)
    assert r.status_code == 200 and r.json()["estado"] == "recaptura"
    _cargar(cliente, base, org_a.admin, {"recaptura/CP-00375/0001.tif": imagen()})
    anterior = cliente.get(f"{base}/digitalizacion/archivos?estado=reemplazado", headers=org_a.admin).json()["recursos"]
    nuevo = cliente.get(f"{base}/digitalizacion/archivos?estado=aprobado", headers=org_a.admin).json()["recursos"]
    assert anterior[0]["id"] == recurso["id"] and nuevo[0]["reemplaza_id"] == recurso["id"]


def test_asignar_lo_que_no_se_reconocio(cliente, org_a):
    _, base = _proyecto_con_inventario(cliente, org_a)
    _cargar(cliente, base, org_a.admin, {"escaneo-sin-nombre.pdf": pdf_escaneado(1)})
    recurso = cliente.get(f"{base}/digitalizacion/archivos?estado=sin_identificar", headers=org_a.admin).json()["recursos"][0]
    unidad = cliente.get(f"{base}/inventario/unidades?q=CP-00376", headers=org_a.admin).json()["unidades"][0]
    r = cliente.post(f"{base}/digitalizacion/archivos/{recurso['id']}/asignar", json={"unidad_id": unidad["id"], "motivo": "Identificado por el rótulo"}, headers=org_a.admin)
    assert r.status_code == 200 and r.json()["unidad_identificador"] == "CP-00376" and r.json()["estado"] == "aprobado"


def test_visor_entrega_el_original_verificado(cliente, org_a):
    _, base = _proyecto_con_inventario(cliente, org_a)
    pdf = pdf_escaneado(1)
    _cargar(cliente, base, org_a.admin, {"CP-00374.pdf": pdf})
    recurso = cliente.get(f"{base}/digitalizacion/archivos", headers=org_a.admin).json()["recursos"][0]
    r = cliente.get(f"{base}/digitalizacion/archivos/{recurso['id']}/contenido", headers=org_a.admin)
    assert r.status_code == 200 and r.content == pdf and r.headers["content-type"] == "application/pdf"


def test_permisos_y_aislamiento_de_la_digitalizacion(cliente, org_a, org_b):
    _, base = _proyecto_con_inventario(cliente, org_a)
    _, consulta = agregar_usuario(cliente, org_a, "auditor@alfa.example.com", "Consulta y auditoría")
    assert _cargar(cliente, base, consulta, {"CP-00374.pdf": pdf_escaneado(1)}).status_code == 403
    assert cliente.get(f"{base}/digitalizacion/resumen", headers=consulta).status_code == 200
    assert _cargar(cliente, base, org_b.admin, {"CP-00374.pdf": pdf_escaneado(1)}).status_code == 404
    assert cliente.get(f"{base}/digitalizacion/archivos", headers=org_b.admin).status_code == 404
