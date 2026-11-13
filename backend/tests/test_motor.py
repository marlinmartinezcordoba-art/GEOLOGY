"""Motor archivístico reutilizado de GEOLOGY: sus reglas funcionan dentro de ARCA y no dependen de ningún contrato."""

import ast
import doctest
import importlib
import pkgutil
from pathlib import Path

import pytest

import arca
import arca.motor
from arca.motor import codigos, fechas, folios, instrucciones, lectores

MODULOS = [m.name for m in pkgutil.walk_packages(arca.motor.__path__, prefix="")]


@pytest.mark.parametrize("nombre", MODULOS)
def test_cada_modulo_importa_y_pasa_sus_ejemplos(nombre):
    modulo = importlib.import_module(f"arca.motor.{nombre}")
    assert "Geológico" not in (modulo.__doc__ or "")
    fallas, _ = doctest.testmod(modulo, verbose=False)
    assert fallas == 0


def test_fechas_y_folios():
    assert fechas.normalizar_fecha("11 de julio de 1931").texto == "1931-07-11"
    assert fechas.normalizar_fecha("S/F").texto is None
    tramites = [folios.Tramite(no_item=1, tipo_documental="Oficio", folio_desde_leido="1", folio_hasta_leido="5"),
                folios.Tramite(no_item=2, tipo_documental="Informe", folio_desde_leido="6", folio_hasta_leido="9")]
    resultado = folios.verificar_folios(tramites, folios_inventario=9)
    assert resultado.total_folios == 9 and not resultado.errores


def test_codigo_de_referencia_parametrizable():
    assert codigos.construir_codigo_referencia("Periodo II", codigo_subserie="01", consecutivo=7, entidad="ENT") == "CO-ENT-AC-PII-S01-00007"


def test_instrucciones_sin_contrato_fijo():
    texto = instrucciones.instruccion_hoja_de_control({"fondo": "el fondo acumulado de la Entidad Ficticia"})
    assert "Entidad Ficticia" in texto
    assert "Geológico" not in texto and "Colombiano" not in texto


def test_sin_llaves_el_lector_no_inventa(monkeypatch):
    for variable in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(lectores, "motores", lambda forzar=False: [])
    assert lectores.elegir_motor(None, folios=10) is None


def _importaciones(ruta: Path) -> set[str]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.add(nodo.module)
        elif isinstance(nodo, ast.Import):
            nombres.update(a.name for a in nodo.names)
    return nombres


def test_la_descripcion_isadg_es_independiente():
    """Ni la digitalización ni la hoja de control dependen de la ISAD(G), y la ISAD(G) no depende de la hoja de control."""
    raiz = Path(arca.__file__).parent
    hoja_de_control = {"arca.motor.instrucciones", "arca.motor.verificar_hoja", "arca.motor.importar_hoja", "arca.motor.folios"}
    describir = {"isadg", "descripcion"}  # el motor ISAD(G) y el módulo que lo usa
    for ruta in raiz.rglob("*.py"):
        if ruta.name == "main.py" or "flujo" in ruta.parts:  # la aplicación y el orquestador del flujo automático coordinan a todos
            continue
        if describir & set(ruta.parts):
            assert not (_importaciones(ruta) & hoja_de_control), f"{ruta} depende de la hoja de control"
        else:
            assert not any(m.startswith(("arca.motor.isadg", "arca.modulos.descripcion")) for m in _importaciones(ruta)), f"{ruta} depende de la ISAD(G)"
