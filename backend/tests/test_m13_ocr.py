"""M13 · OCR local (Tesseract) y propuesta de la hoja de control desde el texto leído. Documentos ficticios."""

import pytest
from fabricas import pdf_con_texto
from test_m04_clasificacion import FILAS, _escenario, _trd

from arca.modulos.m13_ocr import lector
from arca.modulos.m13_ocr.propuestas import corregir, proponer

requiere_tesseract = pytest.mark.skipif(not lector.disponible() or "spa" not in lector.idiomas(), reason="Tesseract con español no está instalado")

PAGINAS = [
    ["ENTIDAD FICTICIA NACIONAL", "CITACIÓN N.º 012", "Ciudad Ficticia, 3 de febrero de 2020", "Se cita a los miembros del comité directivo"],
    ["ENTIDAD FICTICIA NACIONAL", "CITACIÓN N.º 012 (anexo)", "Orden del día", "1. Verificación del quórum"],
    ["ENTIDAD FICTICIA NACIONAL", "ACTA N.º 005", "Comité directivo, 10 de febrero de 2020", "Radicado No. 2020-00123"],
    ["ENTIDAD FICTICIA NACIONAL", "ACTA N.º 005 (continuación)", "Se aprueba el informe de gestión."],
]


def _pagina(n, *lineas, conf=92):
    return {"n": n, "confianza": conf, "lineas": [[x, conf] for x in lineas]}


def test_propuesta_desde_el_texto_sin_tesseract():
    """Las reglas del analizador, sin depender del OCR."""
    docs = proponer([_pagina(i + 1, *p) for i, p in enumerate(PAGINAS)] + [_pagina(5, "ENTIDAD FICTICIA NACIONAL", "Memorando interno", "Asunto: entrega de archivo", conf=55)],
                    ["Citación", "Acta"])
    assert [(d.pagina_desde, d.pagina_hasta, d.tipo) for d in docs] == [(1, 2, "Citación"), (3, 4, "Acta"), (5, 5, "Memorando")]
    assert (docs[0].fecha, docs[1].fecha, docs[1].radicado) == ("2020-02-03", "2020-02-10", "2020-00123")
    assert docs[0].tipo_en_trd and not docs[2].tipo_en_trd and docs[2].confianza == "baja"
    assert docs[1].evidencias["fecha"].pagina == 3 and "10 de febrero" in docs[1].evidencias["fecha"].fragmento
    assert corregir("ACTA N.2 005") == "ACTA N.º 005" and corregir("Página 2 de 3") == "Página 2 de 3"
    # «Anexo» en el cuerpo no es una marca de continuación: solo cuenta junto al título.
    docs = proponer([_pagina(1, "ENTIDAD", "DECRETO N.º 015", "Texto del decreto"), _pagina(2, "ENTIDAD", "SOPORTES DEL DECRETO N.º 015", "fecha", "Anexo técnico del plan")],
                    ["Decreto", "Soportes"])
    assert [d.tipo for d in docs] == ["Decreto", "Soportes"]
    # Sin título reconocible no se parte: la página sigue en el documento anterior.
    assert len(proponer([_pagina(1, "CITACIÓN"), _pagina(2, "texto corrido sin título", "otra línea")], [])) == 1


def _listo(cliente, org):
    p, url, director, cla = _escenario(cliente, org, FILAS)
    _trd(cliente, org, director, url)
    cliente.post(f"{cla}/proponer", headers=org.admin)
    base = f"/api/v1/proyectos/{p['id']}"
    cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("CP-1.pdf", pdf_con_texto(PAGINAS)))], data={"rutas_relativas": ["CP-1.pdf"]}, headers=org.admin)
    unidades = {u["identificador"]: u["id"] for u in cliente.get(f"{base}/inventario/unidades", headers=org.admin).json()["unidades"]}
    return base, director, unidades


@requiere_tesseract
def test_ocr_lee_por_tandas_y_guarda_el_texto(cliente, org_a):
    base, _, u = _listo(cliente, org_a)
    ocr = f"{base}/ocr"
    assert cliente.get(f"{ocr}/resumen", headers=org_a.admin).json()["pendientes"] == 4
    r = cliente.post(f"{ocr}/unidades/{u['CP-1']}/leer", json={"limite": 3}, headers=org_a.admin).json()
    assert (r["procesadas"], r["pendientes"]) == (3, 1) and r["motor"].startswith("tesseract")
    r = cliente.post(f"{ocr}/unidades/{u['CP-1']}/leer", json={}, headers=org_a.admin).json()
    assert (r["procesadas"], r["pendientes"]) == (1, 0)
    assert cliente.post(f"{ocr}/unidades/{u['CP-1']}/leer", json={}, headers=org_a.admin).json()["procesadas"] == 0  # no se relee
    textos = cliente.get(f"{ocr}/unidades/{u['CP-1']}", headers=org_a.admin).json()
    assert textos[2]["estado"] == "leida" and "ACTA" in textos[2]["texto"] and textos[2]["confianza"] > 70
    resumen = cliente.get(f"{ocr}/resumen", headers=org_a.admin).json()
    assert (resumen["leidas"], resumen["pendientes"]) == (4, 0) and resumen["confianza_media"] > 70
    hallado = cliente.get(f"{ocr}/buscar", params={"q": "quórum"}, headers=org_a.admin).json()
    assert hallado and hallado[0]["identificador"] == "CP-1" and "quórum" in hallado[0]["fragmento"]


@requiere_tesseract
def test_hoja_de_control_propuesta_por_ocr_y_confirmada(cliente, org_a):
    base, director, u = _listo(cliente, org_a)
    hc = f"{base}/hojas-control/unidades/{u['CP-1']}"
    cliente.post(hc, json={}, headers=org_a.admin)
    assert cliente.post(f"{hc}/proponer-ocr", json={}, headers=org_a.admin).status_code == 422  # primero el OCR
    cliente.post(f"{base}/ocr/unidades/{u['CP-1']}/leer", json={}, headers=org_a.admin)
    d = cliente.post(f"{hc}/proponer-ocr", json={}, headers=org_a.admin).json()
    t = {x["orden"]: x for x in d["tramites"]}
    assert [(x["pagina_desde"], x["pagina_hasta"], x["tipo_documental"]) for x in t.values()] == [(1, 2, "Citación"), (3, 4, "Acta")]
    assert (t[1]["fecha"], t[2]["fecha"], t[2]["no_radicado"]) == ("2020-02-03", "2020-02-10", "2020-00123")
    assert t[2]["origen"]["fecha"]["fuente"] == "ocr" and "página 3" in t[2]["origen"]["fecha"]["detalle"]
    assert "N.º 005" in t[2]["detalle"]
    # Lo propuesto no se envía sin confirmar.
    assert sum(1 for e in d["validacion"]["errores"] if e["campo"] == "ocr") == 2
    assert cliente.post(f"{hc}/enviar", headers=org_a.admin).status_code == 422
    # Corregir un dato lo vuelve de la persona; confirmar acepta el resto conservando de dónde vino.
    d = cliente.patch(f"{hc}/tramites/{t[1]['id']}", json={"detalle": "Citación n.º 012 a sesión del comité"}, headers=org_a.admin).json()
    for x in d["tramites"]:
        d = cliente.post(f"{hc}/tramites/{x['id']}/confirmar", headers=org_a.admin).json()
    t = {x["orden"]: x for x in d["tramites"]}
    assert t[2]["origen"]["fecha"]["fuente"] == "persona" and "propuesto por OCR" in t[2]["origen"]["fecha"]["detalle"]
    assert t[1]["origen"]["detalle"]["detalle"].startswith("escrito por")
    assert d["validacion"]["errores"] == []
    assert cliente.post(f"{hc}/enviar", headers=org_a.admin).json()["hoja"]["estado"] == "en_revision"
    # Una hoja ya trabajada no se reemplaza sin confirmarlo.
    cliente.post(f"{hc}/devolver", json={"motivo": "Revisar fechas"}, headers=director)
    assert cliente.post(f"{hc}/proponer-ocr", json={}, headers=org_a.admin).status_code == 409
    assert cliente.post(f"{hc}/proponer-ocr", json={"reemplazar": True}, headers=org_a.admin).status_code == 200


def test_permisos_del_ocr(cliente, org_a, org_b):
    from conftest import agregar_usuario

    base, _, u = _listo(cliente, org_a)
    _, consulta = agregar_usuario(cliente, org_a, "consulta@alfa.example.com", "Consulta y auditoría")
    assert cliente.get(f"{base}/ocr/resumen", headers=consulta).status_code == 200
    assert cliente.post(f"{base}/ocr/unidades/{u['CP-1']}/leer", json={}, headers=consulta).status_code == 403
    assert cliente.post(f"{base}/ocr/leer", headers=consulta).status_code == 403
    assert cliente.get(f"{base}/ocr/unidades/{u['CP-1']}", headers=org_b.admin).status_code == 404
