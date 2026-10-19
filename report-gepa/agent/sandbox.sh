#!/bin/bash
# Run one shell command for the page agent in a sandbox.
#
#   agent/sandbox.sh <workspace> <command>
#
# New mount, network and PID namespaces with a fresh root on tmpfs. The command
# sees the workspace read-write; /usr (python3 included), node, fonts and a few
# /etc files read-only; empty /tmp. No other files, no environment beyond
# PATH/HOME/LANG (so no API key), no network.
set -euo pipefail
WS="$(realpath "$1")"
CMD="$2"

exec unshare --mount --net --pid --fork --mount-proc env -i \
  PATH=/usr/sbin:/usr/bin:/bin WS="$WS" CMD="$CMD" /bin/bash -c '
set -euo pipefail
R=$(mktemp -d)
mount -t tmpfs -o size=512m sandbox "$R"
ro() {
  if [ -d "$1" ]; then mkdir -p "$R$1"; else mkdir -p "$(dirname "$R$1")"; touch "$R$1"; fi
  mount --bind "$1" "$R$1"; mount -o remount,bind,ro "$R$1"
}
for d in /usr /opt/node22 /etc/fonts /etc/alternatives; do ro "$d"; done
for f in /etc/passwd /etc/group /etc/ld.so.cache; do [ -e "$f" ] && ro "$f"; done
ln -s usr/bin "$R/bin"; ln -s usr/lib "$R/lib"; ln -s usr/lib64 "$R/lib64"; ln -s usr/sbin "$R/sbin"
mkdir -p "$R/dev" "$R/proc" "$R/tmp"
mount -t tmpfs none "$R/tmp"
mkdir -p "$R$WS"; mount --bind "$WS" "$R$WS"
for d in null zero random urandom; do touch "$R/dev/$d"; mount --bind "/dev/$d" "$R/dev/$d"; done
mount -t proc proc "$R/proc"
exec chroot "$R" /usr/bin/env -i PATH=/opt/node22/bin:/usr/bin:/bin HOME=/tmp LANG=C.UTF-8 \
  /bin/bash -c "cd \"$WS\" && $CMD"
'
