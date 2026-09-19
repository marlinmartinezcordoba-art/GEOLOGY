"""
Prueba de los expedientes partidos, la división automática de documentos de gran volumen y
el perfil de consulta de la entidad. Se corre contra la base real y limpia lo suyo.

    python scripts/prueba_partes_y_consulta.py
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("LEVANTAR_AL_CARGAR", "no")     # aquí no se lee con el modelo

import pikepdf
from fastapi.testclient import TestClient

from geology.nucleo.bd import SesionLocal, crear_tablas
crear_tablas()
from geology.main import aplicacion as app
from geology.modelos import Archivo, Expediente, UnidadInventario, UsuarioBD, cifrar_clave
from geology.dominio import division

DEMO = ("AC-CP-00370", "AC-CP-00371", "AC-CP-00372")


def pdf_de(paginas: int) -> bytes:
    with pikepdf.Pdf.new() as pdf:
        for _ in range(paginas):
            pdf.add_blank_page(page_size=(612, 792))
        m = io.BytesIO(); pdf.save(m, deterministic_id=True)
    return m.getvalue()


db = SesionLocal()
for exp in db.query(Expediente).filter(Expediente.codigo_carpeta.in_(DEMO)).all():
    for a in db.query(Archivo).filter(Archivo.codigo_carpeta == exp.codigo_carpeta).all():
        Path(a.ruta).unlink(missing_ok=True); db.delete(a)
    db.delete(exp)
for a in db.query(Archivo).filter(Archivo.codigo_carpeta.in_(DEMO)).all():
    Path(a.ruta).unlink(missing_ok=True); db.delete(a)
for codigo in DEMO:
    if not db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta == codigo).first():
        db.add(UnidadInventario(codigo_carpeta=codigo, periodo="II", folios=30, asunto="prueba",
                                caja_origen="AC-CJ-00065", caja_trabajo="733-CJ-00003"))
cuentas = (("Prueba Dirección", "prueba.direccion@geology.local", "administradora", "Ambas"),
           ("Prueba Equipo", "prueba.equipo@geology.local", "equipo", "Ambas"),
           ("Prueba Entidad", "prueba.entidad@geology.local", "entidad", "Ambas"))
for nombre, correo, rol, funcion in cuentas:
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo).first()
    if not u:
        u = UsuarioBD(nombre=nombre, correo=correo, rol=rol, funcion=funcion, clave_hash=cifrar_clave("Prueba-2026"))
        db.add(u)
    u.debe_cambiar_clave, u.activo, u.intentos_fallidos, u.rol = False, True, 0, rol
    u.ve_hojas_control, u.ve_isadg, u.ve_fuid, u.ve_imagenes = True, True, True, False
db.commit(); db.close()

c = TestClient(app)
def pase(correo):
    r = c.post("/cuentas/ingresar", json={"correo": correo, "clave": "Prueba-2026"}); r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["pase"]}
DIR, EQUIPO, ENTIDAD = (pase(x[1]) for x in cuentas)

def cargar(nombre, contenido, quien=EQUIPO):
    return c.post("/cargue/cargar", files={"archivo": (nombre, contenido, "application/pdf")}, headers=quien)

print("1. PARTES NOMBRADAS POR QUIEN DIGITALIZÓ: carpeta-00370- 1, - 2, - 3 (la 3 antes que la 2)")
for nombre, paginas in (("carpeta-00370- 1.pdf", 5), ("carpeta-00370- 3.pdf", 7), ("carpeta-00370- 2.pdf", 6)):
    r = cargar(nombre, pdf_de(paginas))
    d = r.json()
    print(f"   {nombre:<24} {r.status_code} fragmento={d.get('fragmento')} partes={d.get('partes_cargadas')} faltan={d.get('partes_faltantes')}")
    assert r.status_code == 200, d
partes = c.get("/cargue/partes/AC-CP-00370", headers=EQUIPO).json()
print("   orden de lectura:", [p["fragmento"] for p in partes])
assert [p["fragmento"] for p in partes] == [1, 2, 3]
assert division.faltantes([1, 3]) == [2] and division.faltantes([1, 2, 3]) == []

print("2. DOCUMENTO DE GRAN VOLUMEN: un solo archivo de 1.000 páginas para AC-CP-00371")
r = cargar("AC-CP-00371.pdf", pdf_de(1000)); d = r.json()
print(f"   {r.status_code} dividido={d.get('dividido_por_sistema')} partes={d.get('partes_cargadas')}")
print("   partes:", d.get("partes_del_sistema"))
assert r.status_code == 200 and d["dividido_por_sistema"] and d["partes_cargadas"] == 4, d
db = SesionLocal()
regs = db.query(Archivo).filter(Archivo.codigo_carpeta == "AC-CP-00371").order_by(Archivo.fragmento).all()
assert [(a.fragmento, a.pagina_inicial, a.pagina_final) for a in regs] == [(1, 1, 250), (2, 251, 500), (3, 501, 750), (4, 751, 1000)]
assert all(Path(a.ruta).exists() for a in regs)
total = sum(len(pikepdf.open(a.ruta).pages) for a in regs)
print("   páginas sumadas en las partes:", total)
assert total == 1000
print("   trazabilidad:", [t.accion for t in db.query(Expediente).filter_by(codigo_carpeta="AC-CP-00371").first().trazabilidad][-2:])
db.close()
print("2b. VOLVER A SUBIR UN ARCHIVO ENTERO CUANDO YA HAY PARTES: se rechaza para no leer dos veces")
r = cargar("AC-CP-00371.pdf", pdf_de(1000))
print("   ", r.status_code, r.json().get("detail", "")[:70])
assert r.status_code == 409
print("2c. UNA PARTE SUELTA CUANDO YA ESTÁ EL ENTERO: también se rechaza")
r = cargar("AC-CP-00370- 9.pdf", pdf_de(2)); assert r.status_code == 200      # 370 va por partes: entra
r = cargar("AC-CP-00372.pdf", pdf_de(10)); assert r.status_code == 200, r.text
r = cargar("AC-CP-00372- 2.pdf", pdf_de(4))
print("   ", r.status_code, r.json().get("detail", "")[:70]); assert r.status_code == 409
print("2d. EL MISMO ARCHIVO OTRA VEZ, con otro nombre: duplicado por la huella")
r = cargar("AC-CP-00370- 9.pdf", pdf_de(2))
print("   ", r.status_code, r.json().get("detail", "")[:70])

print("3. PERFIL DE LA ENTIDAD")
r = c.get("/consulta/yo", headers=ENTIDAD); print("   habilitaciones:", r.json())
assert r.json() == {"hojas_control": True, "isadg": True, "fuid": True, "imagenes": False}
r = c.get("/cargue/estado-de-cargas", headers=ENTIDAD); print("   /cargue/estado-de-cargas ->", r.status_code); assert r.status_code == 403
r = c.get("/unidades/modelos/disponibilidad", headers=ENTIDAD); print("   /unidades/modelos/disponibilidad ->", r.status_code); assert r.status_code == 403
r = c.get("/unidades/resumen", headers=ENTIDAD); print("   /unidades/resumen ->", r.status_code); assert r.status_code == 403
r = c.get("/instrumentos/resumen", headers=ENTIDAD); print("   /instrumentos/resumen ->", r.status_code); assert r.status_code == 403
r = cargar("AC-CP-00370.pdf", pdf_de(2), ENTIDAD); print("   cargar ->", r.status_code)
assert r.status_code == 403
yo = c.get("/cuentas/yo", headers=ENTIDAD).json(); print("   pestañas:", yo["pestanas"])
assert yo["pestanas"] == ["consulta"]
r = c.get("/consulta/unidades?buscar=370", headers=ENTIDAD); print("   unidades publicadas con 370:", len(r.json()), "(la hoja aún no está revisada: no se publica)")
assert r.json() == []
r = c.get("/consulta/ver/AC-CP-00370", headers=ENTIDAD); print("   ver imágenes sin habilitar ->", r.status_code)
assert r.status_code == 403
print("   la dirección habilita las imágenes y apaga el FUID…")
r = c.put("/cuentas/prueba.entidad@geology.local/habilitaciones", json={"imagenes": True, "fuid": False}, headers=DIR)
assert r.status_code == 200, r.text
print("   ahora:", c.get("/consulta/yo", headers=ENTIDAD).json())
r = c.get("/consulta/fuid", headers=ENTIDAD); print("   fuid apagado ->", r.status_code); assert r.status_code == 403
r = c.put("/cuentas/prueba.entidad@geology.local/habilitaciones", json={"imagenes": True}, headers=EQUIPO)
print("   el equipo no administra habilitaciones ->", r.status_code); assert r.status_code == 403
r = c.get("/consulta/resumen", headers=ENTIDAD); print("   resumen:", {k: v for k, v in r.json().items() if k != 'cajas' and k != 'periodos'})
print("   (una carpeta se publica a la entidad cuando su hoja está revisada; FUID cuando está en caja definitiva)")

print("4. CUENTAS: crear una cuenta de la entidad desde la dirección")
db = SesionLocal()
for u in db.query(UsuarioBD).filter(UsuarioBD.correo == "nueva.entidad@sgc.gov.co").all():
    db.delete(u)
db.commit(); db.close()
r = c.post("/cuentas/crear", json={"nombre": "Supervisión SGC", "correo": "nueva.entidad@sgc.gov.co", "rol": "entidad", "cargo": "Supervisión"}, headers=DIR)
print("   ", r.status_code, r.json().get("cuenta", {}).get("pestanas"), "clave provisional entregada:", bool(r.json().get("clave_provisional")))
assert r.status_code == 200, r.text

print("\nTODO CORRECTO: partes en orden, división automática y perfil de la entidad.")
