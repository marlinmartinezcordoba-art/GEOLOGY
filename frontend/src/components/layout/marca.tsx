/**
 * Identidad de ARCA. Un arca es el cofre donde se guarda lo valioso: el isotipo es un arca de archivo
 * vista de frente, con su tapa y tres documentos dentro; el del medio, en turquesa, es el que la
 * plataforma está procesando. Colores fijos a propósito: el logo no cambia con el tema.
 */

const NAVY = "#17324d";
const NAVY_CLARO = "#1f4062";
const TEAL = "#0f8b8d";

export function IsotipoArca({ tamano = 32, sobreOscuro = false, className }: { tamano?: number; sobreOscuro?: boolean; className?: string }) {
  return (
    <svg width={tamano} height={tamano} viewBox="0 0 64 64" aria-hidden="true" className={className} style={{ flexShrink: 0 }}>
      <rect width="64" height="64" rx="16" fill={sobreOscuro ? NAVY_CLARO : NAVY} />
      {/* Tapa del arca */}
      <path d="M13 24 L32 13 L51 24" fill="none" stroke="#ffffff" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Cuerpo */}
      <rect x="15" y="27" width="34" height="24" rx="3.5" fill="none" stroke="#ffffff" strokeWidth="3.5" />
      {/* Documentos: el del medio avanza */}
      <path d="M24 33 V45 M40 33 V45" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
      <path d="M32 33 V45" stroke={TEAL} strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

export function LogoArca({ tamano = 32, claro = false, subtitulo = "Gestión archivística inteligente", className }: { tamano?: number; claro?: boolean; subtitulo?: string | null; className?: string }) {
  return (
    <div className={`flex items-center gap-2.5 ${className ?? ""}`}>
      <IsotipoArca tamano={tamano} sobreOscuro={claro} />
      <div className="leading-none">
        <p className={`font-semibold tracking-[0.08em] ${claro ? "text-white" : "text-titulo"}`} style={{ fontSize: tamano >= 40 ? 24 : 18 }}>
          ARCA
        </p>
        {subtitulo && <p className={`mt-1 text-[11px] ${claro ? "text-profundo-texto" : "text-texto-3"}`}>{subtitulo}</p>}
      </div>
    </div>
  );
}
