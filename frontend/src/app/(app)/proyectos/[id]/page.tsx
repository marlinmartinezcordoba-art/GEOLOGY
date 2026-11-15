"use client";

import { CheckCircle2, CircleSlash, History, MapPin, Pencil, Play, RotateCcw, UserPlus, Users } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ModalMotivo } from "@/components/ui/acciones";
import { useAvisos } from "@/components/ui/avisos";
import { Boton, CabeceraTarjeta, CajaError, Cargando, Codigo, Datos, EncabezadoPagina, Insignia, Modal, Nota, Pestanas, Tabla, Tarjeta, Vacio } from "@/components/ui/basicos";
import { Campo, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { NOMBRE_ESTADO, TONO_ESTADO } from "@/lib/estados";
import { fecha, fechaHora, numero } from "@/lib/formato";
import { nombreUnidad, PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { MiembroProyecto, Persona, Proyecto, Sede, VersionProyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

import { FormularioProyecto } from "../formulario";
import { Clasificacion } from "./clasificacion";
import { Descripciones } from "./descripciones";
import { Digitalizacion } from "./digitalizacion";
import { Disposicion } from "./disposicion";
import { Entregables } from "./entregables";
import { Flujo } from "./flujo";
import { HojasControl } from "./hojas";
import { Inspeccion } from "./inspeccion";
import { Instrumentos } from "./instrumentos";
import { Inventario } from "./inventario";
import { Productividad } from "./productividad";
import { Transferencias } from "./transferencias";

type Pestana = "resumen" | "productividad" | "instrumentos" | "clasificacion" | "transferencias" | "disposicion" | "hojas" | "descripcion" | "flujo" | "inventario" | "digitalizacion" | "entregables" | "sedes" | "equipo" | "versiones" | "inspeccion";
type Transicion = { ruta: "activar" | "cerrar" | "reabrir"; titulo: string; boton: string; peligro?: boolean; descripcion: string };

const TRANSICIONES: Record<string, Transicion[]> = {
  borrador: [{ ruta: "activar", titulo: "Activar el proyecto", boton: "Activar", descripcion: "Desde ahora el equipo puede operar el proyecto." }],
  activo: [{ ruta: "cerrar", titulo: "Cerrar el proyecto", boton: "Cerrar proyecto", peligro: true, descripcion: "Un proyecto cerrado no se edita. Solo se reabre con motivo." }],
  cerrado: [{ ruta: "reabrir", titulo: "Reabrir el proyecto", boton: "Reabrir", descripcion: "La reapertura queda registrada como versión nueva." }],
};

export default function DetalleProyecto() {
  const { id } = useParams<{ id: string }>();
  const { puede } = useSesion();
  const avisos = useAvisos();
  const gestiona = puede(PERMISOS.proyectos);
  const proyecto = useDatos(() => api<Proyecto>(`/proyectos/${id}`), [id]);
  const sedes = useDatos(() => api<Sede[]>(`/proyectos/${id}/sedes`), [id]);
  const procesosLote = useDatos(() => api<{ lote: string; isadg: boolean }[]>(`/proyectos/${id}/procesos-por-lote`).catch(() => []), [id]);
  const conIsadg = (procesosLote.datos ?? []).some((l) => l.isadg);
  const equipo = useDatos(() => api<MiembroProyecto[]>(`/proyectos/${id}/equipo`), [id]);
  const versiones = useDatos(() => api<VersionProyecto[]>(`/proyectos/${id}/versiones`), [id]);
  const personas = useDatos(() => api<Persona[]>("/usuarios/directorio").catch(() => [] as Persona[]), []);
  const [pestana, setPestana] = useState<Pestana>("resumen");
  const [editar, setEditar] = useState(false);
  const [transicion, setTransicion] = useState<Transicion | null>(null);
  const [nuevaSede, setNuevaSede] = useState(false);
  const [nuevoMiembro, setNuevoMiembro] = useState(false);

  const p = proyecto.datos;
  if (proyecto.cargando && !p) return <Cargando />;
  if (proyecto.error || !p) return <CajaError mensaje={proyecto.error ?? "El proyecto no existe"} reintentar={proyecto.recargar} />;

  const nombreDe = (usuarioId: string | null) => {
    if (!usuarioId) return "Sin asignar";
    const persona = personas.datos?.find((x) => x.usuario_id === usuarioId);
    return persona ? persona.nombre_completo : `Persona ${usuarioId.slice(0, 8)}`;
  };
  const recargarTodo = () => Promise.all([proyecto.recargar(), sedes.recargar(), equipo.recargar(), versiones.recargar()]);
  const faltan = [
    !p.fecha_inicio && "fecha de inicio",
    !p.fecha_fin && "fecha de fin",
    !Object.keys(p.metas).length && "metas",
    !p.responsable_id && "responsable",
    !sedes.datos?.some((s) => s.activa) && "una sede",
  ].filter(Boolean) as string[];

  return (
    <>
      <EncabezadoPagina
        volver={{ href: "/proyectos", texto: "Proyectos" }}
        titulo={
          <span className="flex flex-wrap items-center gap-3">
            {p.nombre}
            <Insignia tono={TONO_ESTADO[p.estado]} punto>{NOMBRE_ESTADO[p.estado]}</Insignia>
          </span>
        }
        descripcion={<><Codigo>{p.codigo}</Codigo> · {p.entidad_cliente} · versión {p.version}</>}
        acciones={
          gestiona && (
            <>
              {p.estado !== "cerrado" && <Boton icono={<Pencil />} onClick={() => setEditar(true)}>Editar alcance</Boton>}
              {TRANSICIONES[p.estado].map((t) => (
                <Boton key={t.ruta} variante={t.peligro ? "peligro" : "primario"} icono={t.ruta === "activar" ? <Play /> : t.ruta === "cerrar" ? <CircleSlash /> : <RotateCcw />} onClick={() => setTransicion(t)}>
                  {t.boton}
                </Boton>
              ))}
            </>
          )
        }
      />

      {p.estado === "borrador" && faltan.length > 0 && (
        <div className="mb-5">
          <Nota tono="aviso">Para activarlo le falta: {faltan.join(", ")}.</Nota>
        </div>
      )}

      <Tarjeta>
        <div className="px-5 pt-2">
          <Pestanas
            valor={pestana}
            alCambiar={setPestana}
            opciones={[
              { valor: "resumen", etiqueta: "Resumen" },
              ...(puede(PERMISOS.productividadLeer) ? [{ valor: "productividad" as const, etiqueta: "Productividad" }] : []),
              ...(puede(PERMISOS.instrumentosLeer) ? [{ valor: "instrumentos" as const, etiqueta: "TRD · TVD · CCD" }] : []),
              ...(puede(PERMISOS.inventarioLeer)
                ? [
                    { valor: "flujo" as const, etiqueta: "Flujo automático" },
                    { valor: "inventario" as const, etiqueta: "Inventario FUID" },
                    { valor: "clasificacion" as const, etiqueta: "Clasificación" },
                    { valor: "hojas" as const, etiqueta: "Hoja de control" },
                    ...(conIsadg ? [{ valor: "descripcion" as const, etiqueta: "Descripción ISAD(G)" }] : []),
                    { valor: "transferencias" as const, etiqueta: "Transferencias" },
                    { valor: "disposicion" as const, etiqueta: "Disposición final" },
                    { valor: "digitalizacion" as const, etiqueta: "Digitalización y calidad" },
                    { valor: "inspeccion" as const, etiqueta: "Calidad por lote" },
                    { valor: "entregables" as const, etiqueta: "Entregables" },
                  ]
                : []),
              { valor: "sedes", etiqueta: `Sedes (${sedes.datos?.length ?? 0})` },
              { valor: "equipo", etiqueta: `Equipo (${equipo.datos?.length ?? 0})` },
              { valor: "versiones", etiqueta: `Versiones (${versiones.datos?.length ?? 0})` },
            ]}
          />
        </div>

        {pestana === "resumen" && (
          <div className="grid gap-6 p-5 lg:grid-cols-[1.4fr_1fr]">
            <div className="flex flex-col gap-5">
              <Datos
                filas={[
                  ["Entidad cliente", p.entidad_cliente],
                  ["Número de contrato", p.numero_contrato],
                  ["Fecha de inicio", fecha(p.fecha_inicio)],
                  ["Fecha de fin", fecha(p.fecha_fin)],
                  ["Responsable", nombreDe(p.responsable_id)],
                  ["Creado", fecha(p.creado_en)],
                ]}
              />
              <div>
                <p className="text-xs text-texto-3">Objeto</p>
                <p className="mt-0.5 text-[13.5px] whitespace-pre-line text-texto">{p.objeto || "—"}</p>
              </div>
              {p.motivo_estado && <Nota tono="info">Último cambio de estado: {p.motivo_estado}</Nota>}
            </div>
            <div>
              <p className="mb-2 text-[13px] font-semibold text-titulo">Metas contratadas</p>
              {Object.keys(p.metas).length ? (
                <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                  {Object.entries(p.metas).map(([u, c]) => (
                    <li key={u} className="flex items-center justify-between rounded-lg border border-line px-3.5 py-2.5">
                      <span className="text-[13px] text-texto-2">{nombreUnidad(u)}</span>
                      <span className="tabular text-lg font-bold text-titulo">{numero(c)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] text-texto-3">Sin metas definidas.</p>
              )}
              <p className="mt-2 text-[12px] text-texto-3">El avance real contra estas metas llegará con el tablero de producción (M24), calculado de los eventos operativos.</p>
            </div>
          </div>
        )}

        {pestana === "productividad" && <Productividad proyecto={p} />}
        {pestana === "instrumentos" && <Instrumentos proyecto={p} />}
        {pestana === "inventario" && <Inventario proyecto={p} />}
        {pestana === "clasificacion" && <Clasificacion proyecto={p} />}
        {pestana === "hojas" && <HojasControl proyecto={p} />}
        {pestana === "flujo" && <Flujo proyecto={p} />}
        {pestana === "descripcion" && <Descripciones proyecto={p} />}
        {pestana === "transferencias" && <Transferencias proyecto={p} />}
        {pestana === "disposicion" && <Disposicion proyecto={p} />}
        {pestana === "digitalizacion" && <Digitalizacion proyecto={p} />}
        {pestana === "inspeccion" && <Inspeccion proyecto={p} />}
        {pestana === "entregables" && <Entregables proyecto={p} />}

        {pestana === "sedes" && (
          <>
            {gestiona && p.estado !== "cerrado" && (
              <div className="flex justify-end px-5 pt-4"><Boton icono={<MapPin />} onClick={() => setNuevaSede(true)}>Agregar sede</Boton></div>
            )}
            {!sedes.datos?.length ? (
              <Vacio icono={<MapPin />} titulo="Sin sedes" descripcion="Registre dónde se ejecuta el proyecto: archivo central, bodega, sede regional." />
            ) : (
              <Tabla className="mt-2">
                <thead><tr><th>Sede</th><th>Ciudad</th><th>Dirección</th><th>Estado</th></tr></thead>
                <tbody>
                  {sedes.datos.map((s) => (
                    <tr key={s.id}><td className="font-semibold">{s.nombre}</td><td>{s.ciudad || "—"}</td><td>{s.direccion || "—"}</td><td><Insignia tono={s.activa ? "ok" : "neutro"} punto>{s.activa ? "Activa" : "Inactiva"}</Insignia></td></tr>
                  ))}
                </tbody>
              </Tabla>
            )}
          </>
        )}

        {pestana === "equipo" && (
          <>
            {gestiona && p.estado !== "cerrado" && (
              <div className="flex justify-end px-5 pt-4"><Boton icono={<UserPlus />} onClick={() => setNuevoMiembro(true)}>Asignar persona</Boton></div>
            )}
            {!equipo.datos?.length ? (
              <Vacio icono={<Users />} titulo="Sin equipo asignado" descripcion="Asigne a las personas que trabajarán en el proyecto y su función (por ejemplo: hoja de control, descripción, calidad)." />
            ) : (
              <Tabla className="mt-2">
                <thead><tr><th>Persona</th><th>Función</th><th>Estado</th></tr></thead>
                <tbody>
                  {equipo.datos.map((m) => (
                    <tr key={m.id}><td className="font-semibold">{nombreDe(m.usuario_id)}</td><td>{m.funcion || "—"}</td><td><Insignia tono={m.activo ? "ok" : "neutro"} punto>{m.activo ? "Activo" : "Inactivo"}</Insignia></td></tr>
                  ))}
                </tbody>
              </Tabla>
            )}
          </>
        )}

        {pestana === "versiones" && (
          <ol className="flex flex-col gap-3 p-5">
            {[...(versiones.datos ?? [])].reverse().map((v) => (
              <li key={v.version} className="flex gap-3 rounded-xl border border-line p-3.5">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-marca-suave font-mono text-[13px] font-semibold text-marca">v{v.version}</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-texto">{v.motivo}</span>
                  <span className="block text-[12.5px] text-texto-3">{fechaHora(v.creado_en)} · {nombreDe(v.creado_por)} · estado {String(v.instantanea.estado)}</span>
                  <span className="mt-1.5 flex flex-wrap gap-1">
                    {Object.entries((v.instantanea.metas as Record<string, number>) ?? {}).map(([u, c]) => <Insignia key={u} tono="neutro">{numero(c)} {nombreUnidad(u).toLowerCase()}</Insignia>)}
                  </span>
                </span>
                <History className="size-4 text-texto-3" />
              </li>
            ))}
          </ol>
        )}
      </Tarjeta>

      {editar && (
        <FormularioProyecto
          proyecto={p}
          alCerrar={() => setEditar(false)}
          alGuardar={() => {
            setEditar(false);
            avisos.exito("Alcance actualizado: quedó como versión nueva.");
            void recargarTodo();
          }}
        />
      )}
      <ModalMotivo
        abierto={!!transicion}
        titulo={transicion?.titulo ?? ""}
        descripcion={transicion?.descripcion}
        boton={transicion?.boton ?? ""}
        peligro={transicion?.peligro}
        alCerrar={() => setTransicion(null)}
        alConfirmar={async (motivo) => {
          await api(`/proyectos/${p.id}/${transicion!.ruta}`, { metodo: "POST", cuerpo: { motivo } });
          avisos.exito(`Proyecto ${transicion!.ruta === "cerrar" ? "cerrado" : transicion!.ruta === "activar" ? "activado" : "reabierto"}.`);
          await recargarTodo();
        }}
      />
      {nuevaSede && <ModalSede proyectoId={p.id} alCerrar={() => setNuevaSede(false)} alGuardar={() => (setNuevaSede(false), avisos.exito("Sede agregada."), void sedes.recargar())} />}
      {nuevoMiembro && (
        <ModalMiembro
          proyectoId={p.id}
          personas={(personas.datos ?? []).filter((x) => !equipo.datos?.some((m) => m.usuario_id === x.usuario_id))}
          alCerrar={() => setNuevoMiembro(false)}
          alGuardar={() => (setNuevoMiembro(false), avisos.exito("Persona asignada al equipo."), void equipo.recargar())}
        />
      )}
    </>
  );
}

function ModalSede({ proyectoId, alCerrar, alGuardar }: { proyectoId: string; alCerrar: () => void; alGuardar: () => void }) {
  const [d, setD] = useState({ nombre: "", ciudad: "", direccion: "" });
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  return (
    <Modal
      abierto
      alCerrar={alCerrar}
      titulo="Agregar sede"
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={d.nombre.trim().length < 2}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                await api(`/proyectos/${proyectoId}/sedes`, { metodo: "POST", cuerpo: d });
                alGuardar();
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
      <div className="flex flex-col gap-3">
        <Campo etiqueta="Nombre" requerido><Entrada value={d.nombre} onChange={(e) => setD({ ...d, nombre: e.target.value })} autoFocus placeholder="Archivo central" /></Campo>
        <Campo etiqueta="Ciudad"><Entrada value={d.ciudad} onChange={(e) => setD({ ...d, ciudad: e.target.value })} /></Campo>
        <Campo etiqueta="Dirección"><Entrada value={d.direccion} onChange={(e) => setD({ ...d, direccion: e.target.value })} /></Campo>
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}

function ModalMiembro({ proyectoId, personas, alCerrar, alGuardar }: { proyectoId: string; personas: Persona[]; alCerrar: () => void; alGuardar: () => void }) {
  const [usuarioId, setUsuarioId] = useState("");
  const [funcion, setFuncion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  return (
    <Modal
      abierto
      alCerrar={alCerrar}
      titulo="Asignar persona al equipo"
      descripcion="La persona debe tener este proyecto dentro de su alcance."
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            icono={<CheckCircle2 />}
            cargando={enviando}
            disabled={!usuarioId}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                await api(`/proyectos/${proyectoId}/equipo`, { metodo: "POST", cuerpo: { usuario_id: usuarioId, funcion } });
                alGuardar();
              } catch (e) {
                setError((e as Error).message);
                setEnviando(false);
              }
            }}
          >
            Asignar
          </Boton>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Campo etiqueta="Persona" requerido>
          <Selector value={usuarioId} onChange={(e) => setUsuarioId(e.target.value)} autoFocus>
            <option value="">Elija…</option>
            {personas.map((x) => <option key={x.usuario_id} value={x.usuario_id}>{x.nombre_completo} · {x.rol}</option>)}
          </Selector>
        </Campo>
        <Campo etiqueta="Función en el proyecto" ayuda="Ej.: Hoja de control, Descripción, Control de calidad">
          <Entrada value={funcion} onChange={(e) => setFuncion(e.target.value)} />
        </Campo>
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}
