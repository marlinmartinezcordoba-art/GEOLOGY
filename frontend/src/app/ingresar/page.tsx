"use client";

import { Building2, KeyRound, ScanLine, ShieldCheck, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { IsotipoArca, LogoArca } from "@/components/layout/marca";
import { Boton, CajaError } from "@/components/ui/basicos";
import { Campo, Entrada } from "@/components/ui/campos";
import { api, ErrorApi, sesionGuardada } from "@/lib/api";
import { requisitosClave } from "@/lib/clave";
import type { Token, Yo } from "@/lib/tipos";

const ETAPAS = ["Inventario", "Alistamiento", "Digitalización", "Calidad", "OCR", "Hoja de control", "Verificación", "Inspección", "Entrega"];

type Paso = "clave" | "mfa" | "nueva" | "recuperar";

export default function Ingresar() {
  const router = useRouter();
  const [paso, setPaso] = useState<Paso>("clave");
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [codigo, setCodigo] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  async function abrir() {
    const yo = await api<Yo>("/auth/yo", { sinOrganizacion: true });
    if (yo.es_operador) return router.replace("/plataforma");
    if (yo.organizaciones.length === 1) {
      sesionGuardada.guardarOrganizacion(yo.organizaciones[0].organizacion_id);
      return router.replace("/inicio");
    }
    if (!yo.organizaciones.length) throw new Error("Su cuenta no tiene acceso a ninguna organización activa. Comuníquese con el administrador.");
    router.replace("/elegir");
  }

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      if (paso === "recuperar") {
        const r = await api<{ mensaje: string }>("/auth/recuperar", { metodo: "POST", cuerpo: { correo }, sinOrganizacion: true });
        setAviso(r.mensaje);
        setEnviando(false);
        return;
      }
      if (paso === "nueva") {
        if (requisitosClave(nueva, correo).some((r) => !r.ok)) throw new Error("La contraseña nueva no cumple los requisitos.");
        if (nueva !== confirmacion) throw new Error("Las dos contraseñas no coinciden.");
        const t = await api<Token>("/auth/cambiar-clave", { metodo: "POST", cuerpo: { clave_actual: clave, clave_nueva: nueva }, sinOrganizacion: true });
        sesionGuardada.guardarToken(t.access_token);
        await abrir();
        return;
      }
      sesionGuardada.limpiar();
      const t = await api<Token>("/auth/ingresar", { metodo: "POST", cuerpo: { correo, clave, codigo_mfa: paso === "mfa" ? codigo.replace(/\s/g, "") : null } });
      sesionGuardada.guardarToken(t.access_token);
      if (t.debe_cambiar_clave) {
        setPaso("nueva");
        setEnviando(false);
        return;
      }
      await abrir();
    } catch (err) {
      if (err instanceof ErrorApi && err.cabeceras.get("X-ARCA-MFA") === "requerido") {
        setPaso("mfa");
        setError(null);
      } else {
        setError((err as Error).message);
      }
      setEnviando(false);
    }
  }

  function volver() {
    sesionGuardada.limpiar();
    setPaso("clave");
    setCodigo("");
    setNueva("");
    setConfirmacion("");
    setError(null);
  }

  const titulos: Record<Paso, [string, string]> = {
    clave: ["Ingresar", "Con el correo que le asignó su organización."],
    mfa: ["Verificación en dos pasos", "Escriba el código de 6 dígitos de su aplicación de autenticación."],
    nueva: ["Cree su contraseña", "Su contraseña actual es temporal. Cree una que solo usted conozca."],
    recuperar: ["Recuperar la contraseña", "Le enviaremos un enlace a su correo para crear una nueva."],
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-profundo p-12 text-white lg:flex xl:p-16">
        <svg viewBox="0 0 64 64" aria-hidden="true" className="pointer-events-none absolute -right-28 -bottom-24 h-[34rem] w-[34rem] opacity-[0.06]">
          <path d="M13 24 L32 13 L51 24" fill="none" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" />
          <rect x="15" y="27" width="34" height="24" rx="3.5" fill="none" stroke="#fff" strokeWidth="1.4" />
          <path d="M24 33 V45 M32 33 V45 M40 33 V45" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(15,139,141,0.18),transparent_55%)]" />

        <LogoArca tamano={44} claro subtitulo={null} className="relative" />

        <div className="relative max-w-xl">
          <p className="mb-3 text-[13px] font-medium tracking-wide text-motor-vivo uppercase">Gestión archivística, digitalización y automatización documental</p>
          <h1 className="text-[42px] leading-[1.1] font-semibold tracking-tight">Del archivo físico al expediente digital, sin perder el orden original.</h1>
          <p className="mt-4 max-w-lg text-lg text-profundo-texto">ARCA propone desde el OCR y las reglas archivísticas, su equipo valida y todo queda registrado, con procedencia, evidencia y trazabilidad.</p>
          <ol className="mt-9 grid max-w-lg grid-cols-3 gap-x-4 gap-y-3">
            {ETAPAS.map((nombre, i) => (
              <li key={nombre} className="flex items-center gap-2.5 text-[13px]">
                <span className="grid size-6 shrink-0 place-items-center rounded-full border border-motor-vivo/60 font-mono text-[11px] text-motor-vivo">{i + 1}</span>
                <span className="text-white/85">{nombre}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="relative flex flex-wrap gap-x-7 gap-y-2 text-[13px] text-profundo-texto">
          <span className="flex items-center gap-2"><Building2 className="size-4 text-motor-vivo" /> Multiempresa, datos aislados</span>
          <span className="flex items-center gap-2"><ScanLine className="size-4 text-motor-vivo" /> Procesamiento masivo</span>
          <span className="flex items-center gap-2"><Sparkles className="size-4 text-motor-vivo" /> Propuestas con evidencia</span>
          <span className="flex items-center gap-2"><ShieldCheck className="size-4 text-motor-vivo" /> Auditoría encadenada</span>
        </div>
      </section>

      <main id="contenido" className="flex items-center justify-center bg-canvas p-6">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex justify-center lg:hidden">
            <LogoArca tamano={40} />
          </div>
          <form onSubmit={enviar} className="rounded-2xl border border-line bg-surface p-8 shadow-sm">
            <div className="mb-6 flex items-center gap-3">
              <IsotipoArca tamano={40} className="hidden lg:block" />
              <div>
                <h2 className="text-2xl font-semibold tracking-tight text-titulo">{titulos[paso][0]}</h2>
                <p className="text-[13px] text-texto-3">{titulos[paso][1]}</p>
              </div>
            </div>

            {paso === "clave" && (
              <div className="flex flex-col gap-4">
                <Campo etiqueta="Correo">
                  <Entrada type="email" autoComplete="username" required value={correo} onChange={(e) => setCorreo(e.target.value)} className="h-10" autoFocus />
                </Campo>
                <Campo etiqueta="Contraseña">
                  <Entrada type="password" autoComplete="current-password" required value={clave} onChange={(e) => setClave(e.target.value)} className="h-10" />
                </Campo>
                {error && <CajaError mensaje={error} />}
                <Boton type="submit" variante="primario" cargando={enviando} icono={<KeyRound />} className="mt-1 h-11 text-[15px]">
                  Ingresar
                </Boton>
                <button type="button" onClick={() => (setPaso("recuperar"), setError(null), setAviso(null))} className="text-center text-[12.5px] text-marca underline">¿Olvidó su contraseña?</button>
              </div>
            )}

            {paso === "recuperar" && (
              <div className="flex flex-col gap-4">
                <Campo etiqueta="Correo">
                  <Entrada type="email" autoComplete="username" required value={correo} onChange={(e) => setCorreo(e.target.value)} className="h-10" autoFocus />
                </Campo>
                {error && <CajaError mensaje={error} />}
                {aviso && <p className="rounded-md bg-info-suave px-3 py-2 text-[13px] text-info">{aviso} Si no le llega, pídale al administrador de su organización que restablezca su contraseña.</p>}
                <Boton type="submit" variante="primario" cargando={enviando} icono={<KeyRound />} className="mt-1 h-11 text-[15px]">Enviar el enlace</Boton>
                <button type="button" onClick={volver} className="text-[12.5px] text-texto-3 underline">Volver a ingresar</button>
              </div>
            )}

            {paso === "mfa" && (
              <div className="flex flex-col gap-4">
                <Campo etiqueta="Código de verificación">
                  <Entrada type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={7} required autoFocus value={codigo} onChange={(e) => setCodigo(e.target.value)} className="h-11 text-center font-mono text-lg tracking-[0.3em]" placeholder="000000" />
                </Campo>
                {error && <CajaError mensaje={error} />}
                <Boton type="submit" variante="primario" cargando={enviando} icono={<ShieldCheck />} className="mt-1 h-11 text-[15px]">
                  Verificar y entrar
                </Boton>
                <button type="button" onClick={volver} className="text-[12.5px] text-texto-3 underline">Volver e ingresar con otra cuenta</button>
              </div>
            )}

            {paso === "nueva" && (
              <div className="flex flex-col gap-4">
                <input type="text" autoComplete="username" value={correo} readOnly hidden />
                <Campo etiqueta="Contraseña nueva">
                  <Entrada type="password" autoComplete="new-password" required autoFocus value={nueva} onChange={(e) => setNueva(e.target.value)} className="h-10" />
                </Campo>
                <ul className="flex flex-col gap-1 text-[12.5px]">
                  {requisitosClave(nueva, correo).map((r) => (
                    <li key={r.texto} className={r.ok ? "text-ok" : "text-texto-3"}>{r.ok ? "✓" : "○"} {r.texto}</li>
                  ))}
                </ul>
                <Campo etiqueta="Repítala">
                  <Entrada type="password" autoComplete="new-password" required value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} className="h-10" />
                </Campo>
                {error && <CajaError mensaje={error} />}
                <Boton type="submit" variante="primario" cargando={enviando} icono={<KeyRound />} className="mt-1 h-11 text-[15px]">
                  Guardar y continuar
                </Boton>
                <button type="button" onClick={volver} className="text-[12.5px] text-texto-3 underline">Volver e ingresar con otra cuenta</button>
              </div>
            )}
          </form>
          <p className="mt-3 text-center text-[12px] text-texto-3">Uso autorizado. Cada ingreso y cada acción quedan en la auditoría.</p>
        </div>
      </main>
    </div>
  );
}
