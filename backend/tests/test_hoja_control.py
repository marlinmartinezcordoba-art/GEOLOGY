"""Hoja de control sobre lo digitalizado: elaborar, ver los documentos y el origen de cada dato, verificar y expedir. Datos ficticios."""

import io

import openpyxl
from conftest import agregar_usuario
from fabricas import pdf_escaneado
from test_m04_clasificacion import FILAS, _escenario, _trd


def _listo(cliente, org, paginas=6):
    """Proyecto con FUID, TRD vigente, CP-1 clasificada en 100-02.01 (tipos: Citación; Acta) y digitalizada en un PDF."""
    p, url, director, cla = _escenario(cliente, org, FILAS)
    _trd(cliente, org, director, url)
    cliente.post(f"{cla}/proponer", headers=org.admin)
    base = f"/api/v1/proyectos/{p['id']}"
    r = cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("CP-1.pdf", pdf_escaneado(paginas)))], data={"rutas_relativas": ["CP-1.pdf"]}, headers=org.admin)
    assert r.json()[0]["unidad"] == "CP-1", r.text
    unidades = {u["identificador"]: u["id"] for u in cliente.get(f"{base}/inventario/unidades", headers=org.admin).json()["unidades"]}
    return p, base, director, f"{base}/hojas-control", unidades


def _tramites(d):
    return {t["orden"]: t for t in d["tramites"]}


def test_elaborar_sobre_lo_digitalizado_con_el_origen_de_cada_dato(cliente, org_a):
    p, base, director, hc, u = _listo(cliente, org_a)
    bandeja = cliente.get(hc, headers=org_a.admin).json()
    assert bandeja["cuenta"]["digitalizadas_sin_hoja"] == 1 and bandeja["cuenta"]["sin_hoja"] == 6
    d = cliente.post(f"{hc}/unidades/{u['CP-1']}", json={"imagenes_por_folio": 1}, headers=org_a.admin).json()
    t = _tramites(d)[1]
    assert (t["pagina_desde"], t["pagina_hasta"], t["folio_desde"], t["folio_hasta"]) == (1, 6, 1, 6)
    assert t["origen"]["folios"]["fuente"] == "calculado" and "páginas 1 a 6" in t["origen"]["folios"]["detalle"]
    assert d["tipos_documentales"] == ["Citación", "Acta"] and t["tipo_documental"] == ""  # dos tipos posibles: decide la persona
    assert any(e["campo"] == "tipo_documental" for e in d["validacion"]["errores"])
    meta = {m["campo"]: m for m in d["metadatos"]}
    assert meta["subserie"]["fuente"] == "clasificacion" and "TRD" in meta["subserie"]["detalle"] and meta["subserie"]["valor"].startswith("100-02.01")
    assert meta["oficina_productora"]["valor"] == "100 Dirección general"
    assert meta["nombre"]["fuente"] == "fuid" and "fila" in meta["nombre"]["detalle"]
    assert meta["folios"]["valor"] == 6 and meta["folios"]["alerta"] == "el FUID dice 10"  # manda lo contado, queda la diferencia
    # «Aquí empieza otro documento» en la página 4.
    d = cliente.post(f"{hc}/unidades/{u['CP-1']}/tramites/{t['id']}/dividir", json={"pagina": 4}, headers=org_a.admin).json()
    t1, t2 = _tramites(d)[1], _tramites(d)[2]
    assert (t1["folio_desde"], t1["folio_hasta"], t2["folio_desde"], t2["folio_hasta"]) == (1, 3, 4, 6)
    d = cliente.patch(f"{hc}/unidades/{u['CP-1']}/tramites/{t1['id']}", json={"fecha": "3/3/1990", "tipo_documental": "Citación", "detalle": "Citación a sesión ordinaria"}, headers=org_a.admin).json()
    d = cliente.patch(f"{hc}/unidades/{u['CP-1']}/tramites/{t2['id']}", json={"fecha": "julio de 1990", "tipo_documental": "Memorando"}, headers=org_a.admin).json()
    t1, t2 = _tramites(d)[1], _tramites(d)[2]
    assert (t1["fecha"], t2["fecha"], t2["fecha_texto"]) == ("1990-03-03", None, "1990-07")  # la fecha parcial no se inventa
    assert "de la lista de la TRD" in t1["origen"]["tipo_documental"]["detalle"] and "no está en la lista" in t2["origen"]["tipo_documental"]["detalle"]
    assert d["validacion"]["errores"] == [] and any("no está en la lista" in a for a in d["validacion"]["avisos"])
    assert {m["campo"]: m for m in d["metadatos"]}["fechas"]["valor"] == "1990-03-03 a 1990-07"
    # Recto y verso: dos imágenes por folio. La página 4 queda en el mismo folio que la 3: la continuidad lo detecta.
    d = cliente.put(f"{hc}/unidades/{u['CP-1']}/imagenes-por-folio", json={"valor": 2}, headers=org_a.admin).json()
    assert (_tramites(d)[1]["folio_hasta"], _tramites(d)[2]["folio_desde"]) == (2, 2)
    assert any("folios repetidos" in e["mensaje"] for e in d["validacion"]["errores"])
    d = cliente.put(f"{hc}/unidades/{u['CP-1']}/imagenes-por-folio", json={"valor": 1}, headers=org_a.admin).json()
    assert d["validacion"]["errores"] == []
    # Unir y volver a partir.
    d = cliente.post(f"{hc}/unidades/{u['CP-1']}/tramites/{t1['id']}/unir", headers=org_a.admin).json()
    assert len(d["tramites"]) == 1 and _tramites(d)[1]["pagina_hasta"] == 6 and _tramites(d)[1]["tipo_documental"] == "Citación"


def test_visor_de_paginas(cliente, org_a):
    p, base, director, hc, u = _listo(cliente, org_a, paginas=3)
    cliente.post(f"{hc}/unidades/{u['CP-1']}", json={}, headers=org_a.admin)
    d = cliente.get(f"{hc}/unidades/{u['CP-1']}", headers=org_a.admin).json()
    assert [x["n"] for x in d["paginas"]] == [1, 2, 3] and d["paginas"][0]["archivo"] == "CP-1.pdf"
    img = cliente.get(f"{hc}/unidades/{u['CP-1']}/paginas/2/imagen?ancho=400", headers=org_a.admin)
    assert img.status_code == 200 and img.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert cliente.get(f"{hc}/unidades/{u['CP-1']}/paginas/9/imagen", headers=org_a.admin).status_code == 404
    o = cliente.get(f"{hc}/unidades/{u['CP-1']}/paginas/1/original", headers=org_a.admin)
    assert o.status_code == 200 and o.content[:4] == b"%PDF" and o.headers["x-content-sha256"]


def test_verificar_tramite_por_tramite_devolver_y_expedir(cliente, org_a):
    p, base, director, hc, u = _listo(cliente, org_a)
    d = cliente.post(f"{hc}/unidades/{u['CP-1']}", json={}, headers=org_a.admin).json()
    t = _tramites(d)[1]
    assert cliente.post(f"{hc}/unidades/{u['CP-1']}/enviar", headers=org_a.admin).status_code == 422  # tipo vacío
    d = cliente.post(f"{hc}/unidades/{u['CP-1']}/tramites/{t['id']}/dividir", json={"pagina": 3}, headers=org_a.admin).json()
    for x in d["tramites"]:
        cliente.patch(f"{hc}/unidades/{u['CP-1']}/tramites/{x['id']}", json={"tipo_documental": "Acta", "fecha": "1990-05-10"}, headers=org_a.admin)
    d = cliente.post(f"{hc}/unidades/{u['CP-1']}/enviar", headers=org_a.admin).json()
    assert d["hoja"]["estado"] == "en_revision" and d["hoja"]["total_folios"] == 6
    t1, t2 = _tramites(d)[1], _tramites(d)[2]
    assert cliente.patch(f"{hc}/unidades/{u['CP-1']}/tramites/{t1['id']}", json={"detalle": "x"}, headers=org_a.admin).status_code == 422  # ya no se edita
    rv = f"{hc}/unidades/{u['CP-1']}/tramites"
    assert cliente.post(f"{rv}/{t1['id']}/revisar", json={"conforme": True}, headers=org_a.admin).status_code == 403  # quien elabora no verifica
    cliente.post(f"{rv}/{t1['id']}/revisar", json={"conforme": True}, headers=director)
    assert cliente.post(f"{rv}/{t2['id']}/revisar", json={"conforme": False}, headers=director).status_code == 422  # sin observación
    cliente.post(f"{rv}/{t2['id']}/revisar", json={"conforme": False, "observacion": "Es una citación, no un acta"}, headers=director)
    assert cliente.post(f"{hc}/unidades/{u['CP-1']}/verificar", headers=director).status_code == 422
    d = cliente.post(f"{hc}/unidades/{u['CP-1']}/devolver", json={"motivo": "Corregir el trámite 2"}, headers=director).json()
    assert d["hoja"]["estado"] == "devuelta" and _tramites(d)[2]["observacion_revision"] == "Es una citación, no un acta"
    cliente.patch(f"{rv}/{t2['id']}", json={"tipo_documental": "Citación"}, headers=org_a.admin)
    cliente.post(f"{hc}/unidades/{u['CP-1']}/enviar", headers=org_a.admin)
    for x in (t1, t2):
        cliente.post(f"{rv}/{x['id']}/revisar", json={"conforme": True}, headers=director)
    d = cliente.post(f"{hc}/unidades/{u['CP-1']}/verificar", headers=director).json()
    assert d["hoja"]["estado"] == "verificada"
    # Se expide en el formato de la entidad; sin plantilla vigente se dice.
    assert cliente.post(f"{hc}/unidades/{u['CP-1']}/expedir", headers=org_a.admin).status_code == 422
    pl = cliente.post("/api/v1/plantillas", json={"tipo": "hoja_control", "nombre": "Hoja de control de la entidad"}, headers=org_a.admin).json()
    formato = cliente.get("/api/v1/plantillas/tipos/hoja_control/base", headers=org_a.admin).content
    assert cliente.post(f"/api/v1/plantillas/{pl['id']}/versiones", files={"archivo": ("h.xlsx", formato)}, data={"motivo": "Formato de la entidad"}, headers=org_a.admin).status_code == 201
    e = cliente.post(f"{hc}/unidades/{u['CP-1']}/expedir", headers=org_a.admin)
    assert e.status_code == 201 and e.json()["elementos"] == 2
    hoja = openpyxl.load_workbook(io.BytesIO(cliente.get(f"{base}/entregables/{e.json()['expedicion_id']}/archivo", headers=org_a.admin).content)).active
    textos = [str(c.value) for f in hoja.iter_rows() for c in f if c.value is not None]
    assert "100 Dirección general" in textos and "Actas de comité directivo" in textos and "Citación" in textos
    assert any("Total de folios: 6" in x for x in textos) and any("LOS FOLIOS NO COINCIDEN" in x for x in textos)  # el FUID dice 10
    assert any("Verificó: Persona director@alfa.example.com" in x for x in textos)
    # Corregir una hoja verificada exige reabrirla con motivo.
    assert cliente.post(f"{hc}/unidades/{u['CP-1']}/reabrir", json={"motivo": "Se encontró un folio suelto"}, headers=director).json()["hoja"]["estado"] == "devuelta"


def test_importar_hojas_diligenciadas_en_excel(cliente, org_a):
    p, base, director, hc, u = _listo(cliente, org_a)
    libro = openpyxl.Workbook()
    h = libro.active
    h.title = "CP-2"
    h.append(["HOJA DE CONTROL"])
    h.append(["N°", "FECHA", "TIPO DOCUMENTAL", "FOLIO DESDE", "FOLIO HASTA", "OBSERVACIONES"])
    h.append([1, "10/02/1991", "Decreto - Decreto 15 de la dirección", 1, 12, ""])
    h.append([2, "S/F", "Soportes", 13, 20, "Folio 18 roto"])
    otra = libro.create_sheet("CP-99")
    otra.append(["N°", "FECHA", "TIPO DOCUMENTAL", "FOLIO DESDE", "FOLIO HASTA"])
    otra.append([1, "1991", "Decreto", 1, 2])
    salida = io.BytesIO()
    libro.save(salida)
    r = cliente.post(f"{hc}/importar", files={"archivo": ("hojas.xlsx", salida.getvalue())}, headers=org_a.admin).json()
    resultado = {x["pestana"]: x for x in r}
    assert resultado["CP-2"]["resultado"] == "importada" and resultado["CP-2"]["unidad"] == "CP-2"
    assert "no está en el inventario" in resultado["CP-99"]["resultado"]
    d = cliente.get(f"{hc}/unidades/{u['CP-2']}", headers=org_a.admin).json()
    t1, t2 = _tramites(d)[1], _tramites(d)[2]
    assert (t1["tipo_documental"], t1["detalle"], t1["fecha"], t1["folio_hasta"]) == ("Decreto", "Decreto 15 de la dirección", "1991-02-10", 12)
    assert t2["fecha_texto"] is None and t2["observaciones"] == "Folio 18 roto"  # S/F queda sin fecha
    assert "hojas.xlsx" in t1["origen"]["tipo_documental"]["detalle"] and "fila 3" in t1["origen"]["tipo_documental"]["detalle"]
    assert d["hoja"]["origen"] == "importada" and d["validacion"]["errores"] == []
    assert d["validacion"]["total_folios"] == 20  # el FUID dice 20: coincide


def test_hoja_sin_digitalizar_con_folios_a_mano(cliente, org_a):
    p, base, director, hc, u = _listo(cliente, org_a)
    d = cliente.post(f"{hc}/unidades/{u['CP-3']}", json={}, headers=org_a.admin).json()
    assert d["tramites"] == [] and d["hoja"]["origen"] == "manual"
    d = cliente.post(f"{hc}/unidades/{u['CP-3']}/tramites", headers=org_a.admin).json()
    t = d["tramites"][0]
    d = cliente.patch(f"{hc}/unidades/{u['CP-3']}/tramites/{t['id']}", json={"folio_desde": 1, "folio_hasta": 30, "tipo_documental": "Tutela"}, headers=org_a.admin).json()
    assert d["validacion"]["errores"] == [] and d["validacion"]["total_folios"] == 30
    d = cliente.post(f"{hc}/unidades/{u['CP-3']}/tramites", headers=org_a.admin).json()
    assert _tramites(d)[2]["folio_desde"] == 31


def test_permisos_y_aislamiento(cliente, org_a, org_b):
    p, base, director, hc, u = _listo(cliente, org_a)
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(hc, headers=consulta).status_code == 200
    assert cliente.post(f"{hc}/unidades/{u['CP-1']}", json={}, headers=consulta).status_code == 403
    assert cliente.post(f"{hc}/unidades/{u['CP-1']}", json={"imagenes_por_folio": 3}, headers=org_a.admin).status_code == 422
    cliente.post(f"{hc}/unidades/{u['CP-1']}", json={}, headers=org_a.admin)
    assert cliente.post(f"{hc}/unidades/{u['CP-1']}", json={}, headers=org_a.admin).status_code == 409
    assert cliente.get(f"{hc}/unidades/{u['CP-1']}/paginas/1/imagen", headers=org_b.admin).status_code == 404
