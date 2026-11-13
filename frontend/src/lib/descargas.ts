import { sesionGuardada } from "@/lib/api";

/** Descarga un archivo de la API con la sesión activa y lo guarda con el nombre indicado. */
export async function descargarArchivo(ruta: string, nombre: string) {
  const r = await fetch(`/api/v1${ruta}`, { headers: { Authorization: `Bearer ${sesionGuardada.token()}`, "X-Organizacion": sesionGuardada.organizacion() ?? "" } });
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? "No se pudo descargar");
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
