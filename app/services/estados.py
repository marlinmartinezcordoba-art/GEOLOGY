"""
Ciclo de vida del expediente, competencias y retiro.  Reglas R39 a R49, más el paso nuevo.

Las reglas R39 a R49 son transcripción de REGISTRO.estados, importarUnaHojaDeControl_ y
KUSTOS_competencias_ del motor anterior. Lo que va bajo el título "Paso nuevo" no existía
en la plataforma anterior y se agrega por solicitud de la dirección del proyecto.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

DIAS_EN_PAPELERA = 30       # paso nuevo


class Estado(str, enum.Enum):
    """
    R39. Un expediente tiene un solo estado a la vez.

    El recorrido, tal como lo definió la dirección del proyecto el 9 de septiembre de 2026:

      1. En cola                      el documento digitalizado está cargado
      2. En procesamiento             el modelo está leyendo el documento
      3. Hoja de control en elaboración   alguien la está diligenciando y guardó avance
      4. Hoja de control por revisar  la hoja está completa y verificada; espera ojo humano
      5. Hoja de control revisada     alguien del equipo la revisó; ya se puede describir
      6. Descripción por validar      el ISAD(G) está generado; espera a quien lo valida
      7. Descripción validada         validada; espera la aprobación de la dirección o la líder
      8. Archivado                    aprobada; ya se puede llevar al inventario de salida
      9. En inventario de salida      asignada a caja definitiva, con rótulos y FUID cerrado
    """
    EN_COLA = "En cola"
    EN_PROCESAMIENTO = "En procesamiento"
    HOJA_EN_ELABORACION = "Hoja de control en elaboración"
    HOJA_POR_REVISAR = "Hoja de control por revisar"
    HOJA_REVISADA = "Hoja de control revisada"
    DESCRIPCION_POR_VALIDAR = "Descripción por validar"
    DESCRIPCION_VALIDADA = "Descripción validada"
    DEVUELTO = "Devuelto"
    ARCHIVADO = "Archivado"
    EN_INVENTARIO = "En inventario de salida"
    RETIRADO = "Retirado"

    # Nombres anteriores, conservados para no romper lo ya escrito
    HOJA_VERIFICADA = HOJA_POR_REVISAR
    PENDIENTE_REVISION = DESCRIPCION_POR_VALIDAR


TRANSICIONES: dict[Estado, set[Estado]] = {
    Estado.EN_COLA: {Estado.EN_PROCESAMIENTO, Estado.HOJA_EN_ELABORACION,
                     Estado.HOJA_POR_REVISAR, Estado.DEVUELTO, Estado.RETIRADO},
    Estado.EN_PROCESAMIENTO: {Estado.HOJA_POR_REVISAR, Estado.DEVUELTO,
                              Estado.EN_COLA, Estado.RETIRADO},
    Estado.HOJA_EN_ELABORACION: {Estado.HOJA_POR_REVISAR, Estado.DEVUELTO,
                                 Estado.HOJA_EN_ELABORACION, Estado.RETIRADO},
    # Paso humano 1. Alguien del equipo revisa la hoja de control.
    Estado.HOJA_POR_REVISAR: {Estado.HOJA_REVISADA, Estado.HOJA_EN_ELABORACION,
                              Estado.HOJA_POR_REVISAR, Estado.DEVUELTO, Estado.RETIRADO},
    # Con la hoja revisada ya se puede generar la descripción.
    Estado.HOJA_REVISADA: {Estado.DESCRIPCION_POR_VALIDAR, Estado.HOJA_POR_REVISAR,
                           Estado.DEVUELTO, Estado.RETIRADO},
    # Paso humano 2. Quien valida revisa el ISAD(G).
    Estado.DESCRIPCION_POR_VALIDAR: {Estado.DESCRIPCION_VALIDADA, Estado.HOJA_REVISADA,
                                     Estado.DEVUELTO, Estado.RETIRADO},
    # Paso humano 3. La dirección o la líder aprueban.
    Estado.DESCRIPCION_VALIDADA: {Estado.ARCHIVADO, Estado.DESCRIPCION_POR_VALIDAR,
                                  Estado.DEVUELTO, Estado.RETIRADO},
    Estado.DEVUELTO: {Estado.HOJA_EN_ELABORACION, Estado.HOJA_POR_REVISAR,
                      Estado.EN_COLA, Estado.RETIRADO},
    # R43. Rehacer una descripción aprobada devuelve la hoja al flujo.
    Estado.ARCHIVADO: {Estado.EN_INVENTARIO, Estado.HOJA_REVISADA, Estado.RETIRADO},
    # Una carpeta ya inventariada solo sale del inventario retirándola de la caja.
    Estado.EN_INVENTARIO: {Estado.ARCHIVADO},
    Estado.RETIRADO: set(),
}

# R45. Estados en los que volver a cargar la hoja de control se rechaza como duplicada.
#
# CORRECCIÓN. Antes se bloqueaba también «En cola», y eso rompía el uso normal: se carga el
# documento digitalizado, el expediente queda en cola, y al ir a diligenciar su hoja el
# sistema la rechazaba por duplicada. En cola significa cargado y esperando hoja, así que es
# justamente cuando hay que poder diligenciarla. Lo que la regla protege es que no se
# reemplace una hoja de un expediente que ya tiene descripción hecha.
ESTADOS_QUE_BLOQUEAN_RECARGA = {
    Estado.DESCRIPCION_POR_VALIDAR, Estado.DESCRIPCION_VALIDADA,
    Estado.ARCHIVADO, Estado.EN_INVENTARIO,
}

# Estados en los que ya existe una descripción hecha (R44)
ESTADOS_CON_DESCRIPCION = {Estado.DESCRIPCION_POR_VALIDAR, Estado.DESCRIPCION_VALIDADA,
                           Estado.ARCHIVADO, Estado.EN_INVENTARIO}


class Rol(str, enum.Enum):
    ADMINISTRADORA = "administradora"
    LIDER = "lider"
    EQUIPO = "equipo"
    CONSULTA = "consulta"


class Funcion(str, enum.Enum):
    DESCRIPCION = "Descripción"
    HOJA_CONTROL = "Hoja de control"
    AMBAS = "Ambas"


@dataclass(frozen=True)
class Usuario:
    nombre: str
    correo: str
    rol: Rol = Rol.EQUIPO
    funcion: Funcion = Funcion.AMBAS

    @property
    def aprueba_descripcion(self) -> bool:
        """R48. La administradora y la líder aprueban descripciones."""
        return self.rol in (Rol.ADMINISTRADORA, Rol.LIDER)

    @property
    def aprueba_hoja_control(self) -> bool:
        """R48. También quien tenga la función de hoja de control."""
        return self.aprueba_descripcion or self.funcion in (Funcion.HOJA_CONTROL, Funcion.AMBAS)

    @property
    def edita_hoja_control(self) -> bool:
        return self.rol != Rol.CONSULTA

    @property
    def revisa_hoja_control(self) -> bool:
        """Cualquiera del equipo puede revisar una hoja de control; el perfil de consulta no."""
        return self.rol != Rol.CONSULTA

    @property
    def elabora_descripcion(self) -> bool:
        """
        Quién puede generar el ISAD(G).

        Decisión de la dirección del proyecto del 9 de septiembre de 2026: la descripción la
        elaboran solo las profesionales a cargo de la descripción y la dirección. Diligenciar
        y corregir la hoja de control sigue abierto a todo el equipo, y ahí queda registrado
        quien inició sesión.

        El perfil de consulta queda fuera aunque su función diga otra cosa: quien audita mira,
        no produce, y si produjera dejaría de ser independiente de lo que audita.
        """
        if self.rol is Rol.CONSULTA:
            return False
        return self.funcion in (Funcion.DESCRIPCION, Funcion.AMBAS) or self.rol is Rol.LIDER

    @property
    def valida_descripcion(self) -> bool:
        """
        Quien revisa el ISAD(G). Es la profesional a cargo de la descripción, y también la
        dirección y la líder, para que el trabajo no se detenga si ella no está.
        """
        return self.funcion in (Funcion.DESCRIPCION, Funcion.AMBAS) or self.aprueba_descripcion

    @property
    def puede_retirar(self) -> bool:
        """Paso nuevo. Retirar del flujo es acto de dirección, no de digitación."""
        return self.aprueba_descripcion

    @property
    def pestanas_visibles(self) -> tuple[str, ...]:
        """R49. El perfil de consulta solo ve localización, instrumentos y avance."""
        if self.rol == Rol.CONSULTA:
            return ("localizacion", "instrumentos", "calidad", "avance")
        return ("inicio", "cargue", "hojas", "proceso", "revision",
                "localizacion", "reubicacion", "instrumentos", "calidad", "avance")


class TransicionNoPermitida(Exception):
    pass


class AprobacionPropia(Exception):
    pass


@dataclass
class Huella:
    """Un renglón de la bitácora. Nunca se borra."""
    estado_anterior: Estado | None
    estado_nuevo: Estado
    accion: str
    usuario: str | None = None
    motivo: str = ""
    fecha: datetime = field(default_factory=datetime.now)


@dataclass
class Expediente:
    """Vista mínima del expediente para razonar sobre su ciclo de vida."""
    codigo_carpeta: str
    estado: Estado = Estado.EN_COLA
    describio: str | None = None
    aprobo: str | None = None
    caja_definitiva: str | None = None
    retirado_en: datetime | None = None
    motivo_retiro: str = ""
    trazabilidad: list[Huella] = field(default_factory=list)


def cambiar_estado(exp: Expediente, nuevo: Estado, usuario: Usuario | None,
                   accion: str, motivo: str = "") -> Huella:
    """Aplica una transición validada y deja huella. R39."""
    if nuevo != exp.estado and nuevo not in TRANSICIONES.get(exp.estado, set()):
        raise TransicionNoPermitida(
            f"{exp.codigo_carpeta}: no se puede pasar de «{exp.estado.value}» a «{nuevo.value}».")
    huella = Huella(exp.estado, nuevo, accion, usuario.nombre if usuario else None, motivo)
    exp.estado = nuevo
    exp.trazabilidad.append(huella)
    return huella


def motivo_de_rechazo_de_carga(exp: Expediente | None) -> str | None:
    """
    R44 y R45. Devuelve el mensaje de rechazo cuando la carga es duplicada, o None si procede.
    Solo un expediente devuelto admite reemplazo; un retirado se puede volver a cargar.
    """
    if exp is None or exp.estado in (Estado.DEVUELTO, Estado.RETIRADO):
        return None
    if exp.estado in ESTADOS_CON_DESCRIPCION:
        return (f"DUPLICADA. La carpeta {exp.codigo_carpeta} ya tiene descripción realizada "
                f"(estado «{exp.estado.value}»). Si debe rehacerse, use Rehacer descripción.")
    if exp.estado in ESTADOS_QUE_BLOQUEAN_RECARGA:
        return (f"DUPLICADA. La carpeta {exp.codigo_carpeta} ya está en el proceso "
                f"(estado «{exp.estado.value}»). No se vuelve a cargar.")
    return None


def aprobar_descripcion(exp: Expediente, usuario: Usuario) -> Huella:
    """R47 y R48. Nadie aprueba su propio trabajo."""
    if not usuario.aprueba_descripcion:
        raise PermissionError("Solo la administradora o la líder aprueban descripciones.")
    if exp.describio and _misma_persona(exp.describio, usuario.nombre):
        raise AprobacionPropia(
            f"{usuario.nombre} elaboró esta descripción y no puede aprobar su propio trabajo.")
    exp.aprobo = usuario.nombre
    return cambiar_estado(exp, Estado.ARCHIVADO, usuario, "aprobar")


def _misma_persona(uno: str, otro: str) -> bool:
    from app.services.codigos import normalizar_texto
    return normalizar_texto(uno) == normalizar_texto(otro)


# ---------------------------------------------------------------------------
# Paso nuevo. Retiro de un expediente cargado por error, con papelera y restauración.
#
# No existía en la plataforma anterior: allí, un expediente marcado por equivocación solo
# se podía devolver, y quedaba estorbando en las bandejas para siempre.
#
# Criterio archivístico: en un sistema de gestión de documentos electrónicos de archivo no
# se borra nada de manera definitiva sin dejar rastro. Por eso el retiro no elimina el
# registro: lo saca de las bandejas de trabajo, exige un motivo escrito, guarda quién lo
# retiró y cuándo, libera el código de carpeta para poderlo cargar otra vez, y conserva el
# expediente en la papelera durante treinta días, de donde se puede restaurar. Al cumplirse
# el plazo se purga el contenido de trabajo y permanece la huella en la bitácora.
# ---------------------------------------------------------------------------

def puede_retirarse(exp: Expediente) -> tuple[bool, str]:
    """
    Paso nuevo. Un expediente se puede retirar en cualquier estado, salvo cuando ya está
    incorporado a una caja definitiva y al inventario de salida: allí primero hay que
    retirarlo de la caja, porque el inventario ya fue rotulado.
    """
    if exp.estado == Estado.RETIRADO:
        return False, f"{exp.codigo_carpeta} ya está retirada."
    if exp.estado == Estado.EN_INVENTARIO:
        return False, (f"{exp.codigo_carpeta} ya está en el inventario de salida, en la caja "
                       f"{exp.caja_definitiva or 'asignada'}. Retírela primero de la caja.")
    return True, ""


def retirar_expediente(exp: Expediente, usuario: Usuario, motivo: str) -> Huella:
    """
    Paso nuevo. Saca del flujo un expediente cargado o marcado por error.

    Exige motivo escrito, solo lo puede hacer la administradora o la líder, y no borra:
    deja el expediente en la papelera durante treinta días.
    """
    if not usuario.puede_retirar:
        raise PermissionError("Retirar un expediente del flujo lo hace la administradora o la líder.")
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise ValueError("Escriba el motivo del retiro; queda en la bitácora y en el informe mensual.")
    permitido, razon = puede_retirarse(exp)
    if not permitido:
        raise TransicionNoPermitida(razon)

    exp.retirado_en = datetime.now()
    exp.motivo_retiro = motivo
    return cambiar_estado(exp, Estado.RETIRADO, usuario, "retirar", motivo)


def restaurar_expediente(exp: Expediente, usuario: Usuario,
                         estado_destino: Estado = Estado.DEVUELTO) -> Huella:
    """
    Paso nuevo. Devuelve al flujo un expediente retirado por equivocación, mientras siga en
    la papelera. Regresa a Devuelto, que es el estado desde el cual se corrige y se vuelve a
    verificar, salvo que se indique otro destino.
    """
    if not usuario.puede_retirar:
        raise PermissionError("Restaurar un expediente lo hace la administradora o la líder.")
    if exp.estado != Estado.RETIRADO:
        raise TransicionNoPermitida(f"{exp.codigo_carpeta} no está retirada.")
    if dias_en_papelera(exp) > DIAS_EN_PAPELERA:
        raise TransicionNoPermitida(
            f"{exp.codigo_carpeta} lleva más de {DIAS_EN_PAPELERA} días retirada y ya fue purgada. "
            "Cárguela de nuevo como expediente nuevo; la bitácora conserva el antecedente.")
    huella = Huella(exp.estado, estado_destino, "restaurar", usuario.nombre,
                    f"Restaurada desde la papelera. Motivo del retiro: {exp.motivo_retiro}")
    exp.estado = estado_destino
    exp.retirado_en = None
    exp.motivo_retiro = ""
    exp.trazabilidad.append(huella)
    return huella


def dias_en_papelera(exp: Expediente, hoy: datetime | None = None) -> int:
    if not exp.retirado_en:
        return 0
    return ((hoy or datetime.now()) - exp.retirado_en).days


def purgable(exp: Expediente, hoy: datetime | None = None) -> bool:
    """Paso nuevo. Cumplido el plazo se purga el contenido de trabajo, no la bitácora."""
    return exp.estado == Estado.RETIRADO and dias_en_papelera(exp, hoy) > DIAS_EN_PAPELERA


def fecha_de_purga(exp: Expediente) -> date | None:
    if not exp.retirado_en:
        return None
    return (exp.retirado_en + timedelta(days=DIAS_EN_PAPELERA)).date()
