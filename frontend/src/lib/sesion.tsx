"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { Cargando } from "@/components/ui/basicos";
import { api, definirAlExpirar, sesionGuardada } from "@/lib/api";
import type { MembresiaResumen, Yo } from "@/lib/tipos";

type ValorSesion = {
  usuario: Yo;
  organizacion: MembresiaResumen | null;
  puede: (permiso: string) => boolean;
  salir: () => Promise<void>;
  recargar: () => Promise<void>;
};

const Contexto = createContext<ValorSesion | null>(null);

export function useSesion() {
  const v = useContext(Contexto);
  if (!v) throw new Error("useSesion requiere ProveedorSesion");
  return v;
}

/** Carga la sesión. Sin sesión válida, o con la contraseña temporal sin cambiar, devuelve al ingreso. */
export function ProveedorSesion({ children, alSinSesion }: { children: ReactNode; alSinSesion: (destino?: string) => void }) {
  const [usuario, setUsuario] = useState<Yo | null>(null);

  const recargar = useCallback(async () => {
    if (!sesionGuardada.token()) return alSinSesion();
    try {
      const yo = await api<Yo>("/auth/yo", { sinOrganizacion: true });
      if (yo.debe_cambiar_clave) return alSinSesion();
      if (!yo.es_operador) {
        const guardada = sesionGuardada.organizacion();
        const vigente = yo.organizaciones.find((o) => o.organizacion_id === guardada);
        if (!vigente) {
          if (yo.organizaciones.length === 1) sesionGuardada.guardarOrganizacion(yo.organizaciones[0].organizacion_id);
          else return alSinSesion(yo.organizaciones.length ? "/elegir" : undefined);
        }
      }
      setUsuario(yo);
    } catch {
      sesionGuardada.limpiar();
      alSinSesion();
    }
  }, [alSinSesion]);

  useEffect(() => {
    definirAlExpirar(() => {
      sesionGuardada.limpiar();
      alSinSesion();
    });
    void recargar();
    return () => definirAlExpirar(null);
  }, [recargar, alSinSesion]);

  const valor = useMemo<ValorSesion | null>(() => {
    if (!usuario) return null;
    const organizacion = usuario.organizaciones.find((o) => o.organizacion_id === sesionGuardada.organizacion()) ?? null;
    return {
      usuario,
      organizacion,
      puede: (permiso: string) => !!organizacion?.permisos.includes(permiso),
      salir: async () => {
        sesionGuardada.limpiar();
        alSinSesion();
      },
      recargar,
    };
  }, [usuario, alSinSesion, recargar]);

  if (!valor) return <Cargando texto="Abriendo ARCA…" />;
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}
