"use client";

import { Building2, CirclePause, CirclePlay, Pencil, Plus, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ClaveTemporal, ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, Codigo, EncabezadoPagina, Insignia, Modal, Nota, Tabla, Tarjeta, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { fecha } from "@/lib/formato";
import type { Organizacion, Verificacion } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

export default function Plataforma() {
  const avisos = useAvisos();
  const orgs = useDatos(() => api<Organizacion[]>("/plataforma/organizaciones", { sinOrganizacion: true }), []);
  const [nueva, setNueva] = useState(false);
  const [editar, setEditar] = useState<Organizacion | null>(null);
  const [estado, setEstado] = useState<Organizacion | null>(null);
  const [temporal, setTemporal] = useState<{ correo: string; clave: string } | null>(null);
  const [verificacion, setVerificacion] = useState<Verificacion | null>(null);

  return (
    <>
      <EncabezadoPagina
        titulo="Organizaciones"
        descripcion="Los clientes de ARCA. Usted las administra, pero no ve su contenido: cada una tiene sus datos aislados."
        acciones={
          <>
            <Boton icono={<ShieldCheck />} onClick={async () => setVerificacion(await api<Verificacion>("/plataforma/auditoria/verificar", { sinOrganizacion: true }))}>Verificar auditoría</Boton>
            <Boton variante="primario" icono={<Plus />} onClick={() => setNueva(true)}>Nueva organización</Boton>
          </>
        }
      />
      {verificacion && (
        <div className="mb-5"><Nota tono={verificacion.integra ? "ok" : "critico"}>{verificacion.integra ? `Auditoría de la plataforma íntegra: ${verificacion.revisados} eventos revisados.` : `ALERTA: ${verificacion.problema}`}</Nota></div>
      )}
      {temporal && <div className="mb-5"><ClaveTemporal correo={temporal.correo} clave={temporal.clave} /></div>}
      <Tarjeta>
        {orgs.cargando && !orgs.datos ? (
          <Cargando />
        ) : orgs.error ? (
          <div className="p-5"><CajaError mensaje={orgs.error} reintentar={orgs.recargar} /></div>
        ) : !orgs.datos?.length ? (
          <Vacio icono={<Building2 />} titulo="Todavía no hay organizaciones" descripcion="Cree la primera con su NIT y su administrador inicial." accion={<Boton variante="primario" icono={<Plus />} onClick={() => setNueva(true)}>Nueva organización</Boton>} />
        ) : (
          <Tabla>
            <thead><tr><th>Organización</th><th>Identificación</th><th>Límites del plan</th><th>Creada</th><th>Estado</th><th /></tr></thead>
            <tbody>
              {orgs.datos.map((o) => (
                <tr key={o.id}>
                  <td><span className="block font-semibold">{o.nombre}</span><span className="block text-texto-3">{o.razon_social}</span></td>
                  <td><Codigo>{o.tipo_identificacion} {o.identificacion}</Codigo></td>
                  <td>{Object.keys(o.limites).length ? Object.entries(o.limites).map(([k, v]) => `${v} ${k}`).join(" · ") : <span className="text-texto-3">Sin límites</span>}</td>
                  <td className="whitespace-nowrap">{fecha(o.creado_en)}</td>
                  <td><Insignia tono={o.estado === "activa" ? "ok" : "critico"} punto>{o.estado === "activa" ? "Activa" : "Suspendida"}</Insignia>{o.motivo_estado && <span className="block text-[12px] text-texto-3">{o.motivo_estado}</span>}</td>
                  <td className="whitespace-nowrap">
                    <Boton tamano="sm" variante="fantasma" icono={<Pencil />} onClick={() => setEditar(o)}>Editar</Boton>
                    <Boton tamano="sm" variante="fantasma" icono={o.estado === "activa" ? <CirclePause /> : <CirclePlay />} onClick={() => setEstado(o)}>{o.estado === "activa" ? "Suspender" : "Reactivar"}</Boton>
                  </td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </Tarjeta>
      {nueva && (
        <ModalOrganizacion
          alCerrar={() => setNueva(false)}
          alGuardar={(correo, clave) => {
            setNueva(false);
            setTemporal(clave ? { correo, clave } : null);
            avisos.exito(clave ? "Organización creada. Entréguele al administrador su contraseña temporal." : "Organización creada. El administrador ya tenía cuenta en ARCA.");
            void orgs.recargar();
          }}
        />
      )}
      {editar && <ModalEditar org={editar} alCerrar={() => setEditar(null)} alGuardar={() => (setEditar(null), avisos.exito("Organización actualizada."), void orgs.recargar())} />}
      <ModalMotivo
        abierto={!!estado}
        titulo={estado ? `${estado.estado === "activa" ? "Suspender" : "Reactivar"} ${estado.nombre}` : ""}
        descripcion={estado?.estado === "activa" ? "Sus usuarios dejarán de entrar. Nada se borra: sus datos y su auditoría se conservan." : "Sus usuarios vuelven a entrar."}
        boton={estado?.estado === "activa" ? "Suspender" : "Reactivar"}
        peligro={estado?.estado === "activa"}
        alCerrar={() => setEstado(null)}
        alConfirmar={async (motivo) => {
          await api(`/plataforma/organizaciones/${estado!.id}/${estado!.estado === "activa" ? "suspender" : "reactivar"}`, { metodo: "POST", cuerpo: { motivo }, sinOrganizacion: true });
          avisos.exito("Estado actualizado.");
          await orgs.recargar();
        }}
      />
    </>
  );
}

function Limites({ usuarios, proyectos, alCambiar }: { usuarios: string; proyectos: string; alCambiar: (u: string, p: string) => void }) {
  return (
    <>
      <Campo etiqueta="Límite de usuarios" ayuda="Vacío = sin límite"><Entrada type="number" min={1} value={usuarios} onChange={(e) => alCambiar(e.target.value, proyectos)} /></Campo>
      <Campo etiqueta="Límite de proyectos" ayuda="Vacío = sin límite"><Entrada type="number" min={1} value={proyectos} onChange={(e) => alCambiar(usuarios, e.target.value)} /></Campo>
    </>
  );
}

const aLimites = (u: string, p: string) => Object.fromEntries([["usuarios", u], ["proyectos", p]].filter(([, v]) => v.trim()).map(([k, v]) => [k, Number(v)]));

function ModalOrganizacion({ alCerrar, alGuardar }: { alCerrar: () => void; alGuardar: (correo: string, clave: string | null) => void }) {
  const [d, setD] = useState({ nombre: "", razon_social: "", identificacion: "", correo: "", nombre_admin: "" });
  const [lim, setLim] = useState({ u: "", p: "" });
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const cambiar = (k: keyof typeof d, v: string) => setD({ ...d, [k]: v });
  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo="Nueva organización"
      descripcion="Se crean sus roles base y su administrador inicial."
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={!d.nombre || !d.razon_social || !d.identificacion || !d.correo || d.nombre_admin.trim().length < 3}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                const r = await api<{ administrador_correo: string; clave_temporal: string | null }>("/plataforma/organizaciones", {
                  metodo: "POST",
                  sinOrganizacion: true,
                  cuerpo: { nombre: d.nombre, razon_social: d.razon_social, identificacion: d.identificacion, limites: aLimites(lim.u, lim.p), administrador: { correo: d.correo, nombre_completo: d.nombre_admin } },
                });
                alGuardar(r.administrador_correo, r.clave_temporal);
              } catch (e) {
                setError((e as Error).message);
                setEnviando(false);
              }
            }}
          >
            Crear organización
          </Boton>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta="Nombre" requerido><Entrada value={d.nombre} onChange={(e) => cambiar("nombre", e.target.value)} autoFocus /></Campo>
        <Campo etiqueta="Razón social" requerido><Entrada value={d.razon_social} onChange={(e) => cambiar("razon_social", e.target.value)} /></Campo>
        <Campo etiqueta="NIT" requerido ayuda="Con dígito de verificación: 900123456-8" className="sm:col-span-2"><Entrada value={d.identificacion} onChange={(e) => cambiar("identificacion", e.target.value)} /></Campo>
        <Limites usuarios={lim.u} proyectos={lim.p} alCambiar={(u, p) => setLim({ u, p })} />
        <p className="text-[13px] font-semibold text-titulo sm:col-span-2">Administrador inicial</p>
        <Campo etiqueta="Correo" requerido><Entrada type="email" value={d.correo} onChange={(e) => cambiar("correo", e.target.value)} /></Campo>
        <Campo etiqueta="Nombre completo" requerido><Entrada value={d.nombre_admin} onChange={(e) => cambiar("nombre_admin", e.target.value)} /></Campo>
        {error && <div className="sm:col-span-2"><CajaError mensaje={error} /></div>}
      </div>
    </Modal>
  );
}

function ModalEditar({ org, alCerrar, alGuardar }: { org: Organizacion; alCerrar: () => void; alGuardar: () => void }) {
  const [nombre, setNombre] = useState(org.nombre);
  const [razon, setRazon] = useState(org.razon_social);
  const [lim, setLim] = useState({ u: org.limites.usuarios ? String(org.limites.usuarios) : "", p: org.limites.proyectos ? String(org.limites.proyectos) : "" });
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo={`Editar ${org.nombre}`}
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
                await api(`/plataforma/organizaciones/${org.id}`, { metodo: "PATCH", sinOrganizacion: true, cuerpo: { nombre, razon_social: razon, limites: aLimites(lim.u, lim.p), motivo: motivo.trim() } });
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
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta="Nombre"><Entrada value={nombre} onChange={(e) => setNombre(e.target.value)} /></Campo>
        <Campo etiqueta="Razón social"><Entrada value={razon} onChange={(e) => setRazon(e.target.value)} /></Campo>
        <Limites usuarios={lim.u} proyectos={lim.p} alCambiar={(u, p) => setLim({ u, p })} />
        <Campo etiqueta="Motivo" requerido className="sm:col-span-2"><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        {error && <div className="sm:col-span-2"><CajaError mensaje={error} /></div>}
      </div>
    </Modal>
  );
}
