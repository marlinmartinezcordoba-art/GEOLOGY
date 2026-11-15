"use client";

import { KeyRound, MoreHorizontal, ShieldCheck, UserPlus, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { ClaveTemporal, ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, EncabezadoPagina, Insignia, Modal, Tabla, Tarjeta, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Casilla, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { useSesion } from "@/lib/sesion";
import type { Miembro, Proyecto, Rol } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

type Accion = { tipo: "desactivar" | "reactivar" | "revocar-sesiones" | "restablecer-clave"; miembro: Miembro };

const TEXTOS: Record<Accion["tipo"], { titulo: string; boton: string; peligro?: boolean; descripcion: string }> = {
  desactivar: { titulo: "Quitar el acceso", boton: "Desactivar", peligro: true, descripcion: "La persona deja de entrar a esta organización. Su historial se conserva." },
  reactivar: { titulo: "Devolver el acceso", boton: "Reactivar", descripcion: "La persona vuelve a entrar con su rol anterior." },
  "revocar-sesiones": { titulo: "Cerrar sus sesiones abiertas", boton: "Cerrar sesiones", descripcion: "Útil si perdió un equipo o se sospecha de un acceso indebido." },
  "restablecer-clave": { titulo: "Restablecer contraseña", boton: "Generar temporal", descripcion: "Se genera una contraseña temporal de un solo uso y se cierran sus sesiones." },
};

/** Alcance por proyecto: todos o algunos. */
function Alcance({ proyectos, valor, alCambiar }: { proyectos: Proyecto[]; valor: string[] | null; alCambiar: (v: string[] | null) => void }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[13px] font-medium text-texto-2">Alcance</legend>
      <Casilla etiqueta="Todos los proyectos de la organización" checked={valor === null} onChange={(e) => alCambiar(e.target.checked ? null : [])} />
      {valor !== null && (
        <div className="ml-6 flex max-h-40 flex-col gap-1.5 overflow-y-auto rounded-lg border border-line p-2.5">
          {!proyectos.length && <span className="text-[12.5px] text-texto-3">No hay proyectos todavía.</span>}
          {proyectos.map((p) => (
            <Casilla key={p.id} etiqueta={`${p.codigo} · ${p.nombre}`} checked={valor.includes(p.id)} onChange={(e) => alCambiar(e.target.checked ? [...valor, p.id] : valor.filter((x) => x !== p.id))} />
          ))}
        </div>
      )}
    </fieldset>
  );
}

function MenuFila({ miembro, propio, alElegir, alEditar }: { miembro: Miembro; propio: boolean; alElegir: (a: Accion) => void; alEditar: () => void }) {
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const cerrar = (e: MouseEvent) => !caja.current?.contains(e.target as Node) && setAbierto(false);
    document.addEventListener("mousedown", cerrar);
    return () => document.removeEventListener("mousedown", cerrar);
  }, [abierto]);
  if (propio) return <span className="text-[12px] text-texto-3">Usted</span>;
  const opcion = (texto: string, fn: () => void) => (
    <button role="menuitem" onClick={() => (setAbierto(false), fn())} className="block w-full px-3.5 py-2 text-left text-[13px] text-texto-2 hover:bg-marca-suave hover:text-marca">{texto}</button>
  );
  return (
    <div className="relative" ref={caja}>
      <button className="grid size-8 place-items-center rounded-md text-texto-3 hover:bg-surface-muted" onClick={() => setAbierto(!abierto)} aria-label={`Acciones para ${miembro.nombre_completo}`}>
        <MoreHorizontal className="size-4" />
      </button>
      {abierto && (
        <div role="menu" className="absolute right-0 z-20 mt-1 w-56 animate-subir overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-md">
          {opcion("Cambiar rol o alcance", alEditar)}
          {opcion("Cerrar sus sesiones", () => alElegir({ tipo: "revocar-sesiones", miembro }))}
          {opcion("Restablecer contraseña", () => alElegir({ tipo: "restablecer-clave", miembro }))}
          {miembro.activa ? opcion("Desactivar acceso", () => alElegir({ tipo: "desactivar", miembro })) : opcion("Reactivar acceso", () => alElegir({ tipo: "reactivar", miembro }))}
        </div>
      )}
    </div>
  );
}

export default function Usuarios() {
  const { usuario } = useSesion();
  const avisos = useAvisos();
  const miembros = useDatos(() => api<Miembro[]>("/usuarios"), []);
  const roles = useDatos(() => api<Rol[]>("/roles"), []);
  const proyectos = useDatos(() => api<Proyecto[]>("/proyectos").catch(() => [] as Proyecto[]), []);
  const [nuevo, setNuevo] = useState(false);
  const [editar, setEditar] = useState<Miembro | null>(null);
  const [accion, setAccion] = useState<Accion | null>(null);
  const [temporal, setTemporal] = useState<{ correo: string; clave: string } | null>(null);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("nuevo")) setNuevo(true);
  }, []);
  const nombreProyecto = useMemo(() => Object.fromEntries((proyectos.datos ?? []).map((p) => [p.id, p.codigo])), [proyectos.datos]);

  return (
    <>
      <EncabezadoPagina
        titulo="Usuarios"
        descripcion="Quién entra a la organización, con qué rol y a qué proyectos. Nadie cambia su propio acceso."
        acciones={<Boton variante="primario" icono={<UserPlus />} onClick={() => setNuevo(true)}>Agregar persona</Boton>}
      />
      {temporal && (
        <div className="mb-5">
          <ClaveTemporal correo={temporal.correo} clave={temporal.clave} />
        </div>
      )}
      <Tarjeta>
        {miembros.cargando && !miembros.datos ? (
          <Cargando />
        ) : miembros.error ? (
          <div className="p-5"><CajaError mensaje={miembros.error} reintentar={miembros.recargar} /></div>
        ) : !miembros.datos?.length ? (
          <Vacio icono={<Users />} titulo="Sin personas" />
        ) : (
          <Tabla>
            <thead>
              <tr><th>Persona</th><th>Rol</th><th>Alcance</th><th>Seguridad</th><th>Estado</th><th className="w-12" /></tr>
            </thead>
            <tbody>
              {miembros.datos.map((m) => (
                <tr key={m.usuario_id}>
                  <td>
                    <span className="block font-semibold text-texto">{m.nombre_completo}</span>
                    <span className="block text-texto-3">{m.correo}</span>
                  </td>
                  <td>{m.rol}</td>
                  <td>{m.proyectos === null ? <span className="text-texto-2">Todos los proyectos</span> : <span className="flex flex-wrap gap-1">{m.proyectos.map((p) => <Insignia key={p} tono="marca">{nombreProyecto[p] ?? p.slice(0, 8)}</Insignia>)}{!m.proyectos.length && "Ninguno"}</span>}</td>
                  <td>
                    <span className="flex flex-wrap gap-1">
                      {m.mfa_activo ? <Insignia tono="ok"><ShieldCheck className="size-3" /> Dos pasos</Insignia> : <Insignia tono="neutro">Solo contraseña</Insignia>}
                      {m.bloqueado && <Insignia tono="critico"><KeyRound className="size-3" /> Bloqueada</Insignia>}
                    </span>
                  </td>
                  <td><Insignia tono={m.activa ? "ok" : "neutro"} punto>{m.activa ? "Activa" : "Desactivada"}</Insignia></td>
                  <td><MenuFila miembro={m} propio={m.usuario_id === usuario.id} alElegir={setAccion} alEditar={() => setEditar(m)} /></td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </Tarjeta>

      {nuevo && (
        <ModalPersona
          roles={roles.datos ?? []}
          proyectos={proyectos.datos ?? []}
          alCerrar={() => setNuevo(false)}
          alGuardar={(correo, clave, enviada) => {
            setNuevo(false);
            setTemporal(clave ? { correo, clave } : null);
            avisos.exito(enviada ? "Persona agregada. Se le envió la contraseña temporal por correo." : clave ? "Persona agregada. Entréguele su contraseña temporal." : "La persona ya tenía cuenta en ARCA: entra con su contraseña de siempre.");
            void miembros.recargar();
          }}
        />
      )}
      {editar && (
        <ModalAcceso
          miembro={editar}
          roles={roles.datos ?? []}
          proyectos={proyectos.datos ?? []}
          alCerrar={() => setEditar(null)}
          alGuardar={() => (setEditar(null), avisos.exito("Acceso actualizado."), void miembros.recargar())}
        />
      )}
      <ModalMotivo
        abierto={!!accion}
        titulo={accion ? `${TEXTOS[accion.tipo].titulo} · ${accion.miembro.nombre_completo}` : ""}
        descripcion={accion && TEXTOS[accion.tipo].descripcion}
        boton={accion ? TEXTOS[accion.tipo].boton : ""}
        peligro={accion ? TEXTOS[accion.tipo].peligro : false}
        alCerrar={() => setAccion(null)}
        alConfirmar={async (motivo) => {
          const a = accion!;
          const r = await api<{ clave_temporal?: string | null; enviada_por_correo?: boolean } | null>(`/usuarios/${a.miembro.usuario_id}/${a.tipo}`, { metodo: "POST", cuerpo: { motivo } });
          if (r?.clave_temporal) setTemporal({ correo: a.miembro.correo, clave: r.clave_temporal });
          avisos.exito(r?.enviada_por_correo ? "Listo. La contraseña temporal se le envió por correo. Quedó en la auditoría." : "Listo. Quedó en la auditoría.");
          await miembros.recargar();
        }}
      />
    </>
  );
}

function ModalPersona({ roles, proyectos, alCerrar, alGuardar }: { roles: Rol[]; proyectos: Proyecto[]; alCerrar: () => void; alGuardar: (correo: string, clave: string | null, enviada: boolean) => void }) {
  const [d, setD] = useState({ correo: "", nombre_completo: "", rol_id: "" });
  const [alcance, setAlcance] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo="Agregar persona"
      descripcion="Si la persona ya tiene cuenta en ARCA (en otra organización), se reutiliza: no se le crea otra."
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={!d.correo || d.nombre_completo.trim().length < 3 || !d.rol_id}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                const r = await api<{ clave_temporal: string | null; enviada_por_correo?: boolean }>("/usuarios", { metodo: "POST", cuerpo: { ...d, proyectos: alcance } });
                alGuardar(d.correo, r.clave_temporal, !!r.enviada_por_correo);
              } catch (e) {
                setError((e as Error).message);
                setEnviando(false);
              }
            }}
          >
            Agregar
          </Boton>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta="Correo" requerido><Entrada type="email" value={d.correo} onChange={(e) => setD({ ...d, correo: e.target.value })} autoFocus /></Campo>
        <Campo etiqueta="Nombre completo" requerido><Entrada value={d.nombre_completo} onChange={(e) => setD({ ...d, nombre_completo: e.target.value })} /></Campo>
        <Campo etiqueta="Rol" requerido className="sm:col-span-2" ayuda={roles.find((r) => r.id === d.rol_id)?.descripcion}>
          <Selector value={d.rol_id} onChange={(e) => setD({ ...d, rol_id: e.target.value })}>
            <option value="">Elija…</option>
            {roles.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
          </Selector>
        </Campo>
        <div className="sm:col-span-2"><Alcance proyectos={proyectos} valor={alcance} alCambiar={setAlcance} /></div>
        {error && <div className="sm:col-span-2"><CajaError mensaje={error} /></div>}
      </div>
    </Modal>
  );
}

function ModalAcceso({ miembro, roles, proyectos, alCerrar, alGuardar }: { miembro: Miembro; roles: Rol[]; proyectos: Proyecto[]; alCerrar: () => void; alGuardar: () => void }) {
  const [rolId, setRolId] = useState(miembro.rol_id);
  const [alcance, setAlcance] = useState<string[] | null>(miembro.proyectos);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo={`Acceso de ${miembro.nombre_completo}`}
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={motivo.trim().length < 5}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                await api(`/usuarios/${miembro.usuario_id}`, { metodo: "PATCH", cuerpo: { rol_id: rolId, proyectos: alcance, motivo: motivo.trim() } });
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
        <Campo etiqueta="Rol" ayuda={roles.find((r) => r.id === rolId)?.descripcion}>
          <Selector value={rolId} onChange={(e) => setRolId(e.target.value)}>
            {roles.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
          </Selector>
        </Campo>
        <Alcance proyectos={proyectos} valor={alcance} alCambiar={setAlcance} />
        <Campo etiqueta="Motivo" requerido ayuda="Queda en la auditoría."><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}

