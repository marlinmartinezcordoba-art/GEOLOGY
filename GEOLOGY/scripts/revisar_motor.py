"""
Revisión de que todo lo necesario para levantar hojas de control está en su sitio.

Es lo que hay que correr ANTES de cargar el primer expediente. Comprueba en diez segundos lo
que hoy costó un día descubrir: que el trabajador ve el almacén, que hay llaves escritas, que
los proveedores responden con su lista de modelos y que el motor de imagen está instalado.

Uso dentro de Docker:
    docker compose exec procesador python scripts/revisar_motor.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BIEN, MAL, AVISO = "  BIEN ", "  MAL  ", " AVISO "


def linea(estado: str, texto: str, detalle: str = "") -> None:
    print(f"[{estado}] {texto}")
    if detalle:
        print(f"         {detalle}")


def main() -> None:
    print("\nREVISIÓN DEL MOTOR DE LEVANTAMIENTO\n" + "=" * 60)
    problemas = 0

    # 1. El almacén, que es donde vive lo digitalizado
    almacen = Path("deposito")
    if not almacen.exists():
        linea(MAL, "El trabajador NO ve la carpeta almacen.",
              "Falta montarla en docker-compose.yml, servicio procesador: ./deposito:/srv/geology/deposito")
        problemas += 1
    else:
        pdfs = list(almacen.glob("*.pdf")) + list(almacen.glob("*.PDF"))
        linea(BIEN, f"El almacén está a la vista, con {len(pdfs)} documento(s) portátil(es).")

    # 2. La base de datos
    try:
        from geology.nucleo.bd import verificar_conexion
        if verificar_conexion():
            linea(BIEN, "PostgreSQL responde.")
        else:
            linea(MAL, "PostgreSQL no responde."); problemas += 1
    except Exception as e:
        linea(MAL, f"PostgreSQL no responde: {e}"); problemas += 1

    # 3. Las llaves y los modelos
    from geology.dominio import catalogo

    # De dónde salieron las llaves. Sirve para saber, cuando falta alguna, si el problema
    # está en el archivo o en que Docker no la entregó al contenedor.
    del_archivo = catalogo._leer_archivo_env()
    cuantas_en_archivo = sum(1 for n in del_archivo if "API_KEY" in n)
    if cuantas_en_archivo:
        linea(BIEN, f"El archivo .env está a la vista, con {cuantas_en_archivo} llave(s) "
                    "escrita(s).")
    else:
        linea(AVISO, "El archivo .env no está montado en el contenedor.",
              "Sin él, las llaves solo llegan si Docker las entregó al crear el contenedor. "
              "Agregue  - ./.env:/srv/geology/.env  a los volúmenes en docker-compose.yml.")

    hay_llaves = False
    for proveedor in (catalogo.CLAUDE, catalogo.GEMINI, catalogo.OPENAI):
        llaves = catalogo.claves_de(proveedor)
        if not llaves:
            linea(AVISO, f"{proveedor}: sin llave escrita en el archivo .env.")
            continue
        hay_llaves = True
        modelos = catalogo.modelos_de(proveedor, forzar=True)
        if modelos:
            variable = catalogo._VARIABLE_LLAVE[proveedor]
            en_archivo = sum(1 for n in del_archivo
                             if n == variable or n.startswith(variable + "_"))
            detalle = ", ".join(modelos[:6]) + ("…" if len(modelos) > 6 else "")
            if en_archivo > len(llaves):
                linea(AVISO, f"{proveedor}: se usan {len(llaves)} llave(s) pero en el archivo "
                             f"hay {en_archivo}. Alguna está repetida o vacía.", detalle)
            else:
                linea(BIEN, f"{proveedor}: {len(llaves)} llave(s) y {len(modelos)} modelo(s).",
                      detalle)
        else:
            linea(MAL, f"{proveedor}: hay {len(llaves)} llave(s) pero el proveedor no devolvió "
                       "modelos. Puede estar mal escrita, sin saldo o sin conexión.")
            problemas += 1
    if not hay_llaves:
        linea(MAL, "No hay ninguna llave escrita. Sin llaves el modelo no puede leer nada.")
        problemas += 1

    # 4. La fila de motores
    try:
        from geology.dominio import lectores as mod
        fila = mod.motores()
        if fila:
            linea(BIEN, f"{len(fila)} motores listos para repartirse los expedientes.")
        else:
            linea(MAL, "No hay motores disponibles."); problemas += 1
    except Exception as e:
        linea(MAL, f"No se pudo armar la fila de motores: {e}"); problemas += 1

    # 5. El motor de imagen
    from geology.dominio import recepcion_tecnica as dig
    if dig.disponible():
        linea(BIEN, "El motor de imagen está instalado: matriz PDF/A y copia con texto buscable.")
    else:
        linea(AVISO, "Sin motor de imagen. Los expedientes se leen igual, pero no se generan "
                     "la matriz PDF/A ni la copia de consulta.")

    # 6. El intermediario de tareas
    try:
        from geology.nucleo.cola import celery_app
        celery_app.connection().ensure_connection(max_retries=1)
        linea(BIEN, "Redis responde: las tareas se pueden encolar.")
    except Exception as e:
        linea(MAL, f"Redis no responde: {e}"); problemas += 1

    print("=" * 60)
    if problemas:
        print(f"\n{problemas} problema(s). Resuélvalos antes de cargar expedientes: si carga "
              "ahora, las carpetas se van a quedar sin levantar.\n")
        sys.exit(1)
    print("\nTodo en orden. Puede cargar expedientes.\n")


if __name__ == "__main__":
    main()
