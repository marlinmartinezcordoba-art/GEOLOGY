"use client";

import { Check, Copy, Download, FileStack, Plus, Upload } from "lucide-react";
import { useState } from "react";

import { useAvisos } from "@/components/ui/avisos";
import { Boton, CajaError, Cargando, Codigo, EncabezadoPagina, Insignia, Modal, Nota, Tabla, Tarjeta, Vacio } from "@/components/ui/basicos";
import { Area, Campo, Entrada, Selector } from "@/components/ui/campos";
import { api, apiSubir } from "@/lib/api";
import { descargarArchivo } from "@/lib/descargas";
import { fechaHora } from "@/lib/formato";
import type { Plantilla, Proyecto, TipoPlantilla } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

const TONO = { vigente: "ok", reemplazada: "neutro", programada: "aviso" } as const;

/** Plantillas de la entidad: FUID de salida y rótulos, con sus marcadores y sus versiones con vigencia. */
export default function Plantillas() {
  const avisos = useAvisos();
  const tipos = useDatos(() => api<Record<string, TipoPlantilla>>("/plantillas/tipos"), []);
  const plantillas = useDatos(() => api<Plantilla[]>("/plantillas"), []);
  const proyectos = useDatos(() => api<Proyecto[]>("/proyectos").catch(() => [] as Proyecto[]), []);
  const [nueva, setNueva] = useState(false);
  const [publicar, setPublicar] = useState<Plantilla | null>(null);
  const [campos, setCampos] = useState<string | null>(null);

  return (
    <>
      <EncabezadoPagina
        titulo="Plantillas"
        descripcion="Los formatos que entrega la entidad (FUID de salida, rótulos de caja y de carpeta), en Excel y con marcadores {{campo}}. ARCA los llena sin tocar el código. Cada cambio es una versión con vigencia."
        acciones={<Boton variante="primario" icono={<Plus />} onClick={() => setNueva(true)}>Nueva plantilla</Boton>}
      />
      <div className="mb-5 grid gap-3 md:grid-cols-3">
        {Object.entries(tipos.datos ?? {}).map(([clave, t]) => (
          <div key={clave} className="rounded-xl border border-line bg-surface p-4 shadow-xs">
            <p className="font-semibold text-titulo">{t.nombre}</p>
            <p className="mt-1 text-[12.5px] text-texto-3">{Object.keys(t.encabezado).length} datos de encabezado{Object.keys(t.fila).length ? ` · ${Object.keys(t.fila).length} por fila` : ""}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Boton tamano="sm" icono={<Download />} onClick={() => descargarArchivo(`/plantillas/tipos/${clave}/base`, `Plantilla_base_${clave}.xlsx`).catch((e) => avisos.error(e.message))}>Formato base</Boton>
              <Boton tamano="sm" variante="fantasma" onClick={() => setCampos(clave)}>Ver marcadores</Boton>
            </div>
          </div>
        ))}
      </div>
      <Nota tono="info">Cómo se arma: tome el formato de la entidad (o el formato base), y en cada casilla escriba el marcador del dato, por ejemplo <Codigo>{"{{caja}}"}</Codigo> o <Codigo>{"{{fecha_inicial}}"}</Codigo>. En la tabla, escriba una sola fila modelo con <Codigo>{"{{fila.identificador}}"}</Codigo>, <Codigo>{"{{fila.nombre}}"}</Codigo>…: ARCA la repite por cada expediente y baja lo que haya debajo (totales, firmas). En los rótulos, la hoja es un rótulo: ARCA saca una hoja por caja o por carpeta.</Nota>

      <div className="mt-5 flex flex-col gap-4">
        {plantillas.cargando && !plantillas.datos ? <Cargando /> : plantillas.error ? <CajaError mensaje={plantillas.error} /> : !plantillas.datos?.length ? (
          <Vacio icono={<FileStack />} titulo="Todavía no hay plantillas" descripcion="Cree una por cada formato de la entidad y suba su archivo." />
        ) : plantillas.datos.map((p) => (
          <Tarjeta key={p.id}>
            <div className="flex flex-wrap items-start gap-3 border-b border-line px-5 py-4">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-titulo">{p.nombre}</p>
                <p className="text-[12.5px] text-texto-3">{tipos.datos?.[p.tipo]?.nombre ?? p.tipo} · {p.proyecto_id ? `solo el proyecto ${proyectos.datos?.find((x) => x.id === p.proyecto_id)?.codigo ?? ""}` : "toda la organización"}{p.descripcion ? ` · ${p.descripcion}` : ""}</p>
              </div>
              {(() => { const v = p.versiones.find((x) => x.estado === "vigente"); return v ? <Insignia tono="ok" punto>Vigente v{v.version}{v.codigo_formato ? ` · ${v.codigo_formato}` : ""}</Insignia> : <Insignia tono="aviso" punto>Sin versión vigente</Insignia>; })()}
              <Boton tamano="sm" variante="primario" icono={<Upload />} onClick={() => setPublicar(p)}>{p.versiones.length ? "Nueva versión" : "Subir archivo"}</Boton>
            </div>
            {p.versiones.length > 0 && (
              <Tabla>
                <thead><tr><th>Versión</th><th>Código del formato</th><th>Vigente desde</th><th>Estado</th><th>Motivo</th><th>Valores fijos</th><th /></tr></thead>
                <tbody>
                  {[...p.versiones].reverse().map((v) => (
                    <tr key={v.id}>
                      <td className="font-semibold">v{v.version}</td><td>{v.codigo_formato || "—"}</td><td className="whitespace-nowrap">{fechaHora(v.vigente_desde)}</td>
                      <td><Insignia tono={TONO[v.estado]} punto>{v.estado}</Insignia></td><td className="max-w-64"><span className="line-clamp-2">{v.motivo}</span></td>
                      <td className="max-w-56 text-[12px]">{Object.entries(v.valores_fijos).map(([k, val]) => `${k}: ${val}`).join(" · ") || "—"}</td>
                      <td><Boton tamano="sm" variante="fantasma" icono={<Download />} onClick={() => descargarArchivo(`/plantillas/versiones/${v.id}/archivo`, `${p.nombre}_v${v.version}.xlsx`).catch((e) => avisos.error(e.message))}>Archivo</Boton></td>
                    </tr>
                  ))}
                </tbody>
              </Tabla>
            )}
          </Tarjeta>
        ))}
      </div>

      {nueva && <ModalNueva tipos={tipos.datos ?? {}} proyectos={proyectos.datos ?? []} alCerrar={() => setNueva(false)} alGuardar={(p) => (setNueva(false), void plantillas.recargar(), setPublicar(p))} />}
      {publicar && tipos.datos && <ModalPublicar plantilla={publicar} tipo={tipos.datos[publicar.tipo]} alCerrar={() => setPublicar(null)} alGuardar={() => (setPublicar(null), avisos.exito("Versión publicada."), void plantillas.recargar())} />}
      {campos && tipos.datos && <ModalCampos tipo={tipos.datos[campos]} alCerrar={() => setCampos(null)} />}
    </>
  );
}

function ModalNueva({ tipos, proyectos, alCerrar, alGuardar }: { tipos: Record<string, TipoPlantilla>; proyectos: Proyecto[]; alCerrar: () => void; alGuardar: (p: Plantilla) => void }) {
  const [d, setD] = useState({ tipo: "fuid", nombre: "", descripcion: "", proyecto_id: "" });
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal abierto alCerrar={alCerrar} titulo="Nueva plantilla" pie={<>
      <Boton onClick={alCerrar}>Cancelar</Boton>
      <Boton variante="primario" disabled={d.nombre.trim().length < 3} onClick={async () => {
        try {
          alGuardar(await api<Plantilla>("/plantillas", { metodo: "POST", cuerpo: { ...d, proyecto_id: d.proyecto_id || null } }));
        } catch (e) {
          setError((e as Error).message);
        }
      }}>Crear</Boton>
    </>}>
      <div className="flex flex-col gap-3">
        <Campo etiqueta="Tipo"><Selector value={d.tipo} onChange={(e) => setD({ ...d, tipo: e.target.value })}>{Object.entries(tipos).map(([k, t]) => <option key={k} value={k}>{t.nombre}</option>)}</Selector></Campo>
        <Campo etiqueta="Nombre" requerido ayuda="Ej.: FUID de la entidad, Rótulo de caja X-200"><Entrada value={d.nombre} onChange={(e) => setD({ ...d, nombre: e.target.value })} autoFocus /></Campo>
        <Campo etiqueta="Se usa en">
          <Selector value={d.proyecto_id} onChange={(e) => setD({ ...d, proyecto_id: e.target.value })}>
            <option value="">Toda la organización</option>
            {proyectos.map((p) => <option key={p.id} value={p.id}>Solo el proyecto {p.codigo}</option>)}
          </Selector>
        </Campo>
        <Campo etiqueta="Descripción"><Entrada value={d.descripcion} onChange={(e) => setD({ ...d, descripcion: e.target.value })} /></Campo>
        {error && <CajaError mensaje={error} />}
      </div>
    </Modal>
  );
}

function ModalPublicar({ plantilla, tipo, alCerrar, alGuardar }: { plantilla: Plantilla; tipo: TipoPlantilla; alCerrar: () => void; alGuardar: () => void }) {
  const vigente = plantilla.versiones.find((v) => v.estado === "vigente");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [codigo, setCodigo] = useState(vigente?.codigo_formato ?? "");
  const [fijos, setFijos] = useState<Record<string, string>>(vigente?.valores_fijos ?? {});
  const [vigencia, setVigencia] = useState("");
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const editables = Object.entries(tipo.encabezado).filter(([k]) => !["fecha", "codigo_formato", "version_formato", "total_unidades", "total_folios", "total_imagenes"].includes(k));
  return (
    <Modal abierto ancho="xl" alCerrar={alCerrar} titulo={`${plantilla.nombre} · ${vigente ? `versión ${vigente.version + 1}` : "primera versión"}`}
      descripcion="Publicar una versión vigente desde ahora reemplaza la actual; con fecha futura queda programada. Lo ya expedido conserva su versión."
      pie={<>
        <Boton onClick={alCerrar}>Cancelar</Boton>
        <Boton variante="primario" cargando={enviando} disabled={!archivo || motivo.trim().length < 5} onClick={async () => {
          setEnviando(true);
          setError(null);
          try {
            const datos = new FormData();
            datos.append("archivo", archivo!);
            datos.append("motivo", motivo.trim());
            datos.append("codigo_formato", codigo.trim());
            datos.append("valores_fijos", JSON.stringify(Object.fromEntries(Object.entries(fijos).filter(([, v]) => v.trim()))));
            if (vigencia) datos.append("vigente_desde", new Date(vigencia).toISOString());
            await apiSubir(`/plantillas/${plantilla.id}/versiones`, datos);
            alGuardar();
          } catch (e) {
            setError((e as Error).message);
            setEnviando(false);
          }
        }}>Publicar versión</Boton>
      </>}>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="flex flex-col gap-3">
          <Campo etiqueta="Archivo de la plantilla (.xlsx)" requerido><input type="file" accept=".xlsx" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} className="text-[13px]" /></Campo>
          <Campo etiqueta="Código del formato" ayuda="El que le da la entidad en su sistema de calidad. Disponible como {{codigo_formato}}."><Entrada value={codigo} onChange={(e) => setCodigo(e.target.value)} /></Campo>
          <Campo etiqueta="Vigente desde" ayuda="Vacío = desde ahora (reemplaza la vigente). No puede ser pasada."><Entrada type="datetime-local" value={vigencia} onChange={(e) => setVigencia(e.target.value)} /></Campo>
          <Campo etiqueta="Motivo" requerido ayuda="Ej.: la entidad actualizó el formato a su versión 6."><Area value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        </div>
        <div>
          <p className="text-[13px] font-semibold text-titulo">Valores fijos de la entidad</p>
          <p className="mb-2 text-[12px] text-texto-3">Lo que no sale del sistema y la entidad quiere en el formato. Si lo deja vacío, se usa el dato del proyecto.</p>
          <div className="flex max-h-80 flex-col gap-2 overflow-y-auto pr-1">
            {editables.map(([k, etiqueta]) => (
              <Campo key={k} etiqueta={<span>{etiqueta} <span className="font-mono text-[11px] text-texto-3">{`{{${k}}}`}</span></span>}>
                <Entrada value={fijos[k] ?? ""} onChange={(e) => setFijos({ ...fijos, [k]: e.target.value })} />
              </Campo>
            ))}
          </div>
        </div>
        {error && <div className="md:col-span-2"><CajaError mensaje={error} /></div>}
      </div>
    </Modal>
  );
}

function ModalCampos({ tipo, alCerrar }: { tipo: TipoPlantilla; alCerrar: () => void }) {
  const [copiado, setCopiado] = useState<string | null>(null);
  const fila = (marcador: string, etiqueta: string) => (
    <li key={marcador} className="flex items-center gap-2 border-b border-line py-1.5 text-[13px] last:border-b-0">
      <Codigo className="min-w-0 flex-1 truncate">{marcador}</Codigo>
      <span className="text-texto-3">{etiqueta}</span>
      <button className="text-texto-3 hover:text-marca" onClick={async () => (await navigator.clipboard?.writeText(marcador), setCopiado(marcador))} aria-label={`Copiar ${marcador}`}>
        {copiado === marcador ? <Check className="size-4" /> : <Copy className="size-4" />}
      </button>
    </li>
  );
  return (
    <Modal abierto ancho="lg" alCerrar={alCerrar} titulo={`Marcadores · ${tipo.nombre}`}>
      <p className="mb-1 text-[13px] font-semibold text-titulo">Encabezado (una vez)</p>
      <ul>{Object.entries(tipo.encabezado).map(([k, v]) => fila(`{{${k}}}`, v))}</ul>
      {Object.keys(tipo.fila).length > 0 && (
        <>
          <p className="mt-4 mb-1 text-[13px] font-semibold text-titulo">Fila modelo (se repite por expediente)</p>
          <ul>{Object.entries(tipo.fila).map(([k, v]) => fila(`{{fila.${k}}}`, v))}</ul>
        </>
      )}
    </Modal>
  );
}
