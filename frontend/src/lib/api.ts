/**
 * Cliente de la API de ARCA. La interfaz llama a /api/v1/... en su mismo origen y Next lo reenvía al
 * backend (next.config.ts), así no hay que abrir CORS ni exponer otra dirección.
 *
 * El token vive en sessionStorage: se pierde al cerrar la pestaña (decisión provisional; ver D-18).
 */

const CLAVE_TOKEN = "arca.token";
const CLAVE_ORG = "arca.organizacion";

export class ErrorApi extends Error {
  constructor(
    mensaje: string,
    public status: number,
    public cabeceras: Headers,
  ) {
    super(mensaje);
  }
}

function leer(clave: string): string | null {
  try {
    return window.sessionStorage.getItem(clave);
  } catch {
    return null;
  }
}

function escribir(clave: string, valor: string | null) {
  try {
    if (valor === null) window.sessionStorage.removeItem(clave);
    else window.sessionStorage.setItem(clave, valor);
  } catch {
    /* almacenamiento no disponible: la sesión vive solo en memoria */
  }
}

export const sesionGuardada = {
  token: () => leer(CLAVE_TOKEN),
  guardarToken: (t: string | null) => escribir(CLAVE_TOKEN, t),
  organizacion: () => leer(CLAVE_ORG),
  guardarOrganizacion: (id: string | null) => escribir(CLAVE_ORG, id),
  limpiar: () => (escribir(CLAVE_TOKEN, null), escribir(CLAVE_ORG, null)),
};

/** Mensaje legible a partir del cuerpo de error de FastAPI (texto o lista de validaciones). */
function mensajeDe(cuerpo: unknown, status: number): string {
  const detalle = (cuerpo as { detail?: unknown })?.detail;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) {
    return detalle
      .map((d: { loc?: (string | number)[]; msg?: string }) => {
        const campo = d.loc?.filter((x) => x !== "body").join(" › ");
        return campo ? `${campo}: ${d.msg}` : d.msg;
      })
      .join(" · ");
  }
  if (status === 403) return "Su rol no tiene permiso para esta acción.";
  if (status >= 500) return "Ocurrió una falla en el servidor. Intente de nuevo o comuníquese con soporte.";
  return `Error ${status}`;
}

type Opciones = { metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; cuerpo?: unknown; consulta?: Record<string, string | number | undefined | null>; sinOrganizacion?: boolean };

let alExpirar: (() => void) | null = null;
export function definirAlExpirar(fn: (() => void) | null) {
  alExpirar = fn;
}

export async function api<T>(ruta: string, { metodo = "GET", cuerpo, consulta, sinOrganizacion }: Opciones = {}): Promise<T> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(consulta ?? {})) if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  const url = `/api/v1${ruta}${params.size ? `?${params}` : ""}`;
  const cabeceras: Record<string, string> = { Accept: "application/json" };
  const token = sesionGuardada.token();
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  const org = sesionGuardada.organizacion();
  if (org && !sinOrganizacion) cabeceras["X-Organizacion"] = org;
  if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";

  let respuesta: Response;
  try {
    respuesta = await fetch(url, { method: metodo, headers: cabeceras, body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo) });
  } catch {
    throw new ErrorApi("No hay conexión con el servidor de ARCA.", 0, new Headers());
  }
  if (respuesta.status === 204) return null as T;
  const cuerpoRespuesta = await respuesta.json().catch(() => null);
  if (!respuesta.ok) {
    const error = new ErrorApi(mensajeDe(cuerpoRespuesta, respuesta.status), respuesta.status, respuesta.headers);
    if (respuesta.status === 401 && token && !ruta.startsWith("/auth/ingresar")) alExpirar?.();
    throw error;
  }
  return cuerpoRespuesta as T;
}

function cabecerasBase(): Record<string, string> {
  const cabeceras: Record<string, string> = { Accept: "application/json" };
  const token = sesionGuardada.token();
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  const org = sesionGuardada.organizacion();
  if (org) cabeceras["X-Organizacion"] = org;
  return cabeceras;
}

/** Envía archivos (multipart). El navegador pone el Content-Type con su separador. */
export async function apiSubir<T>(ruta: string, datos: FormData): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`/api/v1${ruta}`, { method: "POST", headers: cabecerasBase(), body: datos });
  } catch {
    throw new ErrorApi("No hay conexión con el servidor de ARCA.", 0, new Headers());
  }
  const cuerpo = await respuesta.json().catch(() => null);
  if (!respuesta.ok) {
    if (respuesta.status === 401) alExpirar?.();
    throw new ErrorApi(mensajeDe(cuerpo, respuesta.status), respuesta.status, respuesta.headers);
  }
  return cuerpo as T;
}

/** Descarga un archivo con la sesión y lo abre en una pestaña nueva (visor del navegador). */
export async function abrirArchivo(ruta: string) {
  const ventana = window.open("", "_blank");
  const respuesta = await fetch(`/api/v1${ruta}`, { headers: cabecerasBase() });
  if (!respuesta.ok) {
    ventana?.close();
    const cuerpo = await respuesta.json().catch(() => null);
    throw new ErrorApi(mensajeDe(cuerpo, respuesta.status), respuesta.status, respuesta.headers);
  }
  const url = URL.createObjectURL(await respuesta.blob());
  if (ventana) ventana.location.href = url;
  else window.location.href = url;
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Trae un archivo de la API con la sesión y devuelve una URL local (blob) para mostrarlo en <img> o <iframe>. Quien la usa la libera. */
export async function urlLocal(ruta: string): Promise<string> {
  const respuesta = await fetch(`/api/v1${ruta}`, { headers: cabecerasBase() });
  if (!respuesta.ok) {
    const cuerpo = await respuesta.json().catch(() => null);
    throw new ErrorApi(mensajeDe(cuerpo, respuesta.status), respuesta.status, respuesta.headers);
  }
  return URL.createObjectURL(await respuesta.blob());
}
