"""Correo saliente (D-46). Si no hay servidor configurado, no se envía nada y quien llama decide qué hacer.

`ARCA_SMTP_HOST=memoria` guarda los mensajes en `BANDEJA` en lugar de enviarlos: sirve para pruebas y demostraciones.
Un fallo al enviar no tumba la operación: se registra y se devuelve False.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from arca.nucleo.config import ajustes

log = logging.getLogger("arca.correo")
BANDEJA: list[dict[str, str]] = []


def configurado() -> bool:
    return bool(ajustes().smtp_host)


def enviar(para: str, asunto: str, texto: str) -> bool:
    a = ajustes()
    if not a.smtp_host:
        return False
    if a.smtp_host == "memoria":
        BANDEJA.append({"para": para, "asunto": asunto, "texto": texto})
        return True
    mensaje = EmailMessage()
    mensaje["From"], mensaje["To"], mensaje["Subject"] = a.smtp_remitente, para, asunto
    mensaje.set_content(texto)
    try:
        with smtplib.SMTP(a.smtp_host, a.smtp_puerto, timeout=20) as s:
            if a.smtp_tls:
                s.starttls(context=ssl.create_default_context())
            if a.smtp_usuario:
                s.login(a.smtp_usuario, a.smtp_clave)
            s.send_message(mensaje)
        return True
    except (OSError, smtplib.SMTPException) as e:
        log.error("No se pudo enviar el correo a %s: %s", para, e)
        return False
