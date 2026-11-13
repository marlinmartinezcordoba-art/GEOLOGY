# M23 · Consulta

Decisión D-37. Pruebas: `backend/tests/test_m23_consulta.py`. Pantallas:
- menú **Consulta** (buscador, filtros, resultados, exportación);
- **ficha** del expediente (`/consulta/{proyecto}/{unidad}`).

## Qué se busca

Se busca en los proyectos del **alcance** de la persona, o en uno solo, y en cuatro fuentes:

| Fuente | Qué entra | Cuándo |
|---|---|---|
| FUID y clasificación | Identificador, nombre, código, caja, carpeta, notas, fechas, serie, subserie y dependencia | Siempre |
| Texto OCR | El texto de cada página, con su número de página | Cuando la página se leyó |
| Hoja de control | Tipo, detalle, fecha, radicado y observaciones de cada trámite | Solo si la hoja está **verificada** |
| Descripción ISAD(G) | Título, alcance, productor, historia y notas | Solo si está **aprobada** |

Lo que está en elaboración no se consulta: se consulta lo validado.

**Cómo se escribe la búsqueda**
- **Sin importar tildes ni mayúsculas:** «quorum» encuentra «quórum».
- **Todas las palabras** deben estar en el expediente, en cualquiera de sus fuentes.
- **Entre comillas**, la frase exacta.
- Los comodines de SQL no se interpretan.

**Filtros:** proyecto, serie o subserie (por código), dependencia, caja, fase del ciclo vital, rango de
fechas (que se cruce con las fechas extremas), solo digitalizadas, solo con hoja verificada, solo
descritas, y en qué fuentes buscar.

**Resultados:**
- cada expediente con su clasificación, caja, fechas, fase, imágenes y si tiene hoja verificada;
- hasta tres fragmentos donde aparece lo buscado, resaltados y con la fuente y el lugar («Texto OCR ·
  página 2»), que abren la ficha en esa página;
- **Exportar a Excel** con los filtros usados, hasta 5.000 resultados.

## El índice

- Es la tabla `consulta_entradas`: el texto original y su versión normalizada, de la misma longitud,
  para poder recortar el fragmento.
- Cada unidad guarda una **firma** de sus fuentes (cambios en el FUID, la clasificación, el OCR, la hoja y
  la descripción). Antes de cada búsqueda se reindexa lo que cambió, hasta 3.000 unidades por vez, y se
  avisa si queda algo pendiente.
- La consulta no depende de que los demás módulos le avisen.

## Acceso

- Solo se ven los proyectos del alcance de la persona; los demás responden 404. El rol **Entidad cliente**
  ahora puede consultar su proyecto.
- **Acceso según la TRD:** en un expediente clasificado o reservado, quien no tiene el permiso
  `consulta:reservada` (Administración y Dirección de proyecto) ve los metadatos, pero no las imágenes, el
  texto, la hoja ni los fragmentos. La búsqueda tampoco le revela coincidencias en ese contenido.
- Abrir una ficha queda en la auditoría, y dice si fue solo de metadatos. También quedan las descargas de
  originales y las exportaciones.

## La ficha

En un solo lugar y solo lectura:
- el inventario;
- la clasificación con el instrumento, el acceso, la disposición y la retención;
- la fase y su historial (transferencias, eliminación);
- la descripción ISAD(G) aprobada;
- la hoja de control verificada (al hacer clic en un trámite, el visor va a su página);
- el visor de páginas, con el original verificado contra su huella.

## API

`/api/v1/consulta`:
- `GET /proyectos` · `GET /buscar` · `GET /exportar`
- `GET /proyectos/{p}/unidades/{u}` (ficha)
- `GET /proyectos/{p}/unidades/{u}/paginas/{n}/imagen` y `/original`

Permisos (migración 0012):
- `consulta:buscar`: todos los roles base, incluida la entidad cliente.
- `consulta:reservada`: Administración y Dirección de proyecto.

## Pendiente

- Solicitudes de consulta y préstamo con trazabilidad (atención a la entidad o al ciudadano).
- Búsqueda por similitud o con IA sobre el contenido (M27).
- Motor de búsqueda dedicado si el volumen lo exige (por ejemplo, el texto completo de PostgreSQL).
