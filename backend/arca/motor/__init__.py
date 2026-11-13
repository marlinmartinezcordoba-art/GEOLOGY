"""Motor archivístico de ARCA: reglas reutilizadas de GEOLOGY, ya sin nada propio de ningún contrato.

Funciones puras (no tocan la base de datos), en dos partes que no dependen la una de la otra:

- Núcleo, para digitalización y hoja de control: fechas y fechas extremas, foliación, tipologías
  documentales, clasificación contra la tabla de valoración, verificación e importación de la hoja de
  control, control de calidad, disposición final, partición de documentos extensos y el reparto del
  trabajo entre modelos de lenguaje (Claude, Gemini y ChatGPT) con la regla de que nunca se inventa nada.
- `isadg`: la descripción archivística ISAD(G), aparte. Se usa solo cuando el proyecto la pide.

El ciclo de estados acoplado de GEOLOGY (hoja de control → descripción → archivado) no se trajo: en
ARCA cada fase del ciclo de vida y cada proceso tiene su propio flujo (decisión D-24). Lo que en
GEOLOGY consultaba su base de datos se reescribe en los módulos de ARCA sobre el modelo multiempresa,
con auditoría y versionado.
"""
