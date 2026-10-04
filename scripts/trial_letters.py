# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.40"]
# ///
"""Trial run for reviewing letter quality before a real generation run. Each letter blends two
tones at one of several temperatures, and the report records the tones, the exact prompt, the
sampling settings, how much the model reasoned, and the output, with the release validation,
an optional checker pass and a wider net of suspect phrases. Nothing is written to
server/letters.json.

    scripts/trial-letters.sh 100      # wrapper with the usual settings
"""
import argparse
import collections
import itertools
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import openai

from lettergen.content import BEATS, ID_PREFIX, ORIGINALS, TONES, LetterPlan, plan_letter
from lettergen.library import find_original, load_library
from lettergen.model import (Reply, add_model_options, check_letter, checker_problems, finish_model_options, make_client,
                             random_temperature, request_letters)
from lettergen.prompts import CHECK_PROMPT, SYSTEM_PROMPT, build_prompt
from lettergen.rules import (accept_variants, body_paragraphs, letter_text, opening, overused_phrases, phrases, shared_phrases,
                             shared_phrasing)

SEPARATOR = '=' * 50

# Where each detail beat shows up in a letter, to report the order the model actually used.
BEAT_MARKERS = {
    'application': re.compile(r'security screening', re.IGNORECASE),
    'sponsors': re.compile(r'March 2026'),
    'stateless': re.compile(r'Lisbon'),
}

# Wider than the validator's rejections: words that often signal an invented claim and are worth
# a human look, but can also appear innocently.
SUSPECT_PHRASES = re.compile(
    r'\b(talented|gifted|brilliant|hard-?working|model (citizen|immigrant)|asset to|'
    r'safely|legally|lawfully|complian\w*|security threat|good standing|well-documented|credentials|'
    r'appeal|tourist|work visa|asylum claim|bias\w*|discriminat\w*|racis\w*|decades?|for (many )?years|'
    r'I (have )?(attended|seen|saw|watched|met)|my (family|children|kids|husband|wife|partner)|'
    r'as an? (parent|teacher|volunteer|donor|sponsor|immigrant|refugee) (myself|too))\b',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Trial:
    number: int
    kind: str
    tones: tuple[str, str]
    temperature: float
    beats: tuple[str, ...] = tuple(BEATS)
    lead: str = 'person'
    stance: str = 'must'

    @property
    def plan(self) -> LetterPlan:
        return LetterPlan(self.lead, self.beats, self.stance)


@dataclass(frozen=True)
class Response:
    trial: Trial
    prompt: str
    sampling: dict
    letter: dict | None
    reasoning: str = ''
    check: Reply | None = None
    tokens: tuple[int | None, int | None] = (None, None)


@dataclass(frozen=True)
class Result:
    response: Response
    verdict: str
    validation_errors: tuple[str, ...]
    suspects: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.verdict.startswith('accepted')


def plan_trials(count: int, home: int, temperatures: list[float], seed: int,
                temperature_range: tuple[float, float] | None = None) -> list[Trial]:
    """Spreads every pair of distinct tones across the temperatures, in a shuffled but repeatable order,
    and gives each letter its own order of detail beats. With a temperature range, each letter instead
    gets a random temperature from it."""
    rng = random.Random(seed)
    combos = list(itertools.product(itertools.combinations(TONES, 2), [None] if temperature_range else temperatures))
    rng.shuffle(combos)
    kinds = ['general'] * (count - home) + ['home'] * home
    trials = []
    for number, (kind, (tones, temperature)) in enumerate(zip(kinds, itertools.cycle(combos)), start=1):
        plan = plan_letter(rng)
        temperature = temperature if temperature is not None else random_temperature(rng, temperature_range)
        trials.append(Trial(number, kind, tones, temperature, plan.order, plan.lead, plan.stance))
    return trials


def beats_found(letter: dict) -> tuple[str, ...]:
    """The background beats in the order they first appear in the letter body."""
    positions = sorted((match.start(), beat) for beat, marker in BEAT_MARKERS.items() if (match := marker.search(letter['body'])))
    return tuple(beat for _, beat in positions)


def request_trial(client, model: str, originals: list[dict], trial: Trial, extra_body: dict, check: bool,
                  think_temperature: float | None = None, finished: list[dict] | None = None) -> Response:
    tone = f'a blend of two tones, “{trial.tones[0]}” and “{trial.tones[1]}”'
    # Like the real run, steer away from what earlier letters did: here, those that finished before this one started.
    earlier = list(finished or [])
    avoid = [opening(letter['body'])[:90] for letter in earlier[-25:]]
    prompt = build_prompt(kind=trial.kind, tone=tone, plans=[trial.plan], avoid=avoid, overused=overused_phrases(earlier))
    sampling = {**extra_body, 'temperature': trial.temperature}
    reply = request_letters(client, model, prompt, sampling, think_temperature)
    letter = reply.value[0] if reply and reply.value else None
    if letter is None:
        return Response(trial, prompt, sampling, None, reply.reasoning if reply else '')
    # The checker uses the base settings, so its temperature is the server's default for the model.
    verdict = check_letter(client, model, find_original(originals, trial.kind), letter, extra_body) if check else None
    return Response(trial, prompt, sampling, letter, reply.reasoning, verdict, (reply.prompt_tokens, reply.completion_tokens))


class Judge:
    """Applies release validation, duplicate checks and the checker to each letter as it arrives, as the real run
    would. Letters are numbered in the order they are judged."""

    def __init__(self, originals: list[dict], check: bool):
        self.kept = list(originals)
        self.serials = {kind: itertools.count(1) for kind in ORIGINALS}
        self.check = check

    def __call__(self, response: Response) -> Result:
        candidate = response.letter
        if candidate is None:
            return Result(response, 'no usable letter returned', (), ())
        kind = response.trial.kind
        letter_id = f'{ID_PREFIX[kind]}-{next(self.serials[kind]):03d}'
        accepted, rejected = accept_variants([candidate], kind=kind, existing=self.kept, next_id=lambda: letter_id)
        errors = tuple(rejected[0]['errors']) if rejected else ()
        suspects = tuple(dict.fromkeys(m.group(0) for m in SUSPECT_PHRASES.finditer(f"{candidate['subject']}\n{candidate['body']}")))
        if errors:
            verdict = 'rejected by validation'
        elif self.check and response.check is None:
            verdict = 'rejected: the checker gave no usable answer'
        elif self.check and response.check.value:
            verdict = 'rejected by the checker'
        else:
            verdict = f'accepted as {letter_id}'
            self.kept.extend(accepted)
        return Result(response, verdict, errors, suspects)


def judge(responses: list[Response], originals: list[dict], check: bool) -> list[Result]:
    judge_one = Judge(originals, check)
    return [judge_one(response) for response in responses]


def checker_line(response: Response) -> str:
    if response.check is None:
        return 'Checker: no usable answer'
    if not response.check.value:
        return 'Checker: no problems'
    return 'Checker found:\n' + '\n'.join(f'  - {problem}' for problem in response.check.value)


def format_result(result: Result, total: int, check: bool) -> str:
    response = result.response
    trial, letter = response.trial, response.letter
    checker_reasoning = f' (checker: {len(response.check.reasoning)})' if response.check else ''
    lines = [
        f'Letter {trial.number} of {total} · {trial.kind} · {result.verdict}',
        f'Tones: {trial.tones[0]} + {trial.tones[1]}',
        f'Opening lead: {trial.lead}; stance: {trial.stance}',
        f"Detail order asked: {', '.join(trial.beats)}",
        *([f"Detail order found: {', '.join(beats_found(letter))}"] if letter else []),
        f'Temperature settings: {json.dumps(response.sampling, ensure_ascii=False)}',
        f'Reasoning: {len(response.reasoning)} characters{checker_reasoning}',
        tokens_line(response),
        f"Validation: {'; '.join(result.validation_errors) or 'passed'}",
        *([checker_line(response)] if check and letter else []),
        f"Suspect phrases: {', '.join(result.suspects) or 'none'}",
        '',
        '--- Prompt sent to the model (after the system prompt in the header) ---',
        response.prompt,
        '',
        f"--- Output ({len(letter['body'].split())} words) ---" if letter else '--- Output ---',
        f"Subject: {letter['subject']}\n\n{letter['body']}" if letter else '(none)',
    ]
    return '\n'.join(lines)


def phrasing_line(letters: list[dict]) -> str:
    """How alike the accepted letters read: the share of six-word phrases two letters have in common."""
    pairs = [shared_phrasing(a, b) for a, b in itertools.combinations([phrases(letter_text(letter)) for letter in letters], 2)]
    if not pairs:
        return 'Shared phrasing between accepted letters: not enough letters to compare'
    return (f'Shared phrasing between accepted letters: average {sum(pairs) / len(pairs):.0%}, closest pair {max(pairs):.0%} '
            '(the repetitive 10-letter trial averaged 21%)')


def order_line(responses: list[Response]) -> str:
    """How varied the accepted letters' details are: distinct orders, and how many followed the order asked."""
    if not responses:
        return 'Detail order in accepted letters: no letters to compare'
    found = [beats_found(response.letter) for response in responses]
    followed = sum(order == response.trial.beats for order, response in zip(found, responses))
    return (f'Detail order in accepted letters: {len(set(found))} distinct orders among {len(found)} letters, '
            f'{followed} followed the order asked for')


def openings_line(letters: list[dict]) -> str:
    """How varied the first words of the letters are, accepted or not."""
    starts = collections.Counter(' '.join(re.findall(r"[\w{}']+", (body_paragraphs(letter) or [''])[0])[:5]) for letter in letters)
    if not starts:
        return 'Opening words: no letters to compare'
    common, times = starts.most_common(1)[0]
    return f'Opening words: {len(starts)} distinct first five words among {len(letters)} letters; most common "{common}" ({times})'


def repeated_phrases_line(letters: list[dict]) -> str:
    """The wordings most letters share, apart from exact names, to catch stock lines like "This is a shame"."""
    picked = shared_phrases(letters)
    if not picked:
        return 'Most repeated phrases: none shared by two letters'
    return 'Most repeated phrases: ' + ', '.join(f'"{text}" ({times} of {len(letters)})' for text, times in picked)


def tokens_line(response: Response) -> str:
    prompt, completion = response.tokens
    checker = response.check
    checked = (f' (checker: prompt {checker.prompt_tokens}, completion {checker.completion_tokens})'
               if checker and checker.prompt_tokens is not None else '')
    return f'Tokens: prompt {prompt}, completion {completion}{checked}' if prompt is not None else 'Tokens: not reported by the server'


def average_tokens_line(results: list[Result]) -> str | None:
    def average(values: list[int | None]) -> str:
        known = [v for v in values if v is not None]
        return f'{sum(known) // len(known)}' if known else '?'
    responses = [r.response for r in results if r.response.letter is not None and r.response.tokens[0] is not None]
    if not responses:
        return None
    checks = [r.check for r in responses if r.check]
    line = (f'Average tokens per letter: prompt {average([r.tokens[0] for r in responses])}, '
            f'completion {average([r.tokens[1] for r in responses])}')
    if checks:
        line += (f'; checker: prompt {average([c.prompt_tokens for c in checks])}, '
                 f'completion {average([c.completion_tokens for c in checks])}')
    return line


def summary(results: list[Result], check: bool, think_temperature: float | None = None) -> list[str]:
    def row(label: str, group: list[Result]) -> str:
        valid = sum(not r.validation_errors and r.response.letter is not None for r in group)
        checked = f', {sum(r.verdict == "rejected by the checker" for r in group)} rejected by the checker' if check else ''
        return (f'{label}: {sum(r.accepted for r in group)}/{len(group)} accepted, {valid} passed validation{checked}, '
                f'{sum(bool(r.suspects) for r in group)} with suspect phrases')
    temperatures = sorted({r.response.trial.temperature for r in results})
    by_temperature = ([row(f'  temperature {t}', [r for r in results if r.response.trial.temperature == t]) for t in temperatures]
                      if len(temperatures) <= 4 else [f'  temperatures {temperatures[0]} to {temperatures[-1]}, one per letter'])
    thinking = ([f'  reasoning sampled at temperature {think_temperature} in a separate request before each letter']
                if think_temperature is not None else [])
    lines = [row('All letters', results),
             *by_temperature,
             *thinking,
             phrasing_line([r.response.letter for r in results if r.accepted]),
             order_line([r.response for r in results if r.accepted]),
             openings_line([r.response.letter for r in results if r.response.letter]),
             repeated_phrases_line([r.response.letter for r in results if r.response.letter])]
    reasoned = [len(r.response.reasoning) for r in results if r.response.letter]
    if reasoned and not any(reasoned):
        lines.append('Warning: no reasoning came back. If thinking is meant to be on, start vLLM with a reasoning parser '
                     '(--reasoning-parser qwen3); without one, the JSON output format can suppress thinking.')
    elif reasoned:
        lines.append(f'Average reasoning: {sum(reasoned) // len(reasoned)} characters per letter')
    tokens = average_tokens_line(results)
    return [*lines, tokens] if tokens else lines


def report_header(title: str, summary_lines: list[str], check: bool) -> str:
    return '\n'.join([title, *summary_lines, '', '--- System prompt (sent with every letter) ---', SYSTEM_PROMPT,
                      *(['', '--- Checker prompt ---', CHECK_PROMPT] if check else [])])


def format_report(results: list[Result], model: str, check: bool, think_temperature: float | None = None,
                  total: int | None = None) -> str:
    total = total or len(results)
    status = '' if len(results) == total else f' · stopped early: {len(results)} of {total} letters finished'
    header = report_header(f'Letter trial · model {model}{status}', summary(results, check, think_temperature), check)
    return f'\n{SEPARATOR}\n'.join([header, *(format_result(result, total, check) for result in results)]) + '\n'


class ReportWriter:
    """Keeps the report file current while a trial runs: each letter is appended as soon as it is judged, so
    stopping a run loses nothing finished. At the end the file is rewritten in letter order with the summary."""

    def __init__(self, path: Path, model: str, check: bool, think_temperature: float | None, total: int):
        self.path, self.model, self.check, self.think_temperature, self.total = path, model, check, think_temperature, total
        self.results: list[Result] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        title = f'Letter trial · model {model} · in progress: letters appear as they finish, the summary at the end'
        path.write_text(report_header(title, [], check) + '\n', encoding='utf-8')

    def add(self, result: Result) -> None:
        self.results.append(result)
        with self.path.open('a', encoding='utf-8') as report:
            report.write(f'{SEPARATOR}\n{format_result(result, self.total, self.check)}\n')

    def finish(self) -> list[Result]:
        ordered = sorted(self.results, key=lambda result: result.response.trial.number)
        self.path.write_text(format_report(ordered, self.model, self.check, self.think_temperature, self.total), encoding='utf-8')
        return ordered


def progress(response: Response, check: bool) -> str:
    if response.letter is None:
        return 'nothing usable'
    if not check:
        return 'letter returned'
    problems = checker_problems(response.check)
    return f'checker found {len(problems)} problem(s)' if problems else 'checker found no problems'


def run(client, model: str, originals: list[dict], trials: list[Trial], extra_body: dict, *, check: bool = True,
        think_temperature: float | None = None, concurrency: int = 4, report: ReportWriter | None = None,
        log=print) -> list[Result]:
    """Requests every trial letter, judging each and adding it to the report as soon as it finishes. On Ctrl-C,
    pending letters are cancelled and the report is finished with the letters done so far."""
    judge_one, results, finished = Judge(originals, check), [], []
    pool = ThreadPoolExecutor(max_workers=concurrency)
    futures = {pool.submit(request_trial, client, model, originals, trial, extra_body, check, think_temperature, finished): trial
               for trial in trials}
    try:
        for future in as_completed(futures):
            trial = futures[future]
            result = judge_one(future.result())
            results.append(result)
            if result.response.letter:
                finished.append(result.response.letter)
            if report:
                report.add(result)
            log(f'{len(results)}/{len(trials)} letter {trial.number} {trial.kind} [{trial.tones[0]} + {trial.tones[1]}] '
                f'temperature {trial.temperature}: {progress(result.response, check)}, {result.verdict}')
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        if report:
            report.finish()
        raise
    pool.shutdown()
    return report.finish() if report else sorted(results, key=lambda result: result.response.trial.number)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate trial letters that blend two tones and write a review report.')
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--home', type=int, default=10, help='how many of the letters are Ottawa Centre ones')
    parser.add_argument('--temperatures', type=float, nargs='+', default=[0.6, 0.7, 0.8])
    parser.add_argument('-c', '--concurrency', type=int, default=4, help='letters requested at once (default 4)')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--out', type=Path, required=True, help='where to write the text report')
    add_model_options(parser)
    args = finish_model_options(parser, parser.parse_args(argv))
    if not 0 <= args.home <= args.count:
        parser.error('--home must be between 0 and --count')
    return args


def main(argv: list[str]) -> None:
    args = parse_args(argv)
    originals = [letter for letter in load_library() if letter['id'] in ORIGINALS.values()]
    trials = plan_trials(args.count, args.home, args.temperatures, args.seed, args.temperature_range)
    report = ReportWriter(args.out, args.model, args.check, args.think_temperature, len(trials))
    print(f'Report (updated as letters finish): {args.out}')
    try:
        results = run(make_client(args), args.model, originals, trials, args.extra_body, check=args.check,
                      think_temperature=args.think_temperature, concurrency=args.concurrency, report=report)
    except KeyboardInterrupt:
        print(f'\nStopped. {len(report.results)} finished letters and their summary are in {args.out}', file=sys.stderr)
        sys.stderr.flush()
        os._exit(130)  # don't wait for requests still running on the server
    print('\n'.join(summary(results, args.check, args.think_temperature)))
    print(f'Report: {args.out}')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (RuntimeError, openai.APIError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
