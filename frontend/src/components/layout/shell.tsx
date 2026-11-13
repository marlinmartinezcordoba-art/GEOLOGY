"use client";

import { Building2, ChevronsUpDown, FileStack, Home, KeyRound, LogOut, Menu, ScrollText, Search, Settings2, ShieldHalf, Users, Waypoints, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { LogoArca } from "@/components/layout/marca";
import { sesionGuardada } from "@/lib/api";
import { cn, iniciales } from "@/lib/formato";
import { MODULOS } from "@/lib/modulos";
import { useSesion } from "@/lib/sesion";

const ICONOS: Record<string, ReactNode> = {
  inicio: <Home />,
  proyectos: <Waypoints />,
  consulta: <Search />,
  usuarios: <Users />,
  roles: <ShieldHalf />,
  configuracion: <Settings2 />,
  plantillas: <FileStack />,
  auditoria: <ScrollText />,
  organizaciones: <Building2 />,
  cuenta: <KeyRound />,
};

const GRUPOS = [
  { clave: "operacion", titulo: "Operación" },
  { clave: "administracion", titulo: "Administración" },
] as const;

function Enlace({ href, icono, nombre, alNavegar }: { href: string; icono: ReactNode; nombre: string; alNavegar?: () => void }) {
  const ruta = usePathname();
  const activo = ruta === href || ruta.startsWith(href + "/");
  return (
    <Link
      href={href}
      onClick={alNavegar}
      aria-current={activo ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-3 py-[7px] text-[13.5px] transition-colors [&_svg]:size-[17px] [&_svg]:shrink-0",
        activo ? "bg-marca font-semibold text-white" : "font-medium text-profundo-texto hover:bg-profundo-2 hover:text-white",
      )}
    >
      {icono}
      <span className="flex-1 truncate">{nombre}</span>
    </Link>
  );
}

function Navegacion({ alNavegar }: { alNavegar?: () => void }) {
  const { usuario, puede } = useSesion();
  if (usuario.es_operador) {
    return (
      <nav className="flex flex-col gap-0.5">
        <p className="px-3 pb-1 text-[11px] font-semibold tracking-wider text-profundo-texto/70 uppercase">Plataforma</p>
        <Enlace href="/plataforma" icono={ICONOS.organizaciones} nombre="Organizaciones" alNavegar={alNavegar} />
        <Enlace href="/cuenta" icono={ICONOS.cuenta} nombre="Mi cuenta" alNavegar={alNavegar} />
      </nav>
    );
  }
  return (
    <nav className="flex flex-col gap-5">
      {GRUPOS.map((g) => {
        const items = MODULOS.filter((m) => m.grupo === g.clave && (!m.permiso || puede(m.permiso)));
        if (!items.length) return null;
        return (
          <div key={g.clave} className="flex flex-col gap-0.5">
            <p className="px-3 pb-1 text-[11px] font-semibold tracking-wider text-profundo-texto/70 uppercase">{g.titulo}</p>
            {items.map((m) => (
              <Enlace key={m.clave} href={m.href} icono={ICONOS[m.clave]} nombre={m.nombre} alNavegar={alNavegar} />
            ))}
          </div>
        );
      })}
      <div className="flex flex-col gap-0.5">
        <p className="px-3 pb-1 text-[11px] font-semibold tracking-wider text-profundo-texto/70 uppercase">Personal</p>
        <Enlace href="/cuenta" icono={ICONOS.cuenta} nombre="Mi cuenta" alNavegar={alNavegar} />
      </div>
    </nav>
  );
}

function OrganizacionActiva() {
  const { usuario, organizacion } = useSesion();
  const router = useRouter();
  if (usuario.es_operador) return <span className="text-sm font-semibold text-titulo">Operación de la plataforma</span>;
  if (!organizacion) return null;
  const varias = usuario.organizaciones.length > 1;
  return (
    <button
      type="button"
      disabled={!varias}
      onClick={() => router.push("/elegir")}
      className={cn("flex min-w-0 items-center gap-2 rounded-lg px-2 py-1 text-sm font-semibold text-titulo", varias && "hover:bg-surface-muted")}
      title={varias ? "Cambiar de organización" : undefined}
    >
      <Building2 className="size-4 shrink-0 text-texto-3" />
      <span className="truncate">{organizacion.organizacion}</span>
      {varias && <ChevronsUpDown className="size-3.5 text-texto-3" />}
    </button>
  );
}

function MenuCuenta() {
  const { usuario, organizacion, salir } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const cerrar = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !caja.current?.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", cerrar);
    document.addEventListener("keydown", cerrar);
    return () => {
      document.removeEventListener("mousedown", cerrar);
      document.removeEventListener("keydown", cerrar);
    };
  }, [abierto]);
  return (
    <div className="relative" ref={caja}>
      <button onClick={() => setAbierto(!abierto)} className="flex items-center gap-2.5 rounded-lg px-1.5 py-1 hover:bg-surface-muted" aria-expanded={abierto} aria-haspopup="menu" aria-label="Mi cuenta">
        <span className="hidden max-w-[13rem] text-right leading-tight lg:block">
          <span className="block truncate text-[13px] font-semibold text-texto">{usuario.nombre_completo}</span>
          <span className="block truncate text-[11px] text-texto-3">{usuario.es_operador ? "Operador de la plataforma" : organizacion?.rol}</span>
        </span>
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-profundo text-xs font-semibold text-white">{iniciales(usuario.nombre_completo)}</span>
      </button>
      {abierto && (
        <div role="menu" className="absolute right-0 z-30 mt-2 w-64 animate-subir overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-md">
          <p className="border-b border-line px-3.5 pt-1.5 pb-2.5 text-[12px] text-texto-3">
            <span className="block truncate font-semibold text-texto">{usuario.nombre_completo}</span>
            <span className="block truncate">{usuario.correo}</span>
          </p>
          <Link role="menuitem" href="/cuenta" onClick={() => setAbierto(false)} className="flex items-center gap-2.5 px-3.5 py-2 text-sm text-texto-2 hover:bg-marca-suave hover:text-marca">
            <KeyRound className="size-4" /> Contraseña y verificación
          </Link>
          <button role="menuitem" onClick={salir} className="flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm text-texto-2 hover:bg-marca-suave hover:text-marca">
            <LogOut className="size-4" /> Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}

function BarraLateral({ alNavegar }: { alNavegar?: () => void }) {
  return (
    <>
      <div className="px-2">
        <LogoArca claro />
      </div>
      <Navegacion alNavegar={alNavegar} />
      <p className="mx-3 mt-auto text-[11px] leading-relaxed text-profundo-texto/70">La IA propone, su equipo valida y ARCA lo deja registrado.</p>
    </>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { salir } = useSesion();
  const [menu, setMenu] = useState(false);
  const ruta = usePathname();
  useEffect(() => setMenu(false), [ruta]);
  useEffect(() => {
    const m = MODULOS.find((x) => ruta === x.href || ruta.startsWith(x.href + "/"));
    document.title = m ? `${m.nombre} · ARCA` : ruta.startsWith("/plataforma") ? "Organizaciones · ARCA" : "ARCA";
  }, [ruta]);
  // Al cambiar la organización activa desde otra pestaña, se recarga para no mezclar datos.
  useEffect(() => {
    const vigilar = () => {
      if (!sesionGuardada.token()) void salir();
    };
    window.addEventListener("storage", vigilar);
    return () => window.removeEventListener("storage", vigilar);
  }, [salir]);
  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[16.5rem] flex-col gap-7 overflow-y-auto bg-profundo px-3 py-5 lg:flex">
        <BarraLateral />
      </aside>
      {menu && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 animate-aparecer bg-profundo/50" onClick={() => setMenu(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 animate-desde-derecha flex-col gap-7 overflow-y-auto bg-profundo px-3 py-5 shadow-lg">
            <div className="flex justify-end px-2">
              <button onClick={() => setMenu(false)} className="text-profundo-texto hover:text-white" aria-label="Cerrar menú">
                <X className="size-5" />
              </button>
            </div>
            <BarraLateral alNavegar={() => setMenu(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-[16.5rem]">
        <header className="sticky top-0 z-20 flex h-15 items-center gap-3 border-b border-line bg-surface px-4 lg:px-8">
          <button className="text-titulo lg:hidden" onClick={() => setMenu(true)} aria-label="Abrir menú">
            <Menu className="size-5" />
          </button>
          <OrganizacionActiva />
          <div className="ml-auto flex items-center gap-1.5">
            <MenuCuenta />
            <button onClick={salir} className="grid size-9 place-items-center rounded-lg text-texto-3 hover:bg-surface-muted hover:text-marca" aria-label="Cerrar sesión" title="Cerrar sesión">
              <LogOut className="size-4" />
            </button>
          </div>
        </header>
        <main id="contenido" tabIndex={-1} className="mx-auto w-full max-w-[1320px] flex-1 animate-aparecer px-4 py-7 focus:outline-none lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
