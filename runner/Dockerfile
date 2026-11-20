# Linesman runner sandbox: the entrant's environment. Pinned by digest (index, 2026-11).
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
RUN pip install --no-cache-dir uv==0.9.17 ezdxf==1.4.5
# The Devin CLI is the one harness in the image (official pinned build, sha256-verified per arch); the
# claude-code and codex adapters run outside the container (--no-docker, docs/protocol.md).
ARG DEVIN_VERSION=3000.14.30821
ARG TARGETARCH
RUN set -eu; case "${TARGETARCH:-$(uname -m)}" in \
      amd64|x86_64) t=x86_64; sha=4dc43e3e4388bace60fe2aa8010cbb399402e724892d7175845b1cdef00e7ddb ;; \
      arm64|aarch64) t=aarch64; sha=3deb8af6b026060e975ed371936e139818020e5dc5abbcba07cde039f473a5a5 ;; \
      *) echo "devin: no pinned tarball for arch ${TARGETARCH:-$(uname -m)}" >&2; exit 2 ;; \
    esac \
 && python -c "import hashlib, sys, urllib.request; d = urllib.request.urlopen(f'https://static.devin.ai/cli/${DEVIN_VERSION}/devin-${DEVIN_VERSION}-{sys.argv[1]}-unknown-linux.tar.gz').read(); assert hashlib.sha256(d).hexdigest() == sys.argv[2], 'devin tarball checksum mismatch'; open('/tmp/devin.tgz', 'wb').write(d)" "$t" "$sha" \
 && tar -xzf /tmp/devin.tgz -C /usr/local bin/devin \
 && rm /tmp/devin.tgz
RUN useradd --uid 10002 --create-home runner  # the entrant never runs as root
WORKDIR /work
USER 10002:10002
ENTRYPOINT ["/bin/bash"]
