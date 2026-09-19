"""
Revisa y repara el archivo .env cuando las llaves quedaron mal escritas.

POR QUÉ EXISTE. Pegando diez llaves a mano en un editor es facilísimo que a un renglón se
le coma la primera letra —«EMINI_API_KEY_4» en vez de «GEMINI_API_KEY_4»— y el resultado es
silencioso: la plataforma no encuentra esa variable, no avisa nada, y usted se queda con una
llave en lugar de ocho sin entender por qué. Eso pasó el 10 de septiembre de 2026 y costó
media jornada.

Este programa lee el archivo, reconoce las llaves POR SU VALOR —las de Claude empiezan por
sk-ant-, las de Gemini por AIza o AQ., las de ChatGPT por sk-— y comprueba que el nombre de
la variable sea el que corresponde. Cuando no lo es, lo corrige.

    docker compose exec servidor python scripts/revisar_llaves.py              solo mira y reporta
    docker compose exec servidor python scripts/revisar_llaves.py --arreglar   corrige el archivo

Nunca muestra una llave completa: solo el principio y el final, lo justo para reconocerla.
Antes de escribir nada deja una copia del archivo con la fecha, de modo que siempre se puede
volver atrás.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / ".env"

# Cómo se reconoce de quién es una llave, por lo que trae escrito al principio.
FIRMAS = (
    ("anthropic", ("sk-ant-",)),
    ("openai", ("sk-proj-", "sk-")),
    ("gemini", ("AIza", "AQ.")),
)
VARIABLE = {"anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY"}
MAXIMO_NUMERADAS = 30

_RENGLON = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$")


def de_quien_es(valor: str) -> str | None:
    """El proveedor al que pertenece una llave, por su prefijo."""
    limpio = valor.strip().strip('"').strip("'")
    for proveedor, prefijos in FIRMAS:
        if any(limpio.startswith(p) for p in prefijos):
            return proveedor
    return None


def tapada(valor: str) -> str:
    """La llave como se puede mostrar en pantalla sin regalarla."""
    v = valor.strip()
    return f"{v[:10]}…{v[-4:]}" if len(v) > 18 else "…"


def nombre_valido(nombre: str, proveedor: str) -> bool:
    base = VARIABLE[proveedor]
    if nombre == base:
        return True
    if not nombre.startswith(base + "_"):
        return False
    resto = nombre[len(base) + 1:]
    return resto.isdigit() and 1 <= int(resto) <= MAXIMO_NUMERADAS


def _apagar_repetidas_vacias(renglones: list[str]) -> int:
    """
    Comenta los renglones vacíos que repiten el nombre de una llave que sí tiene valor.

    HALLAZGO. Al corregir «PENAI_API_KEY» a «OPENAI_API_KEY» puede quedar más abajo otro
    «OPENAI_API_KEY=» vacío, de cuando se preparó el archivo. Y como al leer un archivo de
    configuración manda el ÚLTIMO renglón con ese nombre, el vacío borraba la llave buena
    sin decir nada. Por eso se apaga: no se borra, se comenta, y queda escrito por qué.
    """
    con_valor: set[str] = set()
    for renglon in renglones:
        if renglon.lstrip().startswith("#"):
            continue
        encontrado = _RENGLON.match(renglon)
        if encontrado and encontrado.group(2).strip():
            con_valor.add(encontrado.group(1).strip())

    apagados = 0
    for indice, renglon in enumerate(renglones):
        if renglon.lstrip().startswith("#"):
            continue
        encontrado = _RENGLON.match(renglon)
        if not encontrado:
            continue
        nombre, valor = encontrado.group(1).strip(), encontrado.group(2).strip()
        if not valor and nombre in con_valor:
            renglones[indice] = (f"# {renglon}    "
                                 "# repetía un nombre que ya tiene llave; lo desactivó "
                                 "revisar_llaves.py")
            apagados += 1
    return apagados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arreglar", action="store_true",
                        help="corrige el archivo en lugar de solo reportar")
    parser.add_argument("--archivo", default=str(ARCHIVO))
    argumentos = parser.parse_args()

    ruta = Path(argumentos.archivo)
    if not ruta.exists():
        print(f"No se encontró el archivo {ruta}.")
        print("Si está corriendo esto dentro de Docker, el archivo .env tiene que estar "
              "montado en el contenedor. Actualice docker-compose.yml y vuelva a levantar.")
        sys.exit(1)

    renglones = ruta.read_text(encoding="utf-8", errors="replace").splitlines()

    print("\nREVISIÓN DE LAS LLAVES DEL ARCHIVO .env\n" + "=" * 72)

    ocupados: dict[str, set[str]] = {p: set() for p in VARIABLE}
    hallazgos: list[tuple[int, str, str, str, str]] = []   # fila, nombre, proveedor, valor, nuevo
    vistas: dict[str, list[int]] = {}
    problemas = 0

    # Primera pasada: qué nombres ya están bien usados, para no pisarlos.
    for numero, renglon in enumerate(renglones, start=1):
        if renglon.lstrip().startswith("#"):
            continue
        encontrado = _RENGLON.match(renglon)
        if not encontrado:
            continue
        nombre, valor = encontrado.group(1).strip(), encontrado.group(2).strip()
        proveedor = de_quien_es(valor)
        if proveedor and nombre_valido(nombre, proveedor):
            ocupados[proveedor].add(nombre)

    # Segunda pasada: los que están mal escritos.
    for numero, renglon in enumerate(renglones, start=1):
        if renglon.lstrip().startswith("#"):
            continue
        encontrado = _RENGLON.match(renglon)
        if not encontrado:
            continue
        nombre, valor = encontrado.group(1).strip(), encontrado.group(2).strip()
        if not valor:
            continue
        proveedor = de_quien_es(valor)
        if not proveedor:
            continue

        vistas.setdefault(valor, []).append(numero)

        if nombre_valido(nombre, proveedor):
            continue

        # El nombre no sirve. Se le busca uno libre, conservando el número si lo traía.
        base = VARIABLE[proveedor]
        sufijo = re.search(r"_(\d+)$", nombre)
        candidatos = []
        if sufijo:
            candidatos.append(f"{base}_{int(sufijo.group(1))}")
        candidatos.append(base)
        candidatos += [f"{base}_{n}" for n in range(1, MAXIMO_NUMERADAS + 1)]
        nuevo = next((c for c in candidatos if c not in ocupados[proveedor]), None)
        if not nuevo:
            print(f"[ MAL ] Renglón {numero}: no queda un nombre libre para esta llave de "
                  f"{proveedor}. Suba MAXIMO_NUMERADAS.")
            problemas += 1
            continue
        ocupados[proveedor].add(nuevo)
        hallazgos.append((numero, nombre, proveedor, valor, nuevo))
        problemas += 1

    # Lo que se encontró
    for numero, nombre, proveedor, valor, nuevo in hallazgos:
        print(f"[ MAL ] Renglón {numero}: la variable se llama «{nombre}» y la llave es de "
              f"{proveedor} ({tapada(valor)}).")
        print(f"        Debería llamarse «{nuevo}». Mientras se llame así, no se usa.")

    repetidas = {v: filas for v, filas in vistas.items() if len(filas) > 1}
    for valor, filas in repetidas.items():
        print(f"[AVISO] La misma llave ({tapada(valor)}) está escrita en los renglones "
              f"{', '.join(str(f) for f in filas)}. Cuenta una sola vez.")

    print("-" * 72)
    for proveedor in ("anthropic", "gemini", "openai"):
        cuantas = len(ocupados[proveedor])
        print(f"  {proveedor:>10}: {cuantas} llave(s) quedarían en uso.")
    print("=" * 72)

    if not hallazgos:
        print("\nNo hay nombres mal escritos. Si aun así una llave no entra, el problema es "
              "de la llave misma, no del archivo: revísela con revisar_motor.py.\n")
        return

    if not argumentos.arreglar:
        print(f"\n{len(hallazgos)} renglón(es) por corregir. Para que los arregle, ejecute:\n")
        print("    docker compose exec servidor python scripts/revisar_llaves.py --arreglar\n")
        return

    respaldo = ruta.with_name(f".env.respaldo-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(ruta, respaldo)

    for numero, nombre, _proveedor, _valor, nuevo in hallazgos:
        viejo = renglones[numero - 1]
        renglones[numero - 1] = re.sub(rf"^(\s*){re.escape(nombre)}\s*=", rf"\1{nuevo}=", viejo)

    apagados = _apagar_repetidas_vacias(renglones)

    ruta.write_text("\n".join(renglones) + "\n", encoding="utf-8")
    print(f"\nCorregidos {len(hallazgos)} renglón(es).")
    if apagados:
        print(f"Y se desactivaron {apagados} renglón(es) vacío(s) que repetían un nombre ya "
              "usado. Sin eso, el renglón vacío de abajo borraba la llave de arriba.")
    print(f"La copia de antes quedó en {respaldo.name}, por si algo.")
    print("\nAhora reinicie para que los cambios entren:\n")
    print("    docker compose restart api worker")
    print("    docker compose exec procesador python scripts/revisar_motor.py\n")


if __name__ == "__main__":
    main()
