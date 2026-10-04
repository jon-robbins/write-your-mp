# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.40"]
# ///
"""Generates letter variants with any OpenAI-compatible chat endpoint and stores them server-side in
server/letters.json. Every variant must pass the same release validation as the originals
(scripts/validate-letters.mjs, run through Node).

    OPENAI_BASE_URL=https://api.example.com/v1 OPENAI_API_KEY=... \\
      uv run scripts/generate_letters.py --model some-model --general 300 --home 40

OPENAI_BASE_URL defaults to OpenAI itself; --base-url and --model (or OPENAI_MODEL) override.
--extra-body merges server-specific JSON into each request (sampling settings, chat template
switches), and --out writes somewhere other than server/letters.json for trial runs. Unless
--no-check is given, a second request checks each letter against the original and rejects any
that make claims it does not.
"""
import argparse
import itertools
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import openai

from lettergen.content import ID_PREFIX, TONES, plan_letter
from lettergen.library import LIBRARY, find_original, load_library, write_library
from lettergen.model import add_model_options, finish_model_options, make_client, random_temperature, request_letters, screen
from lettergen.prompts import build_prompt
from lettergen.rules import accept_variants, opening, overused_phrases


@dataclass(frozen=True)
class Batch:
    number: int
    tone: str
    count: int
    prompt: str
    sampling: dict | None


def generate(client, model: str, library: list[dict], *, kind: str, target: int, batch_size: int = 10,
             extra_body: dict | None = None, check: bool = False, temperature_range: tuple[float, float] | None = None,
             think_temperature: float | None = None, concurrency: int = 1, rng: random.Random | None = None,
             log=print) -> list[dict]:
    """Requests batches, one tone each, until `target` letters are kept or three batches in a row yield none.
    Each letter in a batch gets its own plan (opening lead, order of detail beats, stance); with a temperature range, each batch
    its own temperature. With `concurrency` above 1, that many batches are requested at once. Their letters are
    still accepted one batch after another, so later batches are checked against earlier ones for copies, and the
    checker then reviews the whole wave in parallel. Each request is also told which wordings are already common among
    the letters kept, so later letters phrase things differently."""
    rng = rng or random.Random()
    original = find_original(library, kind)
    serials = itertools.count(1)
    next_id = lambda: f'{ID_PREFIX[kind]}-{next(serials):03d}'
    kept = [original]
    batches = empty_batches = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        while len(kept) - 1 < target and empty_batches < 3:
            avoid = [opening(letter['body'])[:90] for letter in kept[-25:]]
            overused = overused_phrases(kept[1:])
            wave, planned, remaining = [], 0, target - (len(kept) - 1)
            while len(wave) < concurrency and planned < remaining:
                count = min(batch_size, remaining - planned)
                number = batches + len(wave) + 1
                tone = TONES[(number - 1) % len(TONES)]
                plans = [plan_letter(rng) for _ in range(count)]
                sampling = ({**(extra_body or {}), 'temperature': random_temperature(rng, temperature_range)}
                            if temperature_range else extra_body)
                wave.append(Batch(number, tone, count, build_prompt(kind=kind, tone=tone, plans=plans, avoid=avoid, overused=overused),
                                  sampling))
                planned += count
            replies = list(pool.map(lambda batch: request_letters(client, model, batch.prompt, batch.sampling, think_temperature), wave))
            staged = []
            for batch, reply in zip(wave, replies):
                candidates = reply.value if reply else []
                valid, rejected = accept_variants(candidates, kind=kind, existing=kept, next_id=next_id)
                valid = valid[:batch.count]  # the model sometimes returns more than asked for
                kept.extend(valid)  # provisionally, so the next batch in the wave is checked against these
                staged.append((batch, len(candidates), valid, rejected))
            if check:
                to_check = [letter for _, _, valid, _ in staged for letter in valid]
                _, flagged = screen(client, model, original, to_check, extra_body, workers=max(4, concurrency))
                failed = {item['letter']['id']: item for item in flagged}
                kept = [letter for letter in kept if letter['id'] not in failed]
                staged = [(batch, n, [l for l in valid if l['id'] not in failed], [*rejected, *(failed[l['id']] for l in valid if l['id'] in failed)])
                          for batch, n, valid, rejected in staged]
            for batch, candidates, accepted, rejected in staged:
                empty_batches = 0 if accepted else empty_batches + 1
                at = f", temperature {batch.sampling['temperature']}" if temperature_range else ''
                log(f'{kind}: batch {batch.number} ({batch.tone}{at}) kept {len(accepted)}/{candidates}, total {len(kept) - 1}/{target}')
                for item in rejected:
                    log(f"  rejected {item['letter']['id']}: {'; '.join(item['errors'])}")
            batches += len(wave)
    return kept[1:]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate letter variants with an OpenAI-compatible endpoint.')
    parser.add_argument('--general', type=int, default=300)
    parser.add_argument('--home', type=int, default=40)
    parser.add_argument('--batch', type=int, default=10)
    parser.add_argument('-c', '--concurrency', type=int, default=1, help='batches requested at once (default 1)')
    parser.add_argument('--out', type=Path, default=LIBRARY, help='where to write the library (default: server/letters.json)')
    add_model_options(parser)
    return finish_model_options(parser, parser.parse_args(argv))


def main(argv: list[str]) -> None:
    args = parse_args(argv)
    # Hand-written and reviewed letters are kept; earlier generated ones are replaced.
    originals = [letter for letter in load_library() if not letter.get('generated')]
    client = make_client(args)
    options = {'batch_size': args.batch, 'extra_body': args.extra_body, 'check': args.check, 'temperature_range': args.temperature_range,
               'think_temperature': args.think_temperature, 'concurrency': args.concurrency}
    general = generate(client, args.model, originals, kind='general', target=args.general, **options)
    east = generate(client, args.model, originals, kind='home', target=args.home, **options)
    out = write_library(args.out, [*originals, *general, *east])
    print(f'Wrote {len(originals) + len(general) + len(east)} letters ({len(general)} general, {len(east)} Ottawa Centre variants) to {out}')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (RuntimeError, openai.APIError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
