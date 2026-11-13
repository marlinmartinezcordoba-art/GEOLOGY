import type { NextConfig } from "next";

/** Dirección del backend de ARCA. La interfaz reenvía /api/* allí: mismo origen, sin CORS. */
const API = process.env.ARCA_API_URL ?? "http://localhost:8000";

const ENCABEZADOS_SEGURIDAD = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  // Las carpetas digitalizadas pesan: el reenvío a la API admite archivos grandes y tiempos largos.
  experimental: { proxyClientMaxBodySize: "500mb", proxyTimeout: 600_000 },
  async rewrites() {
    return [{ source: "/api/:ruta*", destination: `${API}/api/:ruta*` }];
  },
  async headers() {
    return [{ source: "/(.*)", headers: ENCABEZADOS_SEGURIDAD }];
  },
};

export default nextConfig;
