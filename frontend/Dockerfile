# ARCA · Interfaz (Next.js en modo standalone). Reenvía /api/* a la API: mismo origen, sin CORS.
FROM node:22-alpine AS construccion
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# El destino de /api/* queda fijo al construir (rewrites de Next.js).
ARG ARCA_API_URL=http://api:8000
ENV ARCA_API_URL=${ARCA_API_URL} NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S arca && adduser -S arca -G arca
COPY --from=construccion --chown=arca:arca /app/.next/standalone ./
COPY --from=construccion --chown=arca:arca /app/.next/static ./.next/static
USER arca
EXPOSE 3000
CMD ["node", "server.js"]
