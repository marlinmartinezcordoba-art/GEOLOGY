"use client";

import { CalendarClock, History, Plus, Settings2 } from "lucide-react";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, Codigo, EncabezadoPagina, Insignia, Modal, Nota, Tabla, Tarjeta, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { fechaHora } from "@/lib/formato";
import { PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { Parametro, Proyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const mostrar = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

export default function Configuracion() {
  const { puede } = useSesion();
  const avisos = useAvisos();
  const [proyectoId, setProyectoId] = useState("");
  const proyectos = useDatos(() => api<Proyecto[]>("/proyectos").catch(() => [] as Proyecto[]), []);
  const parametros = useDatos(() => api<Parametro[]>("/configuracion/parametros", { consulta: { proyecto_id: proyectoId } }), [proyectoId]);
  const conocidos = useDatos(() => api<Record<string, string>>("/configuracion/parametros/conocidos"), []);
  const [nuevo, setNuevo] = useState<{ clave?: string } | null>(null);
  const [historial, setHistorial] = useState<string | null>(null);

  return (
    <>
      <EncabezadoPagina
        titulo="Configuración"
        descripcion="Parámetros versionados. Una versión no se edita: se publica otra con su vigencia, y la vigencia nunca es pasada."
        acciones={puede(PERMISOS.configuracion) && <Boton variante="primario" icono={<Plus />} onClick={() => setNuevo({})}>Publicar parámetro</Boton>}
      />
      <Tarjeta>
        <div className="flex flex-wrap items-end gap-3 border-b border-line px-5 py-4">
          <Campo etiqueta="Ver la configuración de" className="w-full sm:w-96">
            <Selector value={proyectoId} onChange={(e) => setProyectoId(e.target.value)}>
              <option value="">Toda la organización</option>
              {proyectos.datos?.map((p) => <option key={p.id} value={p.id}>Proyecto {p.codigo} · {p.nombre}</option>)}
            </Selector>
          </Campo>
          {proyectoId && <p className="pb-2 text-[12.5px] text-texto-3">El parámetro del proyecto prevalece sobre el de la organización.</p>}
        </div>
        {parametros.cargando && !parametros.datos ? (
          <Cargando />
        ) : parametros.error ? (
          <div className="p-5"><CajaError mensaje={parametros.error} reintentar={parametros.recargar} /></div>
        ) : !parametros.datos?.length ? (
          <Vacio icono={<Settings2 />} titulo="Sin parámetros publicados" descripcion="Mientras no se publique nada, ARCA usa sus valores por defecto." />
        ) : (
          <Tabla>
            <thead><tr><th>Clave</th><th>Valor vigente</th><th>Versión</th><th>Vigente desde</th><th>Ámbito</th><th>Motivo</th><th /></tr></thead>
            <tbody>
              {parametros.datos.map((p) => (
                <tr key={p.id}>
                  <td><Codigo>{p.clave}</Codigo>{conocidos.datos?.[p.clave] && <span className="block text-[12px] text-texto-3">{conocidos.datos[p.clave]}</span>}</td>
                  <td className="font-semibold">{mostrar(p.valor)}</td>
                  <td>v{p.version}</td>
                  <td className="whitespace-nowrap">{fechaHora(p.vigente_desde)}</td>
                  <td>{p.proyecto_id ? <Insignia tono="marca">Proyecto</Insignia> : <Insignia tono="neutro">Organización</Insignia>}</td>
                  <td className="max-w-64 truncate" title={p.motivo}>{p.motivo}</td>
                  <td className="whitespace-nowrap">
                    <Boton tamano="sm" variante="fantasma" icono={<History />} onClick={() => setHistorial(p.clave)}>Historial</Boton>
                    {puede(PERMISOS.configuracion) && <Boton tamano="sm" variante="fantasma" icono={<CalendarClock />} onClick={() => setNuevo({ clave: p.clave })}>Nueva versión</Boton>}
                  </td>
                </tr>
              ))}
            </tbody>
          </Tabla>
        )}
      </Tarjeta>
      {nuevo && (
        <ModalParametro
          clave={nuevo.clave}
          proyectoId={proyectoId}
          conocidos={conocidos.datos ?? {}}
          alCerrar={() => setNuevo(null)}
          alGuardar={(futuro) => (setNuevo(null), avisos.exito(futuro ? "Publicado. Regirá desde la fecha indicada." : "Publicado y vigente desde ahora."), void parametros.recargar())}
        />
      )}
      {historial && <ModalHistorial clave={historial} proyectoId={proyectoId} alCerrar={() => setHistorial(null)} />}
    </>
  );
}

function ModalParametro({ clave: inicial, proyectoId, conocidos, alCerrar, alGuardar }: { clave?: string; proyectoId: string; conocidos: Record<string, string>; alCerrar: () => void; alGuardar: (futuro: boolean) => void }) {
  const [clave, setClave] = useState(inicial ?? "");
  const [valor, setValor] = useState("");
  const [vigencia, setVigencia] = useState("");
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const interpretar = (texto: string): unknown => {
    try {
      return JSON.parse(texto);
    } catch {
      return texto;
    }
  };
  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo={inicial ? `Nueva versión · ${inicial}` : "Publicar parámetro"}
      descripcion={proyectoId ? "Se publica para el proyecto seleccionado." : "Se publica para toda la organización."}
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton
            variante="primario"
            cargando={enviando}
            disabled={!clave || !valor.trim() || motivo.trim().length < 5}
            onClick={async () => {
              setEnviando(true);
              setError(null);
              try {
                await api("/configuracion/parametros", {
                  metodo: "POST",
                  cuerpo: { clave: clave.trim(), valor: interpretar(valor.trim()), motivo: motivo.trim(), vigente_desde: vigencia ? new Date(vigencia).toISOString() : null, proyecto_id: proyectoId || null },
                });
                alGuardar(!!vigencia);
              } catch (e) {
                setError((e as Error).message);
                setEnviando(false);
              }
            }}
          >
            Publicar
          </Boton>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {!inicial && (
          <Campo etiqueta="Clave" requerido ayuda="En minúsculas y con al menos un punto. Ej.: captura.dpi_minimo">
            <Entrada value={clave} onChange={(e) => setClave(e.target.value.toLowerCase())} list="parametros-conocidos" autoFocus />
            <datalist id="parametros-conocidos">{Object.keys(conocidos).map((k) => <option key={k} value={k} />)}</datalist>
          </Campo>
        )}
        {conocidos[clave] && <Nota tono="info">{conocidos[clave]}</Nota>}
        <Campo etiqueta="Valor" requerido ayuda="Número, true/false, texto o JSON.">
          <Entrada value={valor} onChange={(e) => setValor(e.target.value)} placeholder={clave === "seguridad.mfa_privilegiados" ? "true" : "300"} />
        </Campo>
        <Campo etiqueta="Vigente desde" ayuda="Vacío = desde ahora. No puede ser una fecha pasada.">
          <Entrada type="datetime-local" value={vigencia} onChange={(e) => setVigencia(e.target.value)} />
        </Campo>
        <Campo etiqueta="Motivo" requerido ayuda="Ej.: política de captura aprobada en comité del 13 de noviembre."><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}

function ModalHistorial({ clave, proyectoId, alCerrar }: { clave: string; proyectoId: string; alCerrar: () => void }) {
  const { datos, error, cargando } = useDatos(() => api<Parametro[]>(`/configuracion/parametros/${encodeURIComponent(clave)}/historial`, { consulta: { proyecto_id: proyectoId } }), [clave, proyectoId]);
  const ahora = Date.now();
  return (
    <Modal abierto ancho="lg" alCerrar={alCerrar} titulo={`Historial · ${clave}`} descripcion="Todas las versiones, con su vigencia y su motivo.">
      {cargando ? <Cargando /> : error ? <CajaError mensaje={error} /> : (
        <ol className="flex flex-col gap-2">
          {[...(datos ?? [])].reverse().map((p) => (
            <li key={p.id} className="flex items-start gap-3 rounded-lg border border-line p-3">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-marca-suave font-mono text-[12px] font-semibold text-marca">v{p.version}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{mostrar(p.valor)}</span>
                <span className="block text-[12.5px] text-texto-3">Desde {fechaHora(p.vigente_desde)} · {p.motivo}</span>
              </span>
              {new Date(p.vigente_desde).getTime() > ahora && <Insignia tono="aviso">Programada</Insignia>}
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}
