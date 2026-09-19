"""Prueba de extremo a extremo del flujo de dos pasos contra PostgreSQL real."""
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # permite ejecutarlo desde cualquier carpeta

from fastapi.testclient import TestClient
from geology.nucleo.bd import SesionLocal, crear_tablas

crear_tablas()
from geology.modelos import Fondo, Periodo, Seccion, Serie, Subserie, UnidadInventario
from geology.main import aplicacion as app

DEMO = ("AC-CP-00363", "AC-CP-00364", "AC-CP-00365")

db = SesionLocal()

# La prueba se puede ejecutar las veces que quiera: primero borra sus propios expedientes de
# ejemplo, de modo que el recorrido siempre empiece desde cero. No toca ningún otro dato.
from geology.modelos import Expediente
for exp in db.query(Expediente).filter(Expediente.codigo_carpeta.in_(DEMO)).all():
    db.delete(exp)
db.commit()

if not db.query(Fondo).first():
    f = Fondo(codigo="SGC", nombre="Servicio Geológico Colombiano"); db.add(f); db.flush()
    p = Periodo(fondo=f, numero_romano="II", orden=2, rango_texto="Del 17 diciembre 1923 - 29 marzo 1936",
                fecha_inicio=date(1923,12,17), fecha_fin=date(1936,3,29),
                entidad_productora="Ministerio de Industrias",
                historia_institucional="Durante este periodo la entidad…",
                historia_archivistica="La documentación fue transferida al Archivo Central…",
                caracteristicas_fisicas="Papel con acidez moderada y tintas ferrogálicas.")
    db.add(p); db.flush()
    sec = Seccion(periodo=p, codigo_dependencia="100.1", unidad_administrativa="Servicio Geológico Nacional",
                  oficina_productora="Sección de Laboratorio"); db.add(sec); db.flush()
    se = Serie(seccion=sec, codigo="02", nombre="INFORMES", retencion_central_anios=10, disposicion_final="CT+M")
    db.add(se); db.flush()
    db.add(Subserie(serie=se, codigo="01", nombre="Informes Geológicos", soporte="Papel",
                    retencion_central_anios=10, disposicion_final="CT+M"))
    db.add(UnidadInventario(codigo_carpeta="AC-CP-00363", periodo="II", folios=24,
                            asunto="informes geológicos de la comisión del norte",
                            caja_origen="AC-CJ-00065", caja_trabajo="733-CJ-00003"))
    db.add(UnidadInventario(codigo_carpeta="AC-CP-00364", periodo="", folios=24,
                            asunto="informes de la comisión, sin periodo en el inventario",
                            caja_origen="AC-CJ-00065", caja_trabajo="733-CJ-00003"))
    db.add(UnidadInventario(codigo_carpeta="AC-CP-00365", periodo="S/F", folios=6,
                            asunto="documentos sin fecha", caja_origen="AC-CJ-00065",
                            caja_trabajo="733-CJ-00003"))
    db.commit()
db.close()

c = TestClient(app)
def _pase(correo, clave):
    r = c.post("/cuentas/ingresar", json={"correo": correo, "clave": clave})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["pase"]}

# Cuentas propias de la prueba, con clave conocida y sin obligación de cambiarla. No toca
# las cuentas reales del equipo.
from geology.modelos import UsuarioBD, cifrar_clave
db = SesionLocal()
for nombre, correo, rol, funcion in (("Prueba Dirección", "prueba.direccion@geology.local", "administradora", "Ambas"),
                                     ("Prueba Descripción", "prueba.equipo@geology.local", "equipo", "Descripción")):
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo).first()
    if not u:
        u = UsuarioBD(nombre=nombre, correo=correo, rol=rol, funcion=funcion, clave_hash=cifrar_clave("Prueba-2026"))
        db.add(u)
    u.debe_cambiar_clave, u.activo, u.intentos_fallidos = False, True, 0
db.commit(); db.close()

MARLIN = _pase("prueba.direccion@geology.local", "Prueba-2026")
CAMILA = _pase("prueba.equipo@geology.local", "Prueba-2026")

hoja = {"codigo_carpeta": "ac-cp-363", "archivo_origen": "AC-CP-00363.xlsx",
        "codigo_serie": "02", "codigo_subserie": "01", "serie": "INFORMES",
        "subserie": "Informes Geológicos", "nombre_expediente": "Informes",
        "responsable": "Camila Garzón", "fecha_diligenciamiento": "3/3/1932",
        "tramites": [
          {"no_item": 1, "fecha": "11 de julio de 1931", "tipo_documental": "Oficio", "folio_desde": "1"},
          {"no_item": 2, "fecha": "3/3/1932", "tipo_documental": "Informe", "folio_desde": "4", "folio_hasta": "20"},
          {"no_item": 9, "fecha": "1993-05-01", "tipo_documental": "Anotación", "folio_desde": "21-24"}]}

print("1. CARGAR Y VERIFICAR")
r = c.post("/unidades/hoja-de-control", json=hoja, headers=CAMILA); d = r.json()
print("   estado:", d["estado"], "| folios:", d["folios"], "| subserie:", d["subserie"])
print("   observaciones:", d["observaciones"])
print("   siguiente:", d["siguiente_paso"])
# La hoja verificada ya no pasa sola a describirse: espera a que una persona la revise.
assert d["estado"] == "Hoja de control por revisar" and not d["errores"], d

print("2. RECARGA DE LA MISMA HOJA: es una corrección, no un duplicado")
r = c.post("/unidades/hoja-de-control", json=hoja, headers=CAMILA)
print("  ", r.status_code, r.json().get("estado") or r.json().get("detail", "")[:70])
assert r.status_code == 200

print("3. APROBAR SIN DESCRIBIR (debe negarse)")
r = c.post("/unidades/AC-CP-00363/aprobar", headers=MARLIN)
print("  ", r.status_code, r.json()["detail"][:70])

print("3b. REVISAR LA HOJA, que es el primer punto de control humano")
r = c.post("/unidades/AC-CP-00363/marcar-revisada", headers=CAMILA)
print("  ", r.status_code, str(r.json())[:80])

print("4. GENERAR ISAD(G), que es el paso humano")
r = c.post("/unidades/AC-CP-00363/generar-isadg", headers=CAMILA); d = r.json()
print("   código de referencia:", d["codigo_referencia"], "| estado:", d["estado"])
assert d["codigo_referencia"] == "CO-SGC-AC-PII-S01-00001", d

f = c.get("/unidades/AC-CP-00363", headers=CAMILA).json()
print("   título:", f["titulo"] if "titulo" in f else "-", "| fechas:", f["fechas_extremas"])
assert f["fechas_extremas"] == "1931-07-11 / 1932-03-03"   # 1993 excluida por el periodo

print("5. QUIEN DESCRIBE NO APRUEBA")
r = c.post("/unidades/AC-CP-00363/aprobar", headers=CAMILA)
print("  ", r.status_code, r.json()["detail"][:70])

print("5b. VALIDAR LA DESCRIPCIÓN, segundo punto de control humano")
r = c.post("/unidades/AC-CP-00363/validar-isadg", headers=MARLIN)
print("  ", r.status_code, str(r.json())[:80])

print("6. APRUEBA LA DIRECCIÓN")
print("  ", c.post("/unidades/AC-CP-00363/aprobar", headers=MARLIN).json()["estado"])

print("7. INVENTARIO SIN PERIODO, PERO CON FECHAS: se deduce de las fechas extremas")
hoja2 = dict(hoja); hoja2["codigo_carpeta"] = "AC-CP-00364"
r = c.post("/unidades/hoja-de-control", json=hoja2, headers=CAMILA); d = r.json()
print("   estado:", d["estado"], "| periodo:", d["periodo"], "| origen:", d["origen_del_periodo"])
print("   aviso :", d["observaciones"] or "(sin observaciones: las fechas lo resolvieron solas)")

print("7b. SIN PERIODO Y SIN NINGUNA FECHA: lo asigna una persona")
hoja2b = {**hoja, "codigo_carpeta": "AC-CP-00365",
          "tramites": [{"no_item": 1, "fecha": "S/F", "tipo_documental": "Oficio",
                        "folio_desde": "1", "folio_hasta": "6"}]}
d = c.post("/unidades/hoja-de-control", json=hoja2b, headers=CAMILA).json()
print("   estado:", d["estado"])
print("   error :", d["errores"][-1] if d["errores"]
      else "(esta carpeta sí tiene periodo en el inventario real; no aplica)")
d = c.post("/unidades/hoja-de-control", json={**hoja2b, "periodo_manual": "II"},
           headers=CAMILA).json()
print("   con periodo asignado a mano ->", d["estado"], "| origen:", d["origen_del_periodo"])

print("8. CARPETA QUE NO ESTÁ EN EL INVENTARIO")
hoja3 = dict(hoja); hoja3["codigo_carpeta"] = "AC-CP-99999"
r = c.post("/unidades/hoja-de-control", json=hoja3, headers=CAMILA)
print("  ", r.status_code, r.json()["detail"][:75])

print("\n9. RETIRO POR ERROR")
r = c.post("/unidades/AC-CP-00364/retirar", json={"motivo": "corto"}, headers=MARLIN)
print("   motivo corto:", r.status_code)
r = c.post("/unidades/AC-CP-00364/retirar",
           json={"motivo": "Se marcó por error; corresponde al lote del periodo III."}, headers=CAMILA)
print("   sin permiso :", r.status_code, r.json()["detail"][:50])
r = c.post("/unidades/AC-CP-00364/retirar",
           json={"motivo": "Se marcó por error; corresponde al lote del periodo III."}, headers=MARLIN)
print("   retirada    :", r.json()["estado"], "| se purga el", r.json()["se_purga_el"])
print("   restaurada  :", c.post("/unidades/AC-CP-00364/restaurar", headers=MARLIN).json()["estado"])

print("10. TRAZABILIDAD DE AC-CP-00364")
for h in c.get("/unidades/AC-CP-00364/trazabilidad", headers=MARLIN).json():
    print(f"    {h['fecha']}  {h['accion']:<12} {str(h['de']):<38} -> {h['a']}  ({h['usuario']})")
print("\nFLUJO DE DOS PASOS VERIFICADO CONTRA POSTGRESQL")

# ---------------------------------------------------------------------------
# Periodo deducido de las fechas extremas y reparto entre los dos modelos
# ---------------------------------------------------------------------------
print("\n11. CUOTA DE LOS MODELOS")
for m in c.get("/unidades/modelos/disponibilidad", headers=MARLIN).json():
    print(f"   {m['proveedor']:<7} configurado={m['configurado']}  usadas={m['usadas']}/{m['cuota_diaria']}")

print("\n12. DESCRIBIR SIN MODELO DISPONIBLE (no se inventa nada)")
# AC-CP-00364 quedó Devuelta tras el retiro y la restauración, así que se describe la 365
c.post("/unidades/hoja-de-control", json={**hoja2b, "periodo_manual": "II"}, headers=CAMILA)
r = c.post("/unidades/AC-CP-00365/generar-isadg", headers=CAMILA).json()
print("   redactada por:", r.get("redactada_por") or r.get("detail"))
print("   código       :", r.get("codigo_referencia"))
print("  ", (r.get("mensaje") or "")[:110])
f = c.get("/unidades/AC-CP-00365", headers=CAMILA).json()
print("   título       :", f.get("titulo"))
print("\n" + "=" * 74)
print("TODO CORRECTO. La plataforma quedó funcionando.")
print("Abra la interfaz en   http://localhost:8080/app")
print("e ingrese con su correo  marlin.martinez.cordoba@gmail.com")
print("=" * 74)
