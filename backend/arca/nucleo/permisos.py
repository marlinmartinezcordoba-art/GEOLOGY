"""Permisos de la Etapa 1 y roles base sembrados en cada organización.

Denegar por defecto: una acción solo se permite si el rol de la membresía activa tiene el permiso.
Los roles base son una PROPUESTA INICIAL tomada de los perfiles reales de GEOLOGY (administradora,
líder, equipo, consulta y entidad) y deben aprobarse en la matriz de acceso (decisión D-07).
Cada etapa nueva agrega aquí sus permisos; no se crean permisos que ningún módulo use.
"""

from enum import StrEnum


class Permiso(StrEnum):
    ORGANIZACION_LEER = "organizacion:leer"
    USUARIOS = "usuarios:gestionar"
    ROLES = "roles:gestionar"
    CONFIGURACION_LEER = "configuracion:leer"
    CONFIGURACION = "configuracion:gestionar"
    PROYECTOS_LEER = "proyectos:leer"
    PROYECTOS = "proyectos:gestionar"
    AUDITORIA = "auditoria:leer"
    # Incremento 2: inventario, digitalización y control de calidad.
    INVENTARIO_LEER = "inventario:leer"
    INVENTARIO = "inventario:gestionar"
    CAPTURAR = "captura:cargar"
    CALIDAD = "calidad:validar"
    # M24 productividad y Power BI.
    PRODUCTIVIDAD_LEER = "productividad:leer"
    PRODUCTIVIDAD_REGISTRAR = "productividad:registrar"
    PRODUCTIVIDAD_CONFIGURAR = "productividad:configurar"
    # Plantillas de la entidad (FUID de salida, rótulos) y expedición de esos documentos.
    PLANTILLAS = "plantillas:gestionar"
    # M04 instrumentos archivísticos (TRD, TVD, CCD).
    INSTRUMENTOS_LEER = "instrumentos:leer"
    INSTRUMENTOS = "instrumentos:gestionar"
    INSTRUMENTOS_APROBAR = "instrumentos:aprobar"
    CLASIFICAR = "clasificacion:gestionar"
    TRANSFERIR = "transferencias:gestionar"
    RECIBIR_TRANSFERENCIA = "transferencias:recibir"
    DISPONER = "disposicion:gestionar"
    APROBAR_DISPOSICION = "disposicion:aprobar"
    HOJA_CONTROL = "hoja_control:elaborar"
    VERIFICAR_HOJA = "hoja_control:verificar"
    DESCRIBIR = "descripcion:elaborar"
    APROBAR_DESCRIPCION = "descripcion:aprobar"
    CONSULTAR = "consulta:buscar"
    CONSULTA_RESERVADA = "consulta:reservada"
    EXPEDIR = "entregables:expedir"


TODOS = [p.value for p in Permiso]

# Permisos que vuelven privilegiado un rol: con ellos se exige verificación en dos pasos cuando la
# política «seguridad.mfa_privilegiados» está activa.
PRIVILEGIADOS = {Permiso.USUARIOS.value, Permiso.ROLES.value, Permiso.CONFIGURACION.value}

ADMINISTRADOR = "Administrador de la organización"

ROLES_BASE: list[dict] = [
    {
        "nombre": ADMINISTRADOR,
        "descripcion": "Configura la organización, sus usuarios, roles y parámetros.",
        "permisos": TODOS,
    },
    {
        "nombre": "Dirección de proyecto",
        "descripcion": "Crea y conduce los proyectos: alcance, metas, sedes y equipo.",
        "permisos": [
            Permiso.ORGANIZACION_LEER, Permiso.PROYECTOS_LEER, Permiso.PROYECTOS, Permiso.CONFIGURACION_LEER, Permiso.AUDITORIA,
            Permiso.INVENTARIO_LEER, Permiso.INVENTARIO, Permiso.CAPTURAR, Permiso.CALIDAD,
            Permiso.PRODUCTIVIDAD_LEER, Permiso.PRODUCTIVIDAD_REGISTRAR, Permiso.PRODUCTIVIDAD_CONFIGURAR,
            Permiso.PLANTILLAS, Permiso.EXPEDIR, Permiso.INSTRUMENTOS_LEER, Permiso.INSTRUMENTOS, Permiso.INSTRUMENTOS_APROBAR, Permiso.CLASIFICAR,
            Permiso.TRANSFERIR, Permiso.RECIBIR_TRANSFERENCIA, Permiso.DISPONER, Permiso.APROBAR_DISPOSICION,
            Permiso.HOJA_CONTROL, Permiso.VERIFICAR_HOJA, Permiso.DESCRIBIR, Permiso.APROBAR_DESCRIPCION,
            Permiso.CONSULTAR, Permiso.CONSULTA_RESERVADA,
        ],
    },
    {
        "nombre": "Equipo operativo",
        "descripcion": "Trabaja en los proyectos a los que está asignado: carga lo digitalizado y revisa la calidad.",
        "permisos": [Permiso.ORGANIZACION_LEER, Permiso.PROYECTOS_LEER, Permiso.INVENTARIO_LEER, Permiso.CAPTURAR, Permiso.CALIDAD,
            Permiso.PRODUCTIVIDAD_LEER, Permiso.PRODUCTIVIDAD_REGISTRAR, Permiso.EXPEDIR, Permiso.INSTRUMENTOS_LEER, Permiso.CLASIFICAR, Permiso.TRANSFERIR, Permiso.DISPONER, Permiso.HOJA_CONTROL, Permiso.VERIFICAR_HOJA, Permiso.DESCRIBIR,
            Permiso.CONSULTAR,
        ],
    },
    {
        "nombre": "Consulta y auditoría",
        "descripcion": "Solo lectura: control interno y auditoría. No interviene la operación.",
        "permisos": [Permiso.ORGANIZACION_LEER, Permiso.PROYECTOS_LEER, Permiso.CONFIGURACION_LEER, Permiso.AUDITORIA, Permiso.INVENTARIO_LEER,
            Permiso.PRODUCTIVIDAD_LEER, Permiso.INSTRUMENTOS_LEER, Permiso.CONSULTAR,
        ],
    },
    {
        "nombre": "Entidad cliente",
        "descripcion": "La entidad contratante consulta únicamente los proyectos que se le asignen, y su avance.",
        "permisos": [Permiso.PROYECTOS_LEER, Permiso.PRODUCTIVIDAD_LEER, Permiso.CONSULTAR],
    },
]


def validar_permisos(permisos: list[str]) -> list[str]:
    desconocidos = sorted(set(permisos) - set(TODOS))
    if desconocidos:
        raise ValueError(f"Permisos inexistentes: {', '.join(desconocidos)}")
    return sorted(set(permisos))
