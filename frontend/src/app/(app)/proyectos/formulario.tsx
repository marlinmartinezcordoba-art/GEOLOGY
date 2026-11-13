"use client";

import { useState } from "react";

import { Boton, CajaError, Modal } from "@/components/ui/basicos";
import { Area, Campo, Entrada, Selector } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { UNIDADES_META } from "@/lib/permisos";
import type { Persona, Proyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

type Datos = {
  codigo: string;
  nombre: string;
  entidad_cliente: string;
  numero_contrato: string;
  objeto: string;
  fecha_inicio: string;
  fecha_fin: string;
  responsable_id: string;
  metas: Record<string, string>;
  motivo: string;
};

function desde(p?: Proyecto): Datos {
  return {
    codigo: p?.codigo ?? "",
    nombre: p?.nombre ?? "",
    entidad_cliente: p?.entidad_cliente ?? "",
    numero_contrato: p?.numero_contrato ?? "",
    objeto: p?.objeto ?? "",
    fecha_inicio: p?.fecha_inicio ?? "",
    fecha_fin: p?.fecha_fin ?? "",
    responsable_id: p?.responsable_id ?? "",
    metas: Object.fromEntries(Object.entries(p?.metas ?? {}).map(([k, v]) => [k, String(v)])),
    motivo: "",
  };
}

/** Crear un proyecto, o editar su alcance. Editar exige motivo: cada cambio queda como versión. */
export function FormularioProyecto({ proyecto, alCerrar, alGuardar }: { proyecto?: Proyecto; alCerrar: () => void; alGuardar: (p: Proyecto) => void }) {
  const [d, setD] = useState<Datos>(() => desde(proyecto));
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const personas = useDatos(() => api<Persona[]>("/usuarios/directorio").catch(() => [] as Persona[]), []);
  const cambiar = (campo: keyof Datos, valor: string) => setD((x) => ({ ...x, [campo]: valor }));

  async function guardar() {
    setEnviando(true);
    setError(null);
    const metas = Object.fromEntries(Object.entries(d.metas).filter(([, v]) => v.trim() !== "").map(([k, v]) => [k, Number(v.replace(",", "."))]));
    const cuerpo = {
      nombre: d.nombre.trim(),
      entidad_cliente: d.entidad_cliente.trim(),
      numero_contrato: d.numero_contrato.trim() || null,
      objeto: d.objeto.trim(),
      fecha_inicio: d.fecha_inicio || null,
      fecha_fin: d.fecha_fin || null,
      responsable_id: d.responsable_id || null,
      metas,
    };
    try {
      const p = proyecto
        ? await api<Proyecto>(`/proyectos/${proyecto.id}`, { metodo: "PATCH", cuerpo: { ...cuerpo, motivo: d.motivo.trim() } })
        : await api<Proyecto>("/proyectos", { metodo: "POST", cuerpo: { ...cuerpo, codigo: d.codigo.trim() } });
      alGuardar(p);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  const listo = d.nombre.trim().length >= 3 && d.entidad_cliente.trim().length >= 2 && (proyecto ? d.motivo.trim().length >= 5 : d.codigo.trim().length >= 2);

  return (
    <Modal
      abierto
      ancho="lg"
      alCerrar={alCerrar}
      titulo={proyecto ? `Editar alcance · ${proyecto.codigo}` : "Nuevo proyecto"}
      descripcion={proyecto ? `Quedará como versión ${proyecto.version + 1}, con su motivo.` : "Queda en borrador. Se activa cuando tenga fechas, metas, responsable y sede."}
      pie={
        <>
          <Boton onClick={alCerrar}>Cancelar</Boton>
          <Boton variante="primario" cargando={enviando} disabled={!listo} onClick={guardar}>
            {proyecto ? "Guardar versión" : "Crear proyecto"}
          </Boton>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {!proyecto && (
          <Campo etiqueta="Código" requerido ayuda="Único en su organización. Ej.: PRY-001-2026">
            <Entrada value={d.codigo} onChange={(e) => cambiar("codigo", e.target.value.toUpperCase())} autoFocus />
          </Campo>
        )}
        <Campo etiqueta="Nombre del proyecto" requerido className={proyecto ? "sm:col-span-2" : undefined}>
          <Entrada value={d.nombre} onChange={(e) => cambiar("nombre", e.target.value)} />
        </Campo>
        <Campo etiqueta="Entidad cliente" requerido>
          <Entrada value={d.entidad_cliente} onChange={(e) => cambiar("entidad_cliente", e.target.value)} />
        </Campo>
        <Campo etiqueta="Número de contrato">
          <Entrada value={d.numero_contrato} onChange={(e) => cambiar("numero_contrato", e.target.value)} />
        </Campo>
        <Campo etiqueta="Objeto del contrato" className="sm:col-span-2">
          <Area value={d.objeto} onChange={(e) => cambiar("objeto", e.target.value)} />
        </Campo>
        <Campo etiqueta="Fecha de inicio">
          <Entrada type="date" value={d.fecha_inicio} onChange={(e) => cambiar("fecha_inicio", e.target.value)} />
        </Campo>
        <Campo etiqueta="Fecha de fin">
          <Entrada type="date" value={d.fecha_fin} onChange={(e) => cambiar("fecha_fin", e.target.value)} />
        </Campo>
        <Campo etiqueta="Responsable" className="sm:col-span-2" ayuda={personas.datos?.length ? undefined : "Su rol no puede consultar el directorio de personas."}>
          <Selector value={d.responsable_id} onChange={(e) => cambiar("responsable_id", e.target.value)}>
            <option value="">Sin asignar</option>
            {personas.datos?.map((p) => (
              <option key={p.usuario_id} value={p.usuario_id}>
                {p.nombre_completo} · {p.rol}
              </option>
            ))}
          </Selector>
        </Campo>
        <fieldset className="sm:col-span-2">
          <legend className="mb-2 text-[13px] font-medium text-texto-2">Metas contratadas</legend>
          <p className="mb-2 text-xs text-texto-3">Cada unidad se mide por separado: nunca se suman folios con imágenes. Deje vacías las que no apliquen.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            {UNIDADES_META.map((u) => (
              <Campo key={u.clave} etiqueta={u.nombre}>
                <Entrada type="number" min={0} step={u.decimales ? "0.1" : "1"} value={d.metas[u.clave] ?? ""} onChange={(e) => setD((x) => ({ ...x, metas: { ...x.metas, [u.clave]: e.target.value } }))} />
              </Campo>
            ))}
          </div>
        </fieldset>
        {proyecto && (
          <Campo etiqueta="Motivo del cambio" requerido className="sm:col-span-2" ayuda="Ej.: Otrosí No. 1, ajuste de metas por la interventoría.">
            <Area value={d.motivo} onChange={(e) => cambiar("motivo", e.target.value)} />
          </Campo>
        )}
        {error && (
          <div className="sm:col-span-2">
            <CajaError mensaje={error} />
          </div>
        )}
      </div>
    </Modal>
  );
}
