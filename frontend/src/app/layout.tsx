import type { Metadata, Viewport } from "next";
// Fuentes dentro del proyecto: la publicación no depende de servicios externos.
import "@fontsource-variable/inter/wght.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-500.css";
import "@fontsource/source-serif-4/latin-500-italic.css";

import { ProveedorAvisos } from "@/components/ui/avisos";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ARCA", template: "%s · ARCA" },
  description: "Plataforma de gestión archivística, digitalización masiva y automatización documental.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#17324d", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-CO" className="fuentes">
      <body>
        <a href="#contenido" className="sr-only z-[100] rounded-lg bg-surface px-4 py-2 font-semibold text-marca shadow-lg focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
          Saltar al contenido principal
        </a>
        <ProveedorAvisos>{children}</ProveedorAvisos>
      </body>
    </html>
  );
}
