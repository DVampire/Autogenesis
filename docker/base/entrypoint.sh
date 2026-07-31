#!/usr/bin/env bash
# Container entrypoint for the Autogenesis project sandbox (Model X).
#
# Runs the given command as root (so the agent can `pip install` into the conda env
# and reach the Docker socket to spawn peer containers), then fixes ownership of the
# run's outputs: files created by root inside the container would otherwise be
# root-owned on the host through the bind mount. On exit we chown the output tree
# back to whoever owns the mounted project root (the host user), so artifacts stay
# inspectable and deletable on the host.
set -o pipefail

# Run the command as a child and forward termination to it. `docker stop` signals
# PID 1 only, and a shell defers signals until its foreground command returns —
# so a plain `"$@"` swallowed SIGTERM and the command was SIGKILLed at the end of
# the grace period. Anything it tears down on shutdown (the Gateway destroys the
# per-session IDE containers it started) never got the chance, and the orphans
# piled up until they exhausted the host's file descriptors.
"$@" &
child=$!
trap 'kill -TERM "${child}" 2>/dev/null || true' TERM INT
# `wait` returns as soon as a trap fires, so keep waiting for the real exit.
while kill -0 "${child}" 2>/dev/null; do
    wait "${child}"
    status=$?
done

proj="/Autogenesis"
owner="$(stat -c '%u:%g' "${proj}" 2>/dev/null || true)"
if [ -n "${owner}" ] && [ "${owner}" != "0:0" ]; then
    # Outputs created by root inside the container would otherwise be root-owned on
    # the host through the bind mount. Also covers frontend/node_modules, which
    # `scripts/serve-ui.sh` installs as root on first launch.
    for d in "${proj}/output" "${proj}/frontend/node_modules"; do
        [ -d "${d}" ] && chown -R "${owner}" "${d}" 2>/dev/null || true
    done
fi

exit "${status}"
