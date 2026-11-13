"use client";

import { KeyRound, LogOut, ShieldCheck, Smartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, CabeceraTarjeta, CajaError, Datos, EncabezadoPagina, Insignia, Nota, Tarjeta } from "@/components/ui/basicos";
import { Campo, Entrada } from "@/components/ui/campos";
import { api, sesionGuardada } from "@/lib/api";
import { requisitosClave } from "@/lib/clave";
import { useSesion } from "@/lib/sesion";
import type { Token } from "@/lib/tipos";

export default function Cuenta() {
  const { usuario, organizacion, recargar } = useSesion();
  const avisos = useAvisos();
  const router = useRouter();
  return (
    <>
      <EncabezadoPagina titulo="Mi cuenta" descripcion="Su contraseña y la verificación en dos pasos protegen el acceso a todas sus organizaciones." />
      <div className="grid gap-6 xl:grid-cols-2">
        <Tarjeta>
          <CabeceraTarjeta titulo="Datos de la cuenta" />
          <div className="p-5">
            <Datos
              filas={[
                ["Nombre", usuario.nombre_completo],
                ["Correo", usuario.correo],
                ["Perfil", usuario.es_operador ? "Operador de la plataforma" : organizacion?.rol],
                ["Verificación en dos pasos", usuario.mfa_activo ? <Insignia key="m" tono="ok"><ShieldCheck className="size-3" /> Activa</Insignia> : <Insignia key="m" tono="aviso">Inactiva</Insignia>],
                ["Organizaciones", usuario.organizaciones.map((o) => o.organizacion).join(", ") || "—"],
              ]}
            />
            <div className="mt-5 border-t border-line pt-4">
              <Boton
                icono={<LogOut />}
                onClick={async () => {
                  await api("/auth/cerrar-sesiones", { metodo: "POST", sinOrganizacion: true });
                  sesionGuardada.limpiar();
                  router.replace("/ingresar");
                }}
              >
                Cerrar todas mis sesiones
              </Boton>
              <p className="mt-1.5 text-[12px] text-texto-3">Cierra la sesión en todos los equipos donde haya entrado, incluido este.</p>
            </div>
          </div>
        </Tarjeta>
        <CambiarClave correo={usuario.correo} alCambiar={() => avisos.exito("Contraseña cambiada. Se cerraron sus otras sesiones.")} />
        <VerificacionDosPasos activa={usuario.mfa_activo} correo={usuario.correo} alActivar={async () => {
          avisos.exito("Verificación en dos pasos activada. Ingrese de nuevo con su código.");
          sesionGuardada.limpiar();
          router.replace("/ingresar");
        }} recargar={recargar} />
      </div>
    </>
  );
}

function CambiarClave({ correo, alCambiar }: { correo: string; alCambiar: () => void }) {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const requisitos = requisitosClave(nueva, correo);
  return (
    <Tarjeta>
      <CabeceraTarjeta titulo="Cambiar contraseña" />
      <form
        className="flex flex-col gap-3 p-5"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          if (requisitos.some((r) => !r.ok)) return setError("La contraseña nueva no cumple los requisitos.");
          if (nueva !== confirmacion) return setError("Las dos contraseñas no coinciden.");
          setEnviando(true);
          try {
            const t = await api<Token>("/auth/cambiar-clave", { metodo: "POST", cuerpo: { clave_actual: actual, clave_nueva: nueva }, sinOrganizacion: true });
            sesionGuardada.guardarToken(t.access_token);
            setActual("");
            setNueva("");
            setConfirmacion("");
            alCambiar();
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setEnviando(false);
          }
        }}
      >
        <input type="text" autoComplete="username" value={correo} readOnly hidden />
        <Campo etiqueta="Contraseña actual"><Entrada type="password" autoComplete="current-password" value={actual} onChange={(e) => setActual(e.target.value)} required /></Campo>
        <Campo etiqueta="Contraseña nueva"><Entrada type="password" autoComplete="new-password" value={nueva} onChange={(e) => setNueva(e.target.value)} required /></Campo>
        <ul className="flex flex-col gap-1 text-[12.5px]">
          {requisitos.map((r) => <li key={r.texto} className={r.ok ? "text-ok" : "text-texto-3"}>{r.ok ? "✓" : "○"} {r.texto}</li>)}
        </ul>
        <Campo etiqueta="Repítala"><Entrada type="password" autoComplete="new-password" value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} required /></Campo>
        {error && <CajaError mensaje={error} />}
        <div><Boton type="submit" variante="primario" icono={<KeyRound />} cargando={enviando}>Cambiar contraseña</Boton></div>
      </form>
    </Tarjeta>
  );
}

function VerificacionDosPasos({ activa, correo, alActivar }: { activa: boolean; correo: string; alActivar: () => void; recargar: () => Promise<void> }) {
  const [config, setConfig] = useState<{ secreto: string; uri: string } | null>(null);
  const [codigo, setCodigo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  return (
    <Tarjeta className="xl:col-span-2">
      <CabeceraTarjeta titulo="Verificación en dos pasos" descripcion="Además de la contraseña, un código de 6 dígitos que cambia cada 30 segundos en su teléfono." />
      <div className="p-5">
        {activa ? (
          <Nota tono="ok" icono={<ShieldCheck />}>Está activa. Cada ingreso le pedirá el código de su aplicación de autenticación.</Nota>
        ) : !config ? (
          <div className="flex flex-wrap items-center gap-4">
            <span className="grid size-12 place-items-center rounded-xl bg-motor-suave text-motor"><Smartphone className="size-6" /></span>
            <p className="max-w-xl flex-1 text-[13px] text-texto-2">Necesita una aplicación como Google Authenticator, Microsoft Authenticator o Authy. Si su organización la exige para su rol, no podrá trabajar hasta activarla.</p>
            <Boton
              variante="acento"
              icono={<ShieldCheck />}
              cargando={enviando}
              onClick={async () => {
                setEnviando(true);
                setError(null);
                try {
                  setConfig(await api<{ secreto: string; uri: string }>("/auth/mfa/iniciar", { metodo: "POST", sinOrganizacion: true }));
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setEnviando(false);
                }
              }}
            >
              Activar
            </Boton>
          </div>
        ) : (
          <div className="grid gap-5 md:grid-cols-2">
            <div className="rounded-lg border border-line bg-canvas p-4 text-[13px] text-texto-2">
              <p className="font-medium text-titulo">1. Agregue la cuenta en su aplicación</p>
              <p className="mt-1">Elija «Ingresar clave de configuración» y escriba:</p>
              <p className="mt-2 rounded-md border border-line bg-surface px-3 py-2 text-center font-mono text-[15px] tracking-wider break-all text-titulo select-all">{config.secreto.match(/.{1,4}/g)?.join(" ")}</p>
              <p className="mt-1 text-[12px] text-texto-3">Cuenta: {correo} · tipo: basada en tiempo</p>
              <a href={config.uri} className="mt-2 inline-block text-[12.5px] font-medium text-marca underline">Abrir directamente en la aplicación del teléfono</a>
            </div>
            <form
              className="flex flex-col gap-3"
              onSubmit={async (e) => {
                e.preventDefault();
                setEnviando(true);
                setError(null);
                try {
                  await api("/auth/mfa/confirmar", { metodo: "POST", cuerpo: { codigo: codigo.replace(/\s/g, "") }, sinOrganizacion: true });
                  alActivar();
                } catch (err) {
                  setError((err as Error).message);
                  setEnviando(false);
                }
              }}
            >
              <p className="text-[13px] font-medium text-titulo">2. Escriba el código que muestra la aplicación</p>
              <Entrada inputMode="numeric" autoComplete="one-time-code" maxLength={7} value={codigo} onChange={(e) => setCodigo(e.target.value)} className="h-11 text-center font-mono text-lg tracking-[0.3em]" placeholder="000000" autoFocus />
              <div><Boton type="submit" variante="primario" icono={<ShieldCheck />} cargando={enviando} disabled={codigo.replace(/\s/g, "").length !== 6}>Confirmar y activar</Boton></div>
              <p className="text-[12px] text-texto-3">Al activarla se cierran sus sesiones y deberá ingresar de nuevo con el código.</p>
            </form>
          </div>
        )}
        {error && <div className="mt-3"><CajaError mensaje={error} /></div>}
      </div>
    </Tarjeta>
  );
}
