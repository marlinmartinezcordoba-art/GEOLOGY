"""
Permite que pytest encuentre el paquete geology sin instalar nada.
Basta con estar dentro de la carpeta del proyecto al ejecutar las pruebas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
