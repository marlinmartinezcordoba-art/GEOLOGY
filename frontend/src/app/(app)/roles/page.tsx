"use client";

import { Lock, Pencil, Plus, ShieldHalf } from "lucide-react";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, EncabezadoPagina, Insignia, Modal, Nota, Tarjeta } from "@/components/ui/basicos";
import { Area, Campo, Casilla, Entrada } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { NOMBRE_PERMISO } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { Rol } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

export default function Roles() {
  const { organizacion } = useSesion();
  const avisos = useAvisos();
  const roles = useDatos(() => api<Rol[]>("/roles"), []);
  const catalogo = useDatos(() => api<string[]>("/roles/permisos"), []);
  const [editar, setEditar] = useState<Rol | "nuevo" | null>(null);

  return (
    <>
      <EncabezadoPagina
        titulo="Roles y permisos"
        descripcion="Se niega todo lo que el rol no permite. Los roles base no se editan: cree uno propio cuando necesite otra combinación."
        acciones={<Boton variante="primario" icono={<Plus />} onClick={() => setEditar("nuevo")}>Nuevo rol</Boton>}
      />
      <div className="mb-5"><Nota tono="info">Matriz inicial propuesta a partir de los perfiles de trabajo de GEOLOGY. Pendiente de aprobación formal (decisión D-07).</Nota></div>
      {roles.cargando && !roles.datos ? (
        <Cargando />
      ) : roles.error ? (
        <CajaError mensaje={roles.error} reintentar={roles.recargar} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {roles.datos?.map((r) => {
            const propio = organizacion?.rol === r.nombre;
            return (
              <Tarjeta key={r.id} className="flex flex-col p-4">
                <div className="flex items-start gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-marca-suave text-marca"><ShieldHalf className="size-5" /></span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-titulo">{r.nombre}</p>
                    <p className="text-[12.5px] text-texto-3">{r.descripcion || "Sin descripción"}</p>
                  </div>
                  {r.es_base ? <Insignia tono="neutro"><Lock className="size-3" /> Base</Insignia> : <Insignia tono="motor">Propio</Insignia>}
                </div>
                <ul className="mt-3 flex flex-1 flex-col gap-1 text-[12.5px] text-texto-2">
                  {r.permisos.map((p) => <li key={p}>✓ {NOMBRE_PERMISO[p] ?? p}</li>)}
                  {!r.permisos.length && <li className="text-texto-3">Sin permisos</li>}
                </ul>
                {!r.es_base && (
                  <div className="mt-3 border-t border-line pt-3">
                    {propio ? <span className="text-[12px] text-texto-3">Es su rol: no puede editarlo (segregación de funciones).</span> : <Boton tamano="sm" icono={<Pencil />} onClick={() => setEditar(r)}>Editar</Boton>}
                  </div>
                )}
              </Tarjeta>
            );
          })}
        </div>
      )}
      {editar && (
        <ModalRol
          rol={editar === "nuevo" ? null : editar}
          catalogo={catalogo.datos ?? []}
          alCerrar={() => setEditar(null)}
          alGuardar={() => (setEditar(null), avisos.exito("Rol guardado."), void roles.recargar())}
        />
      )}
    </>
  );
}

function ModalRol({ rol, catalogo, alCerrar, alGuardar }: { rol: Rol | null; catalogo: string[]; alCerrar: () => void; alGuardar: () => void }) {
  const [nombre, setNombre] = useState(rol?.nombre ?? "");
  const [descripcion, setDescripcion] = useState(rol?.descripcion ?? "");
  const [permisos, setPermisos] = useState<string[]>(rol?.permisos ?? []);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const listo = rol ? motivo.trim().length >= 5 : nombre.trim().length >= 3;
  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo={rol ? `Editar rol · ${rol.nombre}` : "Nuevo rol"}
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={!listo}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                if (rol) await api(`/roles/${rol.id}`, { metodo: "PATCH", cuerpo: { descripcion, permisos, motivo: motivo.trim() } });
                else await api("/roles", { metodo: "POST", cuerpo: { nombre: nombre.trim(), descripcion, permisos } });
                alGuardar();
              } catch (e) {
                setError((e as Error).message);
                setEnviando(false);
              }
            }}
          >
            Guardar
          </Boton>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {!rol && <Campo etiqueta="Nombre" requerido><Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus placeholder="Coordinación de calidad" /></Campo>}
        <Campo etiqueta="Descripción"><Entrada value={descripcion} onChange={(e) => setDescripcion(e.target.value)} /></Campo>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-[13px] font-medium text-texto-2">Permisos</legend>
          {catalogo.map((p) => (
            <Casilla key={p} etiqueta={<span>{NOMBRE_PERMISO[p] ?? p} <span className="font-mono text-[11px] text-texto-3">{p}</span></span>} checked={permisos.includes(p)} onChange={(e) => setPermisos(e.target.checked ? [...permisos, p] : permisos.filter((x) => x !== p))} />
          ))}
        </fieldset>
        {rol && <Campo etiqueta="Motivo" requerido><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>}
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}
