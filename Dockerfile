FROM node:22-bookworm-slim

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    WRANGLER_SEND_METRICS=false

COPY package.json package-lock.json ./
RUN npm ci --include=dev

COPY . .
RUN npm run build

EXPOSE 5173

CMD ["node", "--import", "./scripts/sites-env.mjs", "./node_modules/wrangler/bin/wrangler.js", "dev", "--config", "dist/server/wrangler.json", "--local", "--persist-to", ".wrangler/state", "--ip", "0.0.0.0", "--port", "5173", "--inspector-port", "0"]
