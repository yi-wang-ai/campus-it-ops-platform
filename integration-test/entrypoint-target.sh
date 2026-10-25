#!/bin/bash
set -e

# Start sshd
/usr/sbin/sshd

# Start nginx (not as PID 1 — background it and wait)
nginx -g 'daemon off;' &
NGINX_PID=$!

# Keep container alive even if nginx is killed
trap "kill $NGINX_PID 2>/dev/null; exit 0" SIGTERM SIGINT
wait $NGINX_PID || true

# If nginx exits, keep container alive for SSH access
while true; do sleep 60; done
