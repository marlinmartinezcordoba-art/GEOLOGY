"use client";

import { Building2, ChevronRight, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

import { LogoArca } from "@/components/layout/marca";
import { CajaError, Cargando } from "@/components/ui/basicos";
import { api, sesionGuardada } from "@/lib/api";
import type { Yo } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

/** Quien pertenece a varias organizaciones escoge con cuál trabaja. ARCA nunca la escoge por la persona. */
export default function ElegirOrganizacion() {
  const router = useRouter();
  const { datos, error, cargando } = useDatos(() => api<Yo>("/auth/yo", { sinOrganizacion: true }), []);
  const elegir = (id: string) => {
    sesionGuardada.guardarOrganizacion(id);
    router.replace("/inicio");
  };
  return (
    <main id="contenido" className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <div className="w-full max-w-md">
        <div className="mb-6 flex justify-center">
          <LogoArca tamano={40} />
        </div>
        <div className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
          <h1 className="text-xl font-semibold text-titulo">¿Con qué organización va a trabajar?</h1>
          <p className="mt-1 text-[13px] text-texto-3">Pertenece a varias. Los datos de cada una están separados; puede cambiar después desde la barra superior.</p>
          <div className="mt-5 flex flex-col gap-2">
            {cargando && <Cargando />}
            {error && <CajaError mensaje={error} />}
            {datos?.organizaciones.map((o) => (
              <button key={o.organizacion_id} onClick={() => elegir(o.organizacion_id)} className="group flex items-center gap-3 rounded-xl border border-line p-3.5 text-left transition-colors hover:border-marca-borde hover:bg-marca-suave/40">
                <span className="grid size-10 place-items-center rounded-xl bg-marca-suave text-marca"><Building2 className="size-5" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-texto">{o.organizacion}</span>
                  <span className="block truncate text-[12.5px] text-texto-3">{o.rol}</span>
                </span>
                <ChevronRight className="size-4 text-texto-3 group-hover:text-marca" />
              </button>
            ))}
          </div>
          <button onClick={() => (sesionGuardada.limpiar(), router.replace("/ingresar"))} className="mt-5 inline-flex items-center gap-1.5 text-[13px] text-texto-3 hover:text-marca">
            <LogOut className="size-4" /> Salir
          </button>
        </div>
      </div>
    </main>
  );
}
