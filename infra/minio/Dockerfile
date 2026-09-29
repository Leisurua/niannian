# Upstream release registries now reject anonymous pulls. Build the same releases
# from immutable upstream commits; never substitute a third-party mirror.
FROM golang:1.23.6-alpine3.21@sha256:f8113c4b13e2a8b3a168dceaee88ac27743cc84e959f43b9dbd2291e9c3f57a0 AS builder
RUN apk add --no-cache git ca-certificates
ENV CGO_ENABLED=0 GOTOOLCHAIN=local

FROM builder AS server-build
WORKDIR /src
RUN git init && git remote add origin https://github.com/minio/minio.git \
    && git fetch --depth=1 origin 90f5e1e5f62cbc47be6d0a3ca0634bfd84c2248c \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = 90f5e1e5f62cbc47be6d0a3ca0634bfd84c2248c
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -mod=readonly -trimpath -ldflags "$(go run buildscripts/gen-ldflags.go)" -o /out/minio .

FROM builder AS client-build
WORKDIR /src
RUN git init && git remote add origin https://github.com/minio/mc.git \
    && git fetch --depth=1 origin bd925c01a1ccab367993f20c251b7bae9d22f8a5 \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = bd925c01a1ccab367993f20c251b7bae9d22f8a5
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -mod=readonly -trimpath -ldflags "$(go run buildscripts/gen-ldflags.go)" -o /out/mc .

FROM alpine:3.21@sha256:ce64758a109eb420d874a118f87920e625e12d3634e03b4a5573fd9f6e5d3507 AS runtime
RUN apk add --no-cache ca-certificates curl

FROM runtime AS server
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="90f5e1e5f62cbc47be6d0a3ca0634bfd84c2248c" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
COPY --from=server-build /out/minio /usr/bin/minio
COPY --from=server-build /src/LICENSE /licenses/LICENSE
ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]

FROM runtime AS client
LABEL org.opencontainers.image.source="https://github.com/minio/mc" \
      org.opencontainers.image.revision="bd925c01a1ccab367993f20c251b7bae9d22f8a5" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
COPY --from=client-build /out/mc /usr/bin/mc
COPY --from=client-build /src/LICENSE /licenses/LICENSE
ENTRYPOINT ["/usr/bin/mc"]
