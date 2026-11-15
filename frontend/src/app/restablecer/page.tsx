"use client";

import { KeyRound } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { IsotipoArca } from "@/components/layout/marca";
import { Boton, CajaError } from "@/components/ui/basicos";
import { Campo, Entrada } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { requisitosClave } from "@/lib/clave";

/** Restablecer la contraseña con el enlace de un solo uso que llegó por correo. */
function Formulario() {
  const token = useSearchParams().get("token") ?? "";
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState(false);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (requisitosClave(nueva, "").some((r) => !r.ok)) return setError("La contraseña nueva no cumple los requisitos.");
    if (nueva !== confirmacion) return setError("Las dos contraseñas no coinciden.");
    setEnviando(true);
    try {
      await api("/auth/restablecer", { metodo: "POST", cuerpo: { token, clave_nueva: nueva }, sinOrganizacion: true });
      setListo(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={enviar} className="w-full max-w-sm rounded-2xl border border-line bg-surface p-8 shadow-sm">
      <div className="mb-6 flex items-center gap-3">
        <IsotipoArca tamano={40} />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-titulo">Nueva contraseña</h1>
          <p className="text-[13px] text-texto-3">El enlace sirve una sola vez.</p>
        </div>
      </div>
      {listo ? (
        <div className="flex flex-col gap-4">
          <p className="rounded-md bg-ok-suave px-3 py-2 text-[13px] text-ok">Listo: su contraseña quedó cambiada y se cerraron sus otras sesiones.</p>
          <Link href="/ingresar" className="text-center font-semibold text-marca hover:underline">Ingresar</Link>
        </div>
      ) : !token ? (
        <CajaError mensaje="El enlace no trae el código. Ábralo completo desde el correo o pida uno nuevo." />
      ) : (
        <div className="flex flex-col gap-4">
          <Campo etiqueta="Contraseña nueva"><Entrada type="password" autoComplete="new-password" required autoFocus value={nueva} onChange={(e) => setNueva(e.target.value)} className="h-10" /></Campo>
          <ul className="flex flex-col gap-1 text-[12.5px]">
            {requisitosClave(nueva, "").map((r) => <li key={r.texto} className={r.ok ? "text-ok" : "text-texto-3"}>{r.ok ? "✓" : "○"} {r.texto}</li>)}
          </ul>
          <Campo etiqueta="Repítala"><Entrada type="password" autoComplete="new-password" required value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} className="h-10" /></Campo>
          {error && <CajaError mensaje={error} />}
          <Boton type="submit" variante="primario" cargando={enviando} icono={<KeyRound />} className="mt-1 h-11 text-[15px]">Guardar</Boton>
          <Link href="/ingresar" className="text-center text-[12.5px] text-texto-3 underline">Volver a ingresar</Link>
        </div>
      )}
    </form>
  );
}

export default function Restablecer() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <Suspense fallback={null}><Formulario /></Suspense>
    </main>
  );
}
