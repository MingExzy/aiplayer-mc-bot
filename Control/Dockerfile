FROM node:24.15.0-slim
WORKDIR /app/Control
COPY Control/package.json ./package.json
COPY Control/package-lock.json ./package-lock.json
RUN npm ci --omit=dev
COPY Control/. ./
CMD ["node", "launcher.js","1"]
