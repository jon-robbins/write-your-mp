#!/usr/bin/env bash
# Generates trial letters for review without touching server/letters.json. Each letter blends two
# tones at one of several temperatures; the report lists the tones, the prompt sent, the sampling
# settings, the model's reasoning length, validation and checker results, and the output,
# separated by lines of 50 equal signs.
#
#   OPENAI_BASE_URL=http://host:18020/v1 scripts/trial-letters.sh [count] [report-file] [options]
#
# Options after the count go straight to trial_letters.py and override the defaults below, for example
#   scripts/trial-letters.sh 20 --concurrency 12      (or -c 12: letters requested at once)
# The report is updated as each letter finishes, so stopping with Ctrl-C keeps everything done so far.
#
# The API key comes from OPENAI_API_KEY, else VLLM_API_KEY. Each letter gets a random temperature
# from TEMPERATURE_RANGE (default 0.68 to 0.75: trials found 0.6 bland and 0.8 prone to invented
# claims); set TEMPERATURES to a list such as "0.6 0.7 0.8" to compare fixed values instead.
# THINK_TEMPERATURE (default 0.95; set it empty to turn off) samples the reasoning at that temperature
# in a separate request before each letter, which is then written at its usual temperature. Override TOP_P, TOP_K, THINKING (1 or 0),
# CHECK (1 or 0), HOME_LETTERS, CONCURRENCY, SEED or OPENAI_MODEL in the environment. With thinking on, vLLM needs a reasoning parser (--reasoning-parser qwen3); the
# report warns when no reasoning comes back.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${OPENAI_BASE_URL:?set OPENAI_BASE_URL, e.g. http://host:18020/v1}"
export OPENAI_BASE_URL
export OPENAI_API_KEY="${OPENAI_API_KEY:-${VLLM_API_KEY:-}}"
export OPENAI_MODEL="${OPENAI_MODEL:-qwen3.8-27b}"

count="${1:-100}"
[[ $# -gt 0 ]] && shift
report="trials/letters-$(date +%Y%m%d-%H%M%S).txt"
if [[ $# -gt 0 && "$1" != -* ]]; then report="$1"; shift; fi
if [[ -n "${TEMPERATURES:-}" ]]; then
  read -r -a temperature_args <<< "--temperatures $TEMPERATURES"
else
  read -r -a temperature_args <<< "--temperature-range ${TEMPERATURE_RANGE:-0.68 0.75}"
fi
thinking=$([[ "${THINKING:-1}" == 1 ]] && echo true || echo false)
check=$([[ "${CHECK:-1}" == 1 ]] && echo --check || echo --no-check)
think_args=()
think_temperature="${THINK_TEMPERATURE-0.95}"
if [[ -n "$think_temperature" ]]; then think_args=(--think-temperature "$think_temperature"); fi

uv run scripts/trial_letters.py \
  --count "$count" \
  --home "${HOME_LETTERS:-$((count / 10))}" \
  "${temperature_args[@]}" \
  --extra-body "{\"top_p\": ${TOP_P:-0.95}, \"top_k\": ${TOP_K:-20}, \"chat_template_kwargs\": {\"enable_thinking\": $thinking}}" \
  "$check" \
  ${think_args[@]+"${think_args[@]}"} \
  --concurrency "${CONCURRENCY:-4}" \
  --seed "${SEED:-1}" \
  --out "$report" \
  ${@+"$@"}
