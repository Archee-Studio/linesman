#!/usr/bin/env bash
# linesman run: execute one adapter over a built split and grade the submissions outside the sandbox.
# Usage: runner/run.sh <adapter> <split-dir> <out> <k> [--no-docker]
#   adapter: claude-code | codex | devin   k: independent runs per task (spec: 3)
#   Env: MODEL (adapter's model id, default below), JOBS (parallel tasks, default 4), TIMEOUT_S (default 900),
#   NETWORK (default open so the harness reaches its API; "none" restores the isolated sandbox),
#   DEVIN_CREDENTIALS (path to the file `devin auth login` wrote; default ~/.local/share/devin/credentials.toml).
# Copies task.md, inputs.json, RULES.md (and sheet.dxf for review) into a fresh work folder per run;
# truth.json, task.json and MANIFEST never enter. One line per run lands in <out>/runs.jsonl.
set -euo pipefail
adapter=${1:?adapter: claude-code|codex|devin}; split=$(cd "${2:?split dir}" && pwd); out=$(mkdir -p "${3:?out dir}" && cd "$3" && pwd); k=${4:?runs per task}
no_docker=0; [ "${5:-}" = "--no-docker" ] && no_docker=1
model=${MODEL:-}; jobs=${JOBS:-4}; timeout_s=${TIMEOUT_S:-900}; network=${NETWORK:-open}
devin_creds=${DEVIN_CREDENTIALS:-$HOME/.local/share/devin/credentials.toml}
here=$(cd "$(dirname "$0")" && pwd)
image=linesman-runner

case "$adapter" in
  claude-code) model=${model:-claude-sonnet-4-5}; cmd='claude -p "$P" --model "$MODEL" --permission-mode bypassPermissions --max-turns 60'; ver='claude --version' ;;
  codex)       model=${model:-}; cmd='codex exec -m "$MODEL" --dangerously-bypass-approvals-and-sandbox "$P"'; ver='codex --version' ;;
  devin)       model=${model:-swe-2-flash-high}; cmd='devin -p "$P" --model "$MODEL" --permission-mode dangerous --respect-workspace-trust false --export transcript.json'; ver='devin --version' ;;
  *) echo "run.sh: unknown adapter $adapter" >&2; exit 2 ;;
esac
if [ -z "$model" ]; then echo "run.sh: set MODEL for adapter $adapter" >&2; exit 2; fi

mkdir -p "$out/submissions" "$out/work"
: > "$out/runs.jsonl.tmp"

image_id=
creds_tmp=
if [ "$no_docker" = 0 ]; then
  docker build -q -t "$image" "$here" >/dev/null
  image_id=$(docker image inspect -f '{{.Id}}' "$image")
  harness_version=$(docker run --rm "$image" -c "$ver" | head -1)
else
  harness_version=$($ver | head -1)
fi

if [ "$adapter" = devin ]; then
  [ -r "$devin_creds" ] || { echo "run.sh: devin needs credentials from 'devin auth login' ($devin_creds); set DEVIN_CREDENTIALS to its path" >&2; exit 2; }
  if [ "$no_docker" = 0 ]; then
    # The container's uid 10002 must read the file, so a private 644 copy is mounted read-only.
    creds_tmp=$(mktemp "${TMPDIR:-/tmp}/linesman-devin-creds.XXXXXX")
    chmod 644 "$creds_tmp"
    cp "$devin_creds" "$creds_tmp"
    trap 'rm -f "$creds_tmp"' EXIT
  fi
fi

run_one() {
  task_dir=$1; run_i=$2
  name=$(basename "$task_dir"); dest="$out/submissions/run$run_i/$name"
  work="$out/work/${name}-run$run_i"
  rm -rf "$work" "$dest"; mkdir -p "$work" "$dest"
  cp "$task_dir/task.md" "$task_dir/inputs.json" "$task_dir/RULES.md" "$work/"
  [ -f "$task_dir/sheet.dxf" ] && cp "$task_dir/sheet.dxf" "$work/"
  P=$(cat "$here/prompt.txt")
  # Devin's XDG data dir lands in the work folder so the credentials file is in one place and the
  # session state survives the container's exit. In Docker the placeholder also keeps the
  # bind-mount target a file the container's uid can read past.
  if [ "$adapter" = devin ]; then mkdir -p "$work/xdg-data/devin" && : > "$work/xdg-data/devin/credentials.toml" && chmod a+w "$work/xdg-data" "$work/xdg-data/devin"; fi
  start=$(date +%s); iso_s=$(date -u +%FT%TZ); code=0
  if [ "$no_docker" = 1 ]; then
    xdg_env=()
    if [ "$adapter" = devin ]; then cp "$devin_creds" "$work/xdg-data/devin/credentials.toml"; xdg_env=(XDG_DATA_HOME="$work/xdg-data"); fi
    (cd "$work" && env P="$P" MODEL="$model" ${xdg_env[@]+"${xdg_env[@]}"} timeout "$timeout_s" bash -c "$cmd") >"$work/harness.log" 2>&1 || code=$?
    rm -f "$work/xdg-data/devin/credentials.toml"
  else
    # The image's user is uid 10002; the bind-mounted work dir must take its writes.
    chmod a+w "$work"
    net_args=(); [ "$network" = none ] && net_args=(--network none)
    creds_args=(); [ -n "$creds_tmp" ] && creds_args=(-v "$creds_tmp":/work/xdg-data/devin/credentials.toml:ro)
    docker run --rm ${net_args[@]+"${net_args[@]}"} --cpus 2 --memory 4g -v "$work":/work ${creds_args[@]+"${creds_args[@]}"} \
      -e MODEL="$model" -e P="$P" -e XDG_DATA_HOME=/work/xdg-data "$image" \
      -c "cd /work && timeout $timeout_s bash -c '$cmd'" >"$work/harness.log" 2>&1 || code=$?
    rm -f "$work/xdg-data/devin/credentials.toml"
  fi
  end=$(date +%s); iso_e=$(date -u +%FT%TZ)
  tokens=$(python3 - "$work/transcript.json" <<'PY' || true
import json, os, sys
if os.path.isfile(sys.argv[1]):
    m = json.load(open(sys.argv[1])).get("final_metrics") or {}
    keys = ("total_prompt_tokens", "total_completion_tokens", "total_cached_tokens")
    if all(k in m for k in keys):
        print(',"tokens_prompt":%s,"tokens_completion":%s,"tokens_cached":%s' % tuple(m[k] for k in keys))
PY
)
  for f in sheet.dxf findings.json; do [ -f "$work/$f" ] && [ "$f" = findings.json -o ! -f "$task_dir/sheet.dxf" ] && cp "$work/$f" "$dest/"; done
  printf '{"task":"%s","run":%s,"adapter":"%s","model":"%s","harness_version":"%s","network":"%s","image":"%s","start":"%s","end":"%s","wall_s":%s,"exit":%s%s}\n' \
    "$name" "$run_i" "$adapter" "$model" "$harness_version" "$network" "$image_id" "$iso_s" "$iso_e" "$((end - start))" "$code" "$tokens" >> "$out/runs.jsonl.tmp"
}
export -f run_one; export out adapter model cmd no_docker timeout_s network creds_tmp devin_creds image image_id harness_version here

find "$split" -mindepth 1 -maxdepth 1 -type d -name '*' | while read -r d; do
  [ -f "$d/task.json" ] && echo "$d"
done | xargs -P "$jobs" -I{} bash -c 'for i in $(seq 1 '"$k"'); do run_one {} $i; done'
sort "$out/runs.jsonl.tmp" > "$out/runs.jsonl"; rm "$out/runs.jsonl.tmp"
for i in $(seq 1 "$k"); do
  echo "grade run $i: linesman grade $split $out/submissions/run$i --out $out/results-k$i.json"
done
