/** Requisitos de contraseña: los mismos que valida el backend (D-14). */
export function requisitosClave(clave: string, correo: string) {
  const usuario = correo.split("@")[0]?.toLowerCase() ?? "";
  return [
    { texto: "Al menos 12 caracteres", ok: clave.length >= 12 },
    { texto: "No contiene su usuario de correo", ok: !!clave && (!usuario || !clave.toLowerCase().includes(usuario)) },
  ];
}
