"""Historias laborales (D-43): titular del FUID y del OCR, documentos de otra persona, tipos mínimos, orden cronológico
y duplicados. Personas, números de documento y entidad ficticios."""

from conftest import agregar_usuario
from fabricas import pdf_con_texto, pdf_escaneado
from test_m04_clasificacion import _escenario, _trd
from test_m13_ocr import requiere_tesseract

from arca.modulos.historias.servicios import del_fuid, documentos_en

FILAS = [
    [1, "HL-1", "100-02.01", "Historia laboral PÉREZ GÓMEZ ANA · C.C. 52.123.456", "2015-01-01", "2020-12-31", "C-1", "1", "", "", 3, "Papel", ""],
    [2, "HL-2", "100-02.01", "Historia laboral RUIZ LUIS · C.C. 79.555.111", "2016-01-01", "2021-12-31", "C-1", "2", "", "", 5, "Papel", ""],
    [3, "HL-3", "100-02.01", "Historia laboral PÉREZ GÓMEZ ANA tomo 2 · C.C. 52123456", "2021-01-01", "2022-12-31", "C-2", "1", "", "", 5, "Papel", ""],
    [4, "HL-4", "100-02.01", "Historia laboral sin datos de la persona", "2010-01-01", "2011-12-31", "C-2", "2", "", "", 2, "Papel", ""],
]
PAGINAS = [
    ["ENTIDAD FICTICIA NACIONAL", "RESOLUCIÓN N.º 101", "Ciudad Ficticia, 2 de enero de 2015", "Por la cual se nombra a ANA PÉREZ GÓMEZ", "identificada con C.C. 52.123.456"],
    ["ENTIDAD FICTICIA NACIONAL", "ACTA DE POSESIÓN N.º 7", "Ciudad Ficticia, 15 de enero de 2015", "Se posesiona ANA PÉREZ GÓMEZ, C.C. 52123456"],
    ["ENTIDAD FICTICIA NACIONAL", "CERTIFICADO MÉDICO", "Ciudad Ficticia, 10 de enero de 2015", "Paciente: LUIS RUIZ, C.C. 79.555.111"],
]
CONFIG = {"activo": True, "series": ["100-02"], "tipos_obligatorios": ["Resolución de nombramiento", "Acta de posesión", "Certificado de antecedentes"],
          "motivo": "Tipos mínimos de la serie (ficticio)"}


def test_numero_de_documento_y_nombre_sin_ocr():
    assert documentos_en("identificada con C.C. 52.123.456 de Ciudad Ficticia") == ["52123456"]
    assert documentos_en("cédula de ciudadanía No. 79555111 · T.I. 1002003004") == ["79555111", "1002003004"]
    assert documentos_en("Radicado No. 2020-00123 · NIT 900.123.456-8 · folio 12345") == []  # sin su rótulo no es un documento de identidad
    assert del_fuid("Historia laboral PÉREZ GÓMEZ ANA · C.C. 52.123.456") == {"numero_documento": "52123456", "nombres": "PÉREZ GÓMEZ ANA"}
    assert del_fuid("Hoja de vida de Marta Ficticia - CE 4567890") == {"numero_documento": "4567890", "tipo_documento": "CE", "nombres": "Marta Ficticia"}
    assert del_fuid("Historia laboral PÉREZ GÓMEZ ANA tomo 2 · C.C. 52123456")["nombres"] == "PÉREZ GÓMEZ ANA"
    assert del_fuid("Actas del comité directivo") == {}  # sin número, el nombre de la unidad no es el de una persona


def _proyecto(cliente, org):
    p, url, director, cla = _escenario(cliente, org, FILAS)
    _trd(cliente, org, director, url)
    cliente.post(f"{cla}/proponer", headers=org.admin)
    base = f"/api/v1/proyectos/{p['id']}"
    unidades = {u["identificador"]: u["id"] for u in cliente.get(f"{base}/inventario/unidades", headers=org.admin).json()["unidades"]}
    return p, base, director, unidades


@requiere_tesseract
def test_titular_otra_persona_tipos_minimos_orden_y_duplicados(cliente, org_a, org_b):
    p, base, director, u = _proyecto(cliente, org_a)
    hl = f"{base}/historias"
    assert cliente.put(f"{hl}/config", json=CONFIG, headers=org_a.admin).status_code == 200  # administración = todos los permisos
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo", [p["id"]])
    assert cliente.put(f"{hl}/config", json=CONFIG, headers=equipo).status_code == 403  # la configuración es de la dirección
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("HL-1.pdf", pdf_con_texto(PAGINAS)))], data={"rutas_relativas": ["HL-1.pdf"]}, headers=org_a.admin)
    assert cliente.post(f"{base}/ocr/unidades/{u['HL-1']}/leer", json={}, headers=org_a.admin).json()["procesadas"] == 3
    assert cliente.post(f"{hl}/expedientes/proponer", headers=equipo).json() == {"propuestos": 3}  # HL-4 no trae número en el FUID ni tiene OCR
    e = cliente.get(f"{hl}/expedientes/{u['HL-1']}", headers=equipo).json()
    t = e["titular"]
    assert (t["numero_documento"], t["nombres"], t["estado"], t["origen"]["numero_documento"]["fuente"]) == ("52123456", "PÉREZ GÓMEZ ANA", "propuesto", "fuid")
    assert "aparece en las páginas 1, 2" in t["origen"]["numero_documento"]["detalle"]
    clases = {a["clase"]: a for a in e["alertas"]}
    assert clases["otra_persona"]["paginas"] == [3] and "79555111" in clases["otra_persona"]["mensaje"]
    assert "HL-3" in clases["duplicado"]["mensaje"]
    # Hoja de control: tipos mínimos que faltan y orden cronológico.
    hc = f"{base}/hojas-control/unidades/{u['HL-1']}"
    d = cliente.post(hc, json={}, headers=equipo).json()
    d = cliente.post(f"{hc}/tramites/{d['tramites'][0]['id']}/dividir", json={"pagina": 2}, headers=equipo).json()
    d = cliente.post(f"{hc}/tramites/{d['tramites'][1]['id']}/dividir", json={"pagina": 3}, headers=equipo).json()
    for tr, (tipo, fecha) in zip(d["tramites"], (("Resolución de nombramiento", "2015-01-02"), ("Acta de posesión", "2015-01-15"), ("Certificado médico", "2015-01-10")), strict=True):
        cliente.patch(f"{hc}/tramites/{tr['id']}", json={"tipo_documental": tipo, "fecha": fecha}, headers=equipo)
    avisos = cliente.get(hc, headers=equipo).json()["validacion"]["avisos"]
    assert any("trámite 3: su fecha (2015-01-10) es anterior a la del trámite 2" in a for a in avisos)
    assert any("historia laboral: faltan 1 de los 3 tipos documentales mínimos de la serie: Certificado de antecedentes" in a for a in avisos)
    assert any("historia laboral: aparece otro número de documento (79555111)" in a for a in avisos)
    # Una persona confirma el titular; la consulta encuentra el expediente por el número de documento.
    r = cliente.put(f"{hl}/expedientes/{u['HL-1']}/titular", json={"cargo": "Profesional ficticio", "fecha_vinculacion": "2015-01-15", "fecha_retiro": "2014-01-01"}, headers=equipo)
    assert r.status_code == 422  # retiro antes de la vinculación
    e = cliente.put(f"{hl}/expedientes/{u['HL-1']}/titular", json={"cargo": "Profesional ficticio", "fecha_vinculacion": "2015-01-15"}, headers=equipo).json()
    assert e["titular"]["estado"] == "confirmado" and e["titular"]["origen"]["cargo"]["fuente"] == "persona"
    assert cliente.post(f"{hl}/expedientes/proponer", headers=equipo).json() == {"propuestos": 2}  # lo confirmado no se vuelve a proponer
    hallados = cliente.get("/api/v1/consulta/buscar", params={"q": "52123456"}, headers=org_a.admin).json()["filas"]
    assert {f["identificador"] for f in hallados} >= {"HL-1", "HL-3"}
    tablero = cliente.get(f"{hl}/expedientes", headers=equipo).json()
    assert tablero["resumen"]["expedientes"] == 4 and tablero["resumen"]["confirmados"] == 1 and tablero["resumen"]["por_clase"]["sin_numero"] == 1
    assert {f["identificador"] for f in cliente.get(f"{hl}/expedientes", params={"alerta": "duplicado"}, headers=equipo).json()["filas"]} == {"HL-1", "HL-3"}
    # Permisos y aislamiento.
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(f"{hl}/expedientes/{u['HL-1']}", headers=consulta).status_code == 200
    assert cliente.put(f"{hl}/expedientes/{u['HL-1']}/titular", json={"cargo": "x"}, headers=consulta).status_code == 403
    assert cliente.get(f"{hl}/expedientes", headers=org_b.admin).status_code == 404


def test_sin_configuracion_no_aplica_y_orden_cronologico_para_todos(cliente, org_a):
    p, base, director, u = _proyecto(cliente, org_a)
    hl = f"{base}/historias"
    assert not cliente.get(f"{hl}/config", headers=org_a.admin).json()["configurado"]
    assert cliente.get(f"{hl}/expedientes", headers=org_a.admin).json()["resumen"]["expedientes"] == 0
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("HL-2.pdf", pdf_escaneado(2)))], data={"rutas_relativas": ["HL-2.pdf"]}, headers=org_a.admin)
    hc = f"{base}/hojas-control/unidades/{u['HL-2']}"
    d = cliente.post(hc, json={}, headers=org_a.admin).json()
    d = cliente.post(f"{hc}/tramites/{d['tramites'][0]['id']}/dividir", json={"pagina": 2}, headers=org_a.admin).json()
    for tr, fecha in zip(d["tramites"], ("2016-05-01", "2016-02-01"), strict=True):
        cliente.patch(f"{hc}/tramites/{tr['id']}", json={"tipo_documental": "Acta", "fecha": fecha}, headers=org_a.admin)
    avisos = cliente.get(hc, headers=org_a.admin).json()["validacion"]["avisos"]
    assert any("revise el orden cronológico" in a for a in avisos) and not any("historia laboral" in a for a in avisos)


def _plantilla(cliente, org, tipo, contenido):
    pl = cliente.post("/api/v1/plantillas", json={"tipo": tipo, "nombre": f"Formato {tipo} de la entidad"}, headers=org.admin).json()
    r = cliente.post(f"/api/v1/plantillas/{pl['id']}/versiones", files={"archivo": ("f.xlsx", contenido)}, data={"motivo": "Formato de la entidad ficticia"}, headers=org.admin)
    assert r.status_code == 201, r.text


def _textos(cliente, org, base, expedicion_id):
    import io  # noqa: PLC0415

    import openpyxl  # noqa: PLC0415

    hoja = openpyxl.load_workbook(io.BytesIO(cliente.get(f"{base}/entregables/{expedicion_id}/archivo", headers=org.admin).content)).active
    return [[str(c.value) for c in f if c.value is not None] for f in hoja.iter_rows()]


def test_fuid_con_titular_lista_de_chequeo_y_acceso_restringido(cliente, org_a):
    import io  # noqa: PLC0415

    import openpyxl  # noqa: PLC0415

    p, base, director, u = _proyecto(cliente, org_a)
    hl = f"{base}/historias"
    cliente.put(f"{hl}/config", json=CONFIG, headers=director)
    cliente.post(f"{hl}/expedientes/proponer", headers=org_a.admin)
    # 1. El FUID de salida lleva el titular de cada historia.
    libro = openpyxl.Workbook()
    h = libro.active
    h.append(["Identificador", "Documento", "Titular"])
    h.append(["{{fila.identificador}}", "{{fila.tipo_documento}} {{fila.numero_documento}}", "{{fila.titular}}"])
    salida = io.BytesIO()
    libro.save(salida)
    _plantilla(cliente, org_a, "fuid", salida.getvalue())
    e = cliente.post(f"{base}/entregables", json={"tipo": "fuid"}, headers=org_a.admin).json()
    filas = {f[0]: f for f in _textos(cliente, org_a, base, e["id"])[1:]}
    assert filas["HL-1"][1:] == ["CC 52123456", "PÉREZ GÓMEZ ANA"] and filas["HL-2"][2] == "RUIZ LUIS"
    # 2. La lista de chequeo sale de la hoja de control, en el formato de la entidad.
    lc = f"{hl}/expedientes/{u['HL-2']}/lista-chequeo"
    assert cliente.post(lc, headers=org_a.admin).status_code == 422  # sin hoja de control
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("HL-2.pdf", pdf_escaneado(2)))], data={"rutas_relativas": ["HL-2.pdf"]}, headers=org_a.admin)
    hc = f"{base}/hojas-control/unidades/{u['HL-2']}"
    d = cliente.post(hc, json={}, headers=org_a.admin).json()
    d = cliente.post(f"{hc}/tramites/{d['tramites'][0]['id']}/dividir", json={"pagina": 2}, headers=org_a.admin).json()
    for tr, (tipo, fecha) in zip(d["tramites"], (("Resolución de nombramiento", "2016-01-04"), ("Certificado médico", "2016-01-10")), strict=True):
        cliente.patch(f"{hc}/tramites/{tr['id']}", json={"tipo_documental": tipo, "fecha": fecha}, headers=org_a.admin)
    assert cliente.post(lc, headers=org_a.admin).status_code == 422  # sin plantilla vigente: se dice
    tipos = cliente.get("/api/v1/plantillas/tipos", headers=org_a.admin).json()
    assert "numero_documento" in tipos["lista_chequeo"]["encabezado"] and "presente" in tipos["lista_chequeo"]["fila"]
    _plantilla(cliente, org_a, "lista_chequeo", cliente.get("/api/v1/plantillas/tipos/lista_chequeo/base", headers=org_a.admin).content)
    r = cliente.post(lc, headers=org_a.admin)
    assert r.status_code == 201 and r.json()["elementos"] == 4, r.text  # 3 mínimos + 1 adicional
    textos = _textos(cliente, org_a, base, r.json()["expedicion_id"])
    planos = [" ".join(f) for f in textos]
    assert any("Resolución de nombramiento" in f and "Sí Sí" in f for f in planos)
    assert any("Certificado de antecedentes" in f and "No está en el expediente" in f for f in planos)
    assert any("Certificado médico" in f and "No es de los tipos mínimos" in f for f in planos)
    assert any("RUIZ LUIS" in f for f in planos) and any("Faltan: Acta de posesión, Certificado de antecedentes" in f for f in planos)
    # 3. Acceso restringido: sin el permiso de consulta reservada solo se ven los metadatos.
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    fila = next(f for f in cliente.get("/api/v1/consulta/buscar", params={"q": "79555111"}, headers=consulta).json()["filas"] if f["identificador"] == "HL-2")
    assert fila["reservada"] and not fila["contenido_visible"] and fila["acceso"] == "restringida (historia laboral)"
    imagen = f"/api/v1/consulta/proyectos/{p['id']}/unidades/{u['HL-2']}/paginas/1/imagen"
    assert cliente.get(imagen, headers=consulta).status_code == 403
    assert cliente.get(imagen, headers=director).status_code == 200  # la dirección tiene consulta reservada
    cliente.put(f"{hl}/config", json=CONFIG | {"acceso_restringido": False, "motivo": "La TRD de la entidad ya define el acceso"}, headers=director)
    assert cliente.get(imagen, headers=consulta).status_code == 200
    fila = next(f for f in cliente.get("/api/v1/consulta/buscar", params={"q": "79555111"}, headers=consulta).json()["filas"] if f["identificador"] == "HL-2")
    assert fila["contenido_visible"]
