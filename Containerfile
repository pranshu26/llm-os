FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files

FROM quay.io/fedora/fedora-bootc:44@sha256:50dd5c8f495b66912523ceba37cfd24d1bba550544fd64283399875c1bb14e16

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,target=/var/cache \
    --mount=type=cache,target=/var/log \
    --mount=type=tmpfs,target=/run \
    --mount=type=tmpfs,target=/tmp \
    /ctx/build.sh

RUN bootc container lint
