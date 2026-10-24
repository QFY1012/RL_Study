#!/bin/bash
# Run one shell command for the page agent in a sandbox.
#
#   agent/sandbox.sh <workspace> <command>
#
# New mount, network and PID namespaces with a fresh root on tmpfs. The command
# sees the workspace read-write; /usr (python3 included), node, fonts and a few
# /etc files read-only; empty /tmp. No other files, no environment beyond
# PATH/HOME/LANG (so no API key), no network but loopback.
#
# For pageshot (agent/bin) it also sees, read-only, Chromium, this project's
# Python environment and src/, and report-bench's src/ (capture lives there):
# the agent can screenshot its page the way the judge does, served over loopback.
set -euo pipefail
WS="$(realpath "$1")"
CMD="$2"
ROOT="$(realpath "$(dirname "$0")/..")"
BENCH="$(realpath "$ROOT/../report-bench")"

exec unshare --mount --net --pid --fork --mount-proc env -i \
  PATH=/usr/sbin:/usr/bin:/bin WS="$WS" CMD="$CMD" ROOT="$ROOT" BENCH="$BENCH" /bin/bash -c '
set -euo pipefail
# bring loopback up (SIOCGIFFLAGS / SIOCSIFFLAGS): pageshot serves the page to Chromium on 127.0.0.1
python3 -c "import socket,fcntl,struct;s=socket.socket();f=struct.unpack(\"16sH14s\",fcntl.ioctl(s,0x8913,struct.pack(\"16sH14s\",b\"lo\",0,b\"\")))[1];fcntl.ioctl(s,0x8914,struct.pack(\"16sH14s\",b\"lo\",f|1,b\"\"))"
R=$(mktemp -d)
mount -t tmpfs -o size=512m sandbox "$R"
ro() {
  if [ -d "$1" ]; then mkdir -p "$R$1"; else mkdir -p "$(dirname "$R$1")"; touch "$R$1"; fi
  mount --bind "$1" "$R$1"; mount -o remount,bind,ro "$R$1"
}
for d in /usr /opt/node22 /etc/fonts /etc/alternatives /opt/pw-browsers "$ROOT/.venv" "$ROOT/src" "$BENCH/src" "$ROOT/agent/bin"; do ro "$d"; done
for f in /etc/passwd /etc/group /etc/ld.so.cache; do [ -e "$f" ] && ro "$f"; done
ln -s usr/bin "$R/bin"; ln -s usr/lib "$R/lib"; ln -s usr/lib64 "$R/lib64"; ln -s usr/sbin "$R/sbin"
mkdir -p "$R/dev" "$R/proc" "$R/tmp" "$R/dev/shm"
mount -t tmpfs none "$R/tmp"
mount -t tmpfs none "$R/dev/shm"
mkdir -p "$R$WS"; mount --bind "$WS" "$R$WS"
for d in null zero random urandom; do touch "$R/dev/$d"; mount --bind "/dev/$d" "$R/dev/$d"; done
mount -t proc proc "$R/proc"
exec chroot "$R" /usr/bin/env -i PATH=$ROOT/agent/bin:/opt/node22/bin:/usr/bin:/bin HOME=/tmp LANG=C.UTF-8 REPORT_GEPA=$ROOT REPORT_BENCH=$BENCH \
  /bin/bash -c "cd \"$WS\" && $CMD"
'
