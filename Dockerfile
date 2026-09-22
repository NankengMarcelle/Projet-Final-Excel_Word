# Multi-stage: build the static Vite bundle, then serve it with nginx — the running container
# never has Node in it at all, just the built dist/ output plus nginx.

FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Vite bakes import.meta.env.VITE_* values into the JS bundle at BUILD time, not read at
# container startup — so this has to be a build ARG turned into an ENV var before `npm run
# build` runs, not a runtime `docker run -e` value (that would silently have no effect).
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
