import type { EstadoProyecto } from "@/lib/tipos";

export const TONO_ESTADO = { borrador: "neutro", activo: "ok", cerrado: "info" } as const;
export const NOMBRE_ESTADO: Record<EstadoProyecto, string> = { borrador: "Borrador", activo: "Activo", cerrado: "Cerrado" };
