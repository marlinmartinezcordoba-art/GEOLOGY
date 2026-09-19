"""
Ingreso, contraseñas y competencias.

Cada persona entra con su correo y su contraseña. El servidor entrega un pase firmado que
el navegador guarda y presenta en cada petición. La contraseña no se guarda en ninguna
parte: solo su huella.

La clave que se entrega al crear el usuario es provisional y el sistema obliga a cambiarla
en el primer ingreso, de modo que ninguna clave escrita en una hoja de cálculo siga
sirviendo después.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import obtener_sesion
from app.core.seguridad import HORAS_DE_SESION, crear_pase, leer_pase, llave_configurada
from app.models import UsuarioBD, cifrar_clave, clave_correcta
from app.services.estados import Funcion, Rol, Usuario

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

INTENTOS_MAXIMOS = 6
LARGO_MINIMO = 8


class Ingreso(BaseModel):
    correo: str
    clave: str


class CambioDeClave(BaseModel):
    clave_actual: str
    clave_nueva: str = Field(min_length=LARGO_MINIMO)


def _a_usuario(u: UsuarioBD) -> Usuario:
    """Convierte el registro de la base al objeto con el que razonan las reglas."""
    return Usuario(nombre=u.nombre, correo=u.correo, rol=Rol(u.rol), funcion=Funcion(u.funcion))


def usuario_actual(authorization: str = Header(default=""),
                   db: Session = Depends(obtener_sesion)) -> Usuario:
    """Identifica a quien hace la petición por su pase firmado."""
    pase = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not pase:
        raise HTTPException(401, "Su sesión no está iniciada. Ingrese con su correo y contraseña.")
    correo = leer_pase(pase)
    if not correo:
        raise HTTPException(401, "Su sesión venció o el pase no es válido. Vuelva a ingresar.")
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo, UsuarioBD.activo.is_(True)).first()
    if not u:
        raise HTTPException(403, "Su usuario ya no está activo en KUSTOS.")
    return _a_usuario(u)


def _ficha(u: UsuarioBD) -> dict:
    p = _a_usuario(u)
    return {
        "nombre": u.nombre, "correo": u.correo, "cargo": u.cargo,
        "rol": u.rol, "funcion": u.funcion, "activo": u.activo,
        "debe_cambiar_clave": u.debe_cambiar_clave,
        "ultimo_ingreso": u.ultimo_ingreso.isoformat(timespec="minutes") if u.ultimo_ingreso else None,
        "aprueba_descripcion": p.aprueba_descripcion,
        "revisa_hoja_control": p.revisa_hoja_control,
        "valida_descripcion": p.valida_descripcion,
        "elabora_descripcion": p.elabora_descripcion,
        "edita_hoja_control": p.edita_hoja_control,
        "puede_retirar": p.puede_retirar,
        "pestanas": list(p.pestanas_visibles),
    }


@router.post("/ingresar", summary="Ingresar con correo y contraseña")
def ingresar(datos: Ingreso, db: Session = Depends(obtener_sesion)) -> dict:
    correo = datos.correo.strip().lower()
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo).first()

    # El mismo mensaje para correo inexistente y clave errada, para no revelar quién existe.
    generico = "El correo o la contraseña no coinciden."
    if not u or not u.activo:
        raise HTTPException(401, generico)
    if u.intentos_fallidos >= INTENTOS_MAXIMOS:
        raise HTTPException(423, "Su usuario quedó bloqueado por intentos fallidos. "
                                 "Pida a la dirección del proyecto que lo desbloquee.")
    if not clave_correcta(datos.clave, u.clave_hash):
        u.intentos_fallidos += 1
        db.commit()
        restantes = INTENTOS_MAXIMOS - u.intentos_fallidos
        raise HTTPException(401, generico + (f" Le quedan {restantes} intentos."
                                             if restantes <= 3 else ""))

    u.intentos_fallidos = 0
    u.ultimo_ingreso = datetime.now()
    db.commit()
    return {"pase": crear_pase(u.correo), "horas": HORAS_DE_SESION,
            "usuario": _ficha(u),
            "aviso_llave": None if llave_configurada() else
                ("La llave secreta del proyecto no está configurada en el archivo .env, así que "
                 "las sesiones se caen cada vez que el servidor reinicia. Escriba CLAVE_SECRETA "
                 "antes de publicar la plataforma en la red.")}


@router.post("/cambiar-clave", summary="Cambiar la propia contraseña")
def cambiar_clave(datos: CambioDeClave, db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)) -> dict:
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == quien.correo).first()
    if not clave_correcta(datos.clave_actual, u.clave_hash):
        raise HTTPException(401, "La contraseña actual no coincide.")
    if datos.clave_nueva == datos.clave_actual:
        raise HTTPException(422, "La contraseña nueva debe ser distinta de la actual.")
    if len(datos.clave_nueva) < LARGO_MINIMO:
        raise HTTPException(422, f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres.")
    u.clave_hash = cifrar_clave(datos.clave_nueva)
    u.debe_cambiar_clave = False
    db.commit()
    return {"mensaje": "Contraseña cambiada. Su clave anterior ya no sirve."}


@router.get("/yo", summary="Quién soy y qué puedo hacer")
def yo(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    return _ficha(db.query(UsuarioBD).filter(UsuarioBD.correo == quien.correo).first())


@router.get("", summary="Equipo del contrato")
def listar(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    if quien.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "Solo la dirección del proyecto ve el equipo completo.")
    return [_ficha(u) for u in db.query(UsuarioBD).order_by(UsuarioBD.nombre).all()]


@router.post("/{correo}/restablecer", summary="Restablecer la contraseña de alguien del equipo")
def restablecer(correo: str, db: Session = Depends(obtener_sesion),
                quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Genera una clave provisional que la persona deberá cambiar al entrar. Sirve para el olvido
    y para desbloquear a quien falló demasiadas veces.
    """
    if quien.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "Restablecer contraseñas lo hace la dirección del proyecto.")
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo.strip().lower()).first()
    if not u:
        raise HTTPException(404, f"{correo} no está registrado.")
    import secrets
    provisional = "Kustos-" + secrets.token_urlsafe(6)
    u.clave_hash = cifrar_clave(provisional)
    u.debe_cambiar_clave = True
    u.intentos_fallidos = 0
    db.commit()
    return {"correo": u.correo, "clave_provisional": provisional,
            "mensaje": "Entréguesela en persona. La plataforma le exigirá cambiarla al entrar."}
