"use client";

import { CheckCircle2, CircleDashed, FolderPlus, ScrollText, Settings2, ShieldCheck, UserPlus, Users, Waypoints } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { CabeceraTarjeta, EncabezadoPagina, Insignia, Progreso, Tarjeta } from "@/components/ui/basicos";
import { api } from "@/lib/api";
import { NOMBRE_ESTADO, TONO_ESTADO } from "@/lib/estados";
import { cn, fecha, numero } from "@/lib/formato";
import { RECORRIDO } from "@/lib/modulos";
import { nombreUnidad, PERMISOS } from "@/lib/permisos";
import { useSesion } from "@/lib/sesion";
import type { PerfilOrganizacion, Proyecto } from "@/lib/tipos";
import { useDatos } from "@/lib/use-datos";

/** Indicador del Inicio: ícono de color, cifra grande y etiqueta (estilo del panel de gestión de RICORA, como en Kustos). */
function Cifra({ href, icono, tono, valor, etiqueta, detalle, barra }: { href?: string; icono: ReactNode; tono: string; valor: string; etiqueta: string; detalle?: string; barra?: number }) {
  const contenido = (
    <span className="group flex items-center gap-3.5 rounded-xl border border-line bg-surface p-4 shadow-xs transition-[border-color,box-shadow] hover:border-marca-borde hover:shadow-sm">
      <span className={cn("grid size-11 shrink-0 place-items-center rounded-xl [&_svg]:size-[22px]", tono)}>{icono}</span>
      <span className="min-w-0 flex-1">
        <span className="tabular block text-[26px] leading-none font-bold tracking-tight text-titulo">{valor}</span>
        <span className="mt-1 block truncate text-[13px] font-medium text-texto-2">{etiqueta}</span>
        {detalle && <span className="block truncate text-[12px] text-texto-3">{detalle}</span>}
        {barra !== undefined && <Progreso valor={barra} className="mt-2" />}
      </span>
    </span>
  );
  return href ? <Link href={href}>{contenido}</Link> : contenido;
}

function Accion({ href, icono, titulo, detalle }: { href: string; icono: ReactNode; titulo: string; detalle: string }) {
  return (
    <Link href={href} className="group flex items-start gap-3 rounded-xl border border-line p-3.5 transition-colors hover:border-marca-borde hover:bg-marca-suave/40">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-marca-suave text-marca [&_svg]:size-[18px]">{icono}</span>
      <span className="min-w-0">
        <span className="block text-[13.5px] font-semibold text-texto group-hover:text-marca">{titulo}</span>
        <span className="block text-[12.5px] text-texto-3">{detalle}</span>
      </span>
    </Link>
  );
}

export default function Inicio() {
  const { usuario, organizacion, puede } = useSesion();
  const perfil = useDatos(() => (puede(PERMISOS.organizacionLeer) ? api<PerfilOrganizacion>("/organizacion") : Promise.resolve(null)), [organizacion?.organizacion_id]);
  const proyectos = useDatos(() => (puede(PERMISOS.proyectosLeer) ? api<Proyecto[]>("/proyectos") : Promise.resolve([] as Proyecto[])), [organizacion?.organizacion_id]);
  const lista = proyectos.datos ?? [];
  const activos = lista.filter((p) => p.estado === "activo");
  const limites = perfil.datos?.limites ?? {};
  const uso = perfil.datos?.uso ?? {};
  const primerNombre = usuario.nombre_completo.split(" ")[0];

  return (
    <>
      <EncabezadoPagina titulo={`Hola, ${primerNombre}`} descripcion={`${organizacion?.organizacion} · ${organizacion?.rol}. Este es el estado de su operación.`} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Cifra href="/proyectos" icono={<Waypoints />} tono="bg-ok-suave text-ok" valor={numero(activos.length)} etiqueta="Proyectos activos" detalle={`${lista.length} en total`} />
        <Cifra href="/proyectos" icono={<CircleDashed />} tono="bg-neutro-suave text-neutro" valor={numero(lista.filter((p) => p.estado === "borrador").length)} etiqueta="En preparación" detalle="Borradores por completar" />
        <Cifra
          href={puede(PERMISOS.usuarios) ? "/usuarios" : undefined}
          icono={<Users />}
          tono="bg-marca-suave text-marca"
          valor={perfil.datos ? numero(uso.usuarios) : "—"}
          etiqueta="Personas con acceso"
          detalle={limites.usuarios ? `Límite del plan: ${limites.usuarios}` : "Sin límite definido"}
          barra={limites.usuarios ? (100 * (uso.usuarios ?? 0)) / limites.usuarios : undefined}
        />
        <Cifra href={puede(PERMISOS.auditoria) ? "/auditoria" : undefined} icono={<ShieldCheck />} tono="bg-motor-suave text-motor" valor="SHA-256" etiqueta="Auditoría encadenada" detalle="Cada acción queda sellada" />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Tarjeta>
          <CabeceraTarjeta titulo="Proyectos activos" descripcion="Metas contratadas por unidad de medida" acciones={<Link href="/proyectos" className="text-[13px] font-semibold text-marca hover:underline">Ver todos</Link>} />
          {activos.length === 0 ? (
            <p className="px-5 py-8 text-center text-[13px] text-texto-3">Aún no hay proyectos activos. Un proyecto se activa cuando tiene fechas, metas, responsable y sede.</p>
          ) : (
            <ul className="divide-y divide-line">
              {activos.slice(0, 6).map((p) => (
                <li key={p.id}>
                  <Link href={`/proyectos/${p.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5 hover:bg-canvas">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold text-texto">{p.nombre}</span>
                      <span className="block truncate text-[12.5px] text-texto-3">
                        {p.codigo} · {p.entidad_cliente} · hasta {fecha(p.fecha_fin)}
                      </span>
                    </span>
                    <span className="flex flex-wrap gap-1.5">
                      {Object.entries(p.metas).map(([u, c]) => (
                        <Insignia key={u} tono="marca">{numero(c)} {nombreUnidad(u).toLowerCase()}</Insignia>
                      ))}
                    </span>
                    <Insignia tono={TONO_ESTADO[p.estado]} punto>{NOMBRE_ESTADO[p.estado]}</Insignia>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Tarjeta>

        <div className="flex flex-col gap-6">
          <Tarjeta>
            <CabeceraTarjeta titulo="Acciones rápidas" />
            <div className="grid gap-2.5 p-4">
              {puede(PERMISOS.proyectos) && <Accion href="/proyectos?nuevo=1" icono={<FolderPlus />} titulo="Crear proyecto" detalle="Contrato, entidad cliente, metas y sedes" />}
              {puede(PERMISOS.usuarios) && <Accion href="/usuarios?nuevo=1" icono={<UserPlus />} titulo="Agregar persona" detalle="Con su rol y su alcance por proyecto" />}
              {puede(PERMISOS.configuracion) && <Accion href="/configuracion" icono={<Settings2 />} titulo="Publicar parámetro" detalle="Con vigencia, nunca retroactivo" />}
              {puede(PERMISOS.auditoria) && <Accion href="/auditoria" icono={<ScrollText />} titulo="Verificar la auditoría" detalle="Comprobar que nada fue alterado" />}
            </div>
          </Tarjeta>

          <Tarjeta>
            <CabeceraTarjeta titulo="Recorrido de ARCA" descripcion="Lo que ya funciona y lo que viene" />
            <ol className="relative flex flex-col gap-3 px-5 py-4 before:absolute before:top-6 before:bottom-6 before:left-[29px] before:w-px before:bg-line">
              {RECORRIDO.map((r) => (
                <li key={r.codigo} className="relative flex items-center gap-3">
                  <span className={cn("relative z-10 grid size-5 place-items-center rounded-full bg-surface", r.listo ? "text-ok-vivo" : "text-line-strong")}>
                    {r.listo ? <CheckCircle2 className="size-5" /> : <CircleDashed className="size-5" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={cn("block truncate text-[13px]", r.listo ? "font-semibold text-texto" : "text-texto-2")}>{r.nombre}</span>
                    <span className="block text-[11.5px] text-texto-3">{r.codigo} · {r.etapa}</span>
                  </span>
                </li>
              ))}
            </ol>
          </Tarjeta>
        </div>
      </div>
    </>
  );
}
