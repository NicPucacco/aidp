# syntax=docker/dockerfile:1
# Multi-stage build: compile in a full toolchain, ship only the bundle and
# production node_modules. Tagged with the git tree hash of portal/ (ADR-0011).

# 1. package.json files only, so `yarn install` is cached until deps change.
FROM node:24-trixie-slim AS packages
WORKDIR /app
COPY backstage.json package.json yarn.lock .yarnrc.yml ./
COPY .yarn ./.yarn
COPY packages packages
COPY plugins plugins
RUN find packages plugins -mindepth 2 -maxdepth 2 \! -name package.json -exec rm -rf {} +

# 2. Install, type-check, build the backend bundle (which includes the frontend).
FROM node:24-trixie-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends python3 g++ build-essential \
    && rm -rf /var/lib/apt/lists/*
USER node
WORKDIR /app
COPY --from=packages --chown=node:node /app .
RUN --mount=type=cache,target=/home/node/.yarn/berry/cache,sharing=locked,uid=1000,gid=1000 \
    yarn install --immutable
COPY --chown=node:node . .
RUN yarn tsc && yarn --cwd packages/backend build
RUN mkdir -p dist/skeleton dist/bundle \
    && tar xzf packages/backend/dist/skeleton.tar.gz -C dist/skeleton \
    && tar xzf packages/backend/dist/bundle.tar.gz -C dist/bundle

# 3. Production dependencies only (native modules need the toolchain here).
FROM node:24-trixie-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends python3 g++ build-essential \
    && rm -rf /var/lib/apt/lists/*
USER node
WORKDIR /app
COPY --from=build --chown=node:node /app/.yarn ./.yarn
COPY --from=build --chown=node:node /app/.yarnrc.yml /app/backstage.json /app/yarn.lock /app/package.json ./
COPY --from=build --chown=node:node /app/dist/skeleton/ ./
RUN --mount=type=cache,target=/home/node/.yarn/berry/cache,sharing=locked,uid=1000,gid=1000 \
    yarn workspaces focus --all --production

# 4. Runtime: no compilers, non-root, read-only root filesystem friendly.
FROM node:24-trixie-slim
USER node
WORKDIR /app
COPY --from=deps --chown=node:node /app ./
COPY --from=build --chown=node:node /app/dist/bundle/ ./
COPY --chown=node:node app-config.yaml app-config.production.yaml ./
ENV NODE_ENV=production
# The scaffolder's sandbox (isolated-vm) needs this on Node 20+.
ENV NODE_OPTIONS=--no-node-snapshot
EXPOSE 7007
CMD ["node", "packages/backend", "--config", "app-config.yaml", "--config", "app-config.production.yaml"]
