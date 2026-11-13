"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Cargando } from "@/components/ui/basicos";
import { sesionGuardada } from "@/lib/api";

export default function Raiz() {
  const router = useRouter();
  useEffect(() => {
    router.replace(sesionGuardada.token() ? "/inicio" : "/ingresar");
  }, [router]);
  return <Cargando texto="Abriendo ARCA…" />;
}
