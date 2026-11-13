"use client";

import { Check, Copy, KeyRound } from "lucide-react";
import { type ReactNode, useState } from "react";

import { Boton, CajaError, Modal } from "@/components/ui/basicos";
import { Area, Campo } from "@/components/ui/campos";

/**
 * Confirmar una acción sensible con su motivo. El motivo queda en la auditoría: ARCA no suspende,
 * cierra, desactiva ni cambia accesos sin decir por qué.
 */
export function ModalMotivo({
  abierto,
  titulo,
  descripcion,
  boton,
  peligro,
  alCerrar,
  alConfirmar,
}: {
  abierto: boolean;
  titulo: string;
  descripcion?: ReactNode;
  boton: string;
  peligro?: boolean;
  alCerrar: () => void;
  alConfirmar: (motivo: string) => Promise<void>;
}) {
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const cerrar = () => (setMotivo(""), setError(null), alCerrar());
  async function confirmar() {
    setEnviando(true);
    setError(null);
    try {
      await alConfirmar(motivo.trim());
      setMotivo("");
      alCerrar();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Modal
      abierto={abierto}
      alCerrar={cerrar}
      titulo={titulo}
      descripcion={descripcion}
      pie={
        <>
          <Boton onClick={cerrar}>Cancelar</Boton>
          <Boton variante={peligro ? "peligro" : "primario"} cargando={enviando} disabled={motivo.trim().length < 5} onClick={confirmar}>
            {boton}
          </Boton>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Campo etiqueta="Motivo" requerido ayuda="Mínimo 5 caracteres. Queda en la auditoría.">
          <Area value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus />
        </Campo>
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}

/** Contraseña temporal recién generada: se muestra una única vez, con botón para copiarla. */
export function ClaveTemporal({ correo, clave }: { correo: string; clave: string }) {
  const [copiada, setCopiada] = useState(false);
  return (
    <div className="rounded-xl border border-aviso/30 bg-aviso-suave p-4 text-[13px] text-texto-2">
      <p className="flex items-center gap-2 font-semibold text-aviso">
        <KeyRound className="size-4" /> Contraseña temporal de {correo}
      </p>
      <div className="mt-2 flex items-center gap-2">
        <code className="flex-1 rounded-md border border-line bg-surface px-3 py-2 font-mono text-[15px] tracking-wide text-titulo select-all">{clave}</code>
        <Boton
          tamano="sm"
          icono={copiada ? <Check /> : <Copy />}
          onClick={async () => {
            await navigator.clipboard?.writeText(clave);
            setCopiada(true);
          }}
        >
          {copiada ? "Copiada" : "Copiar"}
        </Boton>
      </div>
      <p className="mt-2">Entréguela por un canal seguro. Se muestra una sola vez y la persona deberá cambiarla en su primer ingreso.</p>
    </div>
  );
}
