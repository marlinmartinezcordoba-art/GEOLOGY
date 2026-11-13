"""M24 · Productividad con el diseño de Power BI: importar, tablero con las fórmulas del diseño, registro diario,
base de cajas (procesadas y pendientes), conteo automático desde ARCA y llaves de lectura para Power BI.

Todo con datos ficticios: frentes F1 y F2 de una entidad inventada.
"""

import io
from datetime import date, timedelta

import openpyxl
from conftest import agregar_usuario, proyecto_basico
from fabricas import fuid_xlsx

INICIO = date(2030, 1, 7)


def _libro() -> bytes:
    libro = openpyxl.Workbook()
    libro.remove(libro.active)

    def hoja(nombre, encabezado, filas):
        h = libro.create_sheet(nombre)
        h.append(encabezado)
        for f in filas:
            h.append(f)

    hoja("dFrentes", ["Cod_Frente", "Frente", "Sede", "Unidad_Avance", "Volumen_Total", "Actividad_Avance", "Fecha_Inicio", "Fecha_Fin"], [
        ["F1", "Inventario de prueba", "Sede ficticia", "expedientes", 3, "F1-01 · Inventario", INICIO, INICIO + timedelta(days=9)],
        ["F2", "Organización de prueba", "Sede ficticia", "cajas", 10, "F2-02 · Organización", INICIO, INICIO + timedelta(days=9)],
    ])
    hoja("dActividades", ["Actividad_Clave", "Cod_Frente", "Orden", "Actividad", "Unidad", "Rol", "Cuenta_Avance", "Fuente_Automatica"], [
        ["F1-01 · Inventario", "F1", 1, "Inventario", "expedientes", "Archivista", "Sí", "expedientes_inventariados"],
        ["F2-01 · Limpieza", "F2", 1, "Limpieza", "cajas", "Auxiliar", "No", None],
        ["F2-02 · Organización", "F2", 2, "Organización", "cajas", "Archivista", "Sí", None],
    ])
    hoja("dTurnos", ["Turno", "Horario", "Jornada"], [["A", "06:00 – 14:00", "Mañana"], ["B", "14:00 – 22:00", "Tarde"], ["C", "22:00 – 06:00", "Noche"]])
    hoja("dMetas", ["Clave", "Actividad_Clave", "Turno", "Personas_Plan", "Meta_Turno", "Meta_Persona"], [
        [None, "F2-02 · Organización", "A", 2, 1, None], [None, "F2-02 · Organización", "B", 2, 1, None],
    ])
    hoja("dCalendario", ["Fecha", "Anio", "Mes", "Nombre_Mes", "Semana_ISO", "Dia_Semana", "Operativo", "Fase", "Fecha_Entrega_Corte", "Es_Dia_Entrega"],
         [[INICIO + timedelta(days=i), None, None, None, None, None, "Sí", "Producción", None, "No"] for i in range(10)])
    hoja("Registro_Produccion", ["Fecha", "Turno", "Actividad", "Lote", "Caja_Desde", "Caja_Hasta", "Cantidad", "Personas_Presentes", "Horas_Efectivas", "Supervisor", "Observaciones"], [
        [INICIO, "A", "F2-01 · Limpieza", "L1", "C-0001", "C-0005", 5, 2, 8, "Supervisor ficticio", ""],
        [INICIO, "A", "F2-02 · Organización", "L1", "C-0001", "C-0003", 3, 2, 8, "Supervisor ficticio", ""],
        [INICIO, "B", "F2-02 · Organización", "L1", "", "", 1, 2, 8, "Supervisor ficticio", "FILA DE EJEMPLO: bórrela"],
    ])
    hoja("Registro_Calidad", ["Fecha", "Cod_Frente", "Lote", "Unidad_Inspeccion", "Tamano_Lote", "Muestra", "Criticos", "Mayores", "Menores", "Limitaciones_Original", "Resultado", "Analista", "Observaciones"], [
        [INICIO, "F2", "L1", "cajas", 3, 1, 1, 0, 2, 0, "Rechazado", "Analista ficticio", ""],
    ])
    hoja("Registro_Novedades", ["Fecha", "Turno", "Cod_Frente", "Lote", "Caja", "Tipo_Novedad", "Descripcion", "Accion_Tomada", "Responsable", "Estado", "Fecha_Cierre"], [
        [INICIO, "A", "F2", "L1", "C-0002", "Deterioro físico", "Humedad", "Se separó", "Persona ficticia", "Abierta", None],
    ])
    hoja("Registro_Entregas", ["Fecha_Entrega", "Cod_Frente", "Lote", "Cantidad", "Unidad", "Numero_Acta", "Estado_Entrega", "Fecha_Aceptacion", "Observaciones"], [
        [INICIO, "F2", "L1", 2, "cajas", "ACTA-1", "Aceptado", INICIO, ""],
    ])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _preparar(cliente, org):
    p = proyecto_basico(cliente, org)
    base = f"/api/v1/proyectos/{p['id']}/productividad"
    r = cliente.post(f"{base}/libro", files={"archivo": ("productividad.xlsx", _libro())}, headers=org.admin)
    assert r.status_code == 200, r.text
    return p, base, {x["hoja"]: x for x in r.json()}


def test_plantilla_vacia_con_el_diseno(cliente, org_a):
    p = proyecto_basico(cliente, org_a)
    r = cliente.get(f"/api/v1/proyectos/{p['id']}/productividad/plantilla", headers=org_a.admin)
    libro = openpyxl.load_workbook(io.BytesIO(r.content))
    assert {"dFrentes", "dActividades", "dMetas", "dTurnos", "dCalendario", "dPersonal", "Registro_Produccion", "Registro_Calidad", "Listas"} <= set(libro.sheetnames)
    assert libro["dFrentes"].max_row == 1 and libro["Registro_Produccion"].max_row == 1  # solo encabezados: ningún dato


def test_importar_reemplaza_configuracion_y_agrega_registros_sin_duplicar(cliente, org_a):
    p, base, reporte = _preparar(cliente, org_a)
    assert reporte["dFrentes"]["accion"] == "reemplazada" and reporte["dFrentes"]["filas"] == 2
    assert reporte["Registro_Produccion"]["filas"] == 2 and reporte["Registro_Produccion"]["omitidas"] == 1  # la fila de ejemplo no entra
    otra = {x["hoja"]: x for x in cliente.post(f"{base}/libro", files={"archivo": ("p.xlsx", _libro())}, headers=org_a.admin).json()}
    assert otra["Registro_Produccion"]["filas"] == 0 and otra["Registro_Produccion"]["omitidas"] == 3


def test_tablero_con_las_formulas_del_diseno(cliente, org_a):
    _, base, _ = _preparar(cliente, org_a)
    t = cliente.get(f"{base}/tablero", headers=org_a.admin).json()
    assert t["fecha_corte"] == INICIO.isoformat()  # la última fecha con producción
    f2 = next(f for f in t["frentes"] if f["Frente"] == "F2")
    assert f2["Acumulado"] == 3 and f2["Meta_Diaria"] == 2 and f2["Producido_Fecha_Corte"] == 3
    assert f2["Dias_Operativos_Restantes"] == 9 and round(f2["Ritmo_Requerido_Dia"], 4) == round(7 / 9, 4)
    assert f2["Estado"] == "En ritmo" and f2["Pct_Cumplimiento_Dia"] == 1.5
    cal = next(c for c in t["calidad"] if c["Frente"] == "F2")
    assert cal["Lotes_Rechazados"] == 1 and cal["Defectos_Criticos"] == 1 and cal["Novedades_Abiertas"] == 1 and cal["Cantidad_Aceptada"] == 2
    turnos = next(x for x in t["por_turno"] if x["Frente"] == "F2")["turnos"]
    assert turnos[0] == {"Turno": "A", "Producido": 3, "Meta": 1}
    # Si se va quedando atrás, el estado cambia según la regla del 15 %.
    tarde = cliente.get(f"{base}/tablero?fecha_corte={(INICIO + timedelta(days=8)).isoformat()}", headers=org_a.admin).json()
    assert next(f for f in tarde["frentes"] if f["Frente"] == "F2")["Estado"] == "En riesgo"
    assert next(f for f in tarde["frentes"] if f["Frente"] == "F1")["Estado"] == "En riesgo"


def test_lo_que_hace_arca_se_cuenta_solo(cliente, org_a):
    p, base, _ = _preparar(cliente, org_a)
    inv = f"/api/v1/proyectos/{p['id']}/inventario"
    lote = cliente.post(f"{inv}/lotes", files={"archivo": ("fuid.xlsx", fuid_xlsx([
        [1, "CP-1", "1", "Expediente ficticio uno", "2001", "2002", "C-0001", "1", "", "", 10, "Papel", ""],
        [2, "CP-2", "1", "Expediente ficticio dos", "2001", "2002", "C-0001", "2", "", "", 10, "Papel", ""],
        [3, "CP-3", "1", "Expediente ficticio tres", "2001", "2002", "C-0002", "1", "", "", 10, "Papel", ""],
    ]))}, headers=org_a.admin).json()
    cliente.post(f"{inv}/lotes/{lote['id']}/integrar", json={}, headers=org_a.admin)
    filas = cliente.get(f"{base}/tablas/fProduccion", headers=org_a.admin).json()
    automaticas = [f for f in filas if f["Origen"] == "automatico"]
    assert sum(f["Cantidad"] for f in automaticas) == 3 and automaticas[0]["Actividad"] == "F1-01 · Inventario"
    f1 = next(f for f in cliente.get(f"{base}/tablero", headers=org_a.admin).json()["frentes"] if f["Frente"] == "F1")
    assert f1["Acumulado"] == 3 and f1["Estado"] == "Terminado"
    # La base de cajas también puede salir del FUID.
    r = cliente.post(f"{base}/cajas/desde-fuid?frente=F2", headers=org_a.admin).json()
    assert r["nuevas"] == 2
    cajas = {c["Caja"]: c for c in cliente.get(f"{base}/cajas", headers=org_a.admin).json()["cajas"]}
    assert cajas["C-0001"]["Carpetas"] == 2 and cajas["C-0001"]["Estado"] == "procesada"


def test_registro_diario_desde_el_formulario(cliente, org_a):
    _, base, _ = _preparar(cliente, org_a)
    _, equipo = agregar_usuario(cliente, org_a, "equipo@alfa.example.com", "Equipo operativo")
    malo = cliente.post(f"{base}/registros/fProduccion", json={"Fecha": INICIO.isoformat(), "Turno": "A", "Actividad": "No existe", "Cantidad": 1}, headers=equipo)
    assert malo.status_code == 422 and "no está configurada" in malo.json()["detail"]
    r = cliente.post(f"{base}/registros/fProduccion", json={"Fecha": INICIO.isoformat(), "Turno": "B", "Actividad": "F2-02 · Organización", "Caja_Desde": "C-0004", "Caja_Hasta": "C-0004", "Cantidad": 1}, headers=equipo)
    assert r.status_code == 201 and r.json()["Origen"] == "formulario"
    assert next(f for f in cliente.get(f"{base}/tablero", headers=equipo).json()["frentes"] if f["Frente"] == "F2")["Acumulado"] == 4
    assert cliente.post(f"{base}/registros/fCalidad", json={"Fecha": INICIO.isoformat(), "Cod_Frente": "F2", "Resultado": "Excelente"}, headers=equipo).status_code == 422
    assert cliente.post(f"{base}/libro", files={"archivo": ("p.xlsx", _libro())}, headers=equipo).status_code == 403  # el equipo no configura


def test_base_de_cajas_procesadas_y_pendientes(cliente, org_a):
    _, base, _ = _preparar(cliente, org_a)
    listado = "Caja;Carpetas;Cod_Frente;Ubicacion\n" + "\n".join(f"C-{i};{i};F2;Estante {i}" for i in (7, 6, 5, 4, 3, 2, 1))
    r = cliente.post(f"{base}/cajas/listado", files={"archivo": ("cajas.csv", listado.encode())}, headers=org_a.admin).json()
    assert r["nuevas"] == 7
    datos = cliente.get(f"{base}/cajas", headers=org_a.admin).json()
    assert [c["Caja"] for c in datos["cajas"]] == [f"C-{i}" for i in range(1, 8)]  # orden natural, no alfabético
    estados = {c["Caja"]: c["Estado"] for c in datos["cajas"]}
    assert [estados[f"C-{i}"] for i in range(1, 8)] == ["procesada"] * 3 + ["en_proceso"] * 2 + ["pendiente"] * 2
    resumen = next(x for x in datos["resumen"] if x["Cod_Frente"] == "F2")
    assert resumen == {"Cod_Frente": "F2", "total": 7, "procesada": 3, "en_proceso": 2, "pendiente": 2, "carpetas": 28, "carpetas_procesadas": 6}
    pendientes = cliente.get(f"{base}/cajas?estado=pendiente", headers=org_a.admin).json()["cajas"]
    assert [c["Caja"] for c in pendientes] == ["C-6", "C-7"] and pendientes[0]["Ubicacion"] == "Estante 6"
    assert cliente.get(f"{base}/cajas?q=c 4", headers=org_a.admin).json()["cajas"][0]["Actividades_Pendientes"] == ["F2-02 · Organización"]


def test_power_bi_con_llave_de_solo_lectura(cliente, operador, org_a):
    p, base, _ = _preparar(cliente, org_a)
    r = cliente.post(f"{base}/claves", json={"nombre": "Power BI de la dirección"}, headers=org_a.admin)
    assert r.status_code == 201
    token, clave_id = r.json()["token"], r.json()["clave"]["id"]
    pbi = {"Authorization": f"Bearer {token}"}
    assert "Tablero" in cliente.get("/api/v1/powerbi/tablas", headers=pbi).json()["tablas"]
    tablero = cliente.get("/api/v1/powerbi/Tablero", headers=pbi).json()
    assert {f["Frente"] for f in tablero} == {"F1", "F2"}
    csv = cliente.get("/api/v1/powerbi/fProduccion?formato=csv", headers=pbi)
    assert csv.headers["content-type"].startswith("text/csv") and csv.text.startswith("Fecha,Turno,Actividad")
    assert cliente.get("/api/v1/powerbi/dCalendario", headers=pbi).json()[0]["Dia_Semana"] == "Lunes"
    assert cliente.get("/api/v1/powerbi/Tablero", headers={"Authorization": "Bearer arca_pbi_inventada"}).status_code == 401
    assert cliente.get("/api/v1/powerbi/Tablero", headers=org_a.admin).status_code == 401  # una sesión de usuario no sirve aquí
    cliente.post(f"/api/v1/plataforma/organizaciones/{org_a.id}/suspender", json={"motivo": "Prueba de suspensión"}, headers=operador)
    assert cliente.get("/api/v1/powerbi/Tablero", headers=pbi).status_code == 403
    cliente.post(f"/api/v1/plataforma/organizaciones/{org_a.id}/reactivar", json={"motivo": "Fin de la prueba"}, headers=operador)
    cliente.post(f"{base}/claves/{clave_id}/revocar", json={"motivo": "Rotación de llaves"}, headers=org_a.admin)
    assert cliente.get("/api/v1/powerbi/Tablero", headers=pbi).status_code == 401


def test_permisos_y_aislamiento(cliente, org_a, org_b):
    p, base, _ = _preparar(cliente, org_a)
    _, entidad = agregar_usuario(cliente, org_a, "cliente@entidad.example.com", "Entidad cliente", proyectos=[p["id"]])
    assert cliente.get(f"{base}/tablero", headers=entidad).status_code == 200  # la entidad ve el avance
    assert cliente.post(f"{base}/registros/fProduccion", json={}, headers=entidad).status_code == 403
    assert cliente.get(f"{base}/tablero", headers=org_b.admin).status_code == 404
