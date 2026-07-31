# Full VS Code in the browser (openvscode-server), editing a session workspace.
#
# Built ON TOP OF autogenesis/base so the integrated terminal is the *same*
# environment the agent runs in — conda at /opt/conda, the project importable,
# every project dependency present. The alternative (a slim editor image) meant
# a terminal without the project's Python, and copying conda into it would have
# added ~10GB; this way the layers are shared with a base image that is already
# on the host.
#
# openvscode-server itself is copied out of the upstream image rather than
# downloaded, so the build needs no network beyond the two base pulls. It ships
# its own node, so nothing else is required to run it.
#
# Ports:
#   3000  openvscode-server (HTTP + the workbench WebSocket, same port)
#
# Runs as ROOT so it can write workspace files owned by the host user. That
# matches the rest of the framework: the base container also runs as root, and
# scripts/serve-ui.sh periodically chowns output/ back to the host owner.
#
# Build (the IDE manager auto-builds this when missing; or run it yourself):
#   docker build -t autogenesis/vscode:latest docker/vscode/
FROM gitpod/openvscode-server:latest AS upstream

FROM autogenesis/base:latest

USER root

# The editor, lifted wholesale from the upstream image (self-contained: bundled
# node, extensions, web assets).
COPY --from=upstream /home/.openvscode-server /home/.openvscode-server
ENV OPENVSCODE_SERVER_ROOT=/home/.openvscode-server

COPY entrypoint-vscode.sh /usr/local/bin/entrypoint-vscode
# $BROWSER for the container: rewrites loopback OAuth callbacks onto the
# forwarded origin so a browser-based sign-in can actually return here.
COPY ide-open.sh /usr/local/bin/ide-open
RUN chmod +x /usr/local/bin/entrypoint-vscode /usr/local/bin/ide-open

EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/entrypoint-vscode"]
