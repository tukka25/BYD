# Dev-mode image: this stack is for local testing, and `next dev` gives hot
# reload against the mounted source. For a production image you would want a
# multi-stage build running `next build` then `next start`.
FROM node:22-alpine

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Copy manifests first so a source edit does not reinstall node_modules.
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]
