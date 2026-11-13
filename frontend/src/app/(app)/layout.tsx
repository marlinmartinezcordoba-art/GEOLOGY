"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback } from "react";

import { Shell } from "@/components/layout/shell";
import { Vacio } from "@/components/ui/basicos";
import { MODULOS } from "@/lib/modulos";
import { ProveedorSesion, useSesion } from "@/lib/sesion";

/** Sin el permiso del módulo la pantalla no se abre, aunque se escriba la dirección a mano. */
function GuardaModulo({ children }: { children: React.ReactNode }) {
  const ruta = usePathname();
  const { puede, usuario } = useSesion();
  const plataforma = ruta.startsWith("/plataforma");
  const m = MODULOS.find((x) => ruta === x.href || ruta.startsWith(x.href + "/"));
  const sinAcceso = (plataforma && !usuario.es_operador) || (!plataforma && usuario.es_operador && !ruta.startsWith("/cuenta")) || (m?.permiso && !puede(m.permiso));
  if (sinAcceso) {
    return (
      <Vacio
        icono={<Lock />}
        titulo="Sin acceso"
        descripcion={usuario.es_operador ? "El operador de la plataforma administra organizaciones, pero no entra a su contenido." : "Su rol no tiene acceso a esta sección. Si la necesita para su trabajo, solicítela al administrador de su organización."}
        accion={<Link href={usuario.es_operador ? "/plataforma" : "/inicio"} className="font-semibold text-marca hover:underline">Volver</Link>}
      />
    );
  }
  return <>{children}</>;
}

export default function LayoutApp({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const alSinSesion = useCallback((destino?: string) => router.replace(destino ?? "/ingresar"), [router]);
  return (
    <ProveedorSesion alSinSesion={alSinSesion}>
      <Shell>
        <GuardaModulo>{children}</GuardaModulo>
      </Shell>
    </ProveedorSesion>
  );
}
