/** Utilidades de formato (recicladas de Kustos). */

export function cn(...clases: (string | false | null | undefined)[]): string {
  return clases.filter(Boolean).join(" ");
}

const NUMERO = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });

export function numero(valor: number | string | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  return NUMERO.format(Number(valor));
}

function aFecha(valor: string | Date): Date {
  if (valor instanceof Date) return valor;
  // Las fechas sin hora (AAAA-MM-DD) se interpretan en hora local, no UTC.
  return /^\d{4}-\d{2}-\d{2}$/.test(valor) ? new Date(`${valor}T00:00:00`) : new Date(valor);
}

export function fecha(valor: string | Date | null | undefined): string {
  if (!valor) return "—";
  return aFecha(valor).toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
}

export function fechaHora(valor: string | null | undefined): string {
  if (!valor) return "—";
  return aFecha(valor).toLocaleString("es-CO", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function iniciales(nombre: string | null | undefined): string {
  return (nombre ?? "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

/** Sin tildes y en minúscula: la forma para comparar textos al filtrar. */
export function normalizar(texto: string): string {
  return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}
