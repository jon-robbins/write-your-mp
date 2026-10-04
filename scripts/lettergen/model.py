"""Talking to the OpenAI-compatible endpoint: schema-shaped JSON requests, the letter and checker
calls, and the command-line options both scripts share."""
import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

import openai

from .prompts import CHECK_PROMPT, build_messages, check_request

BATCH_SCHEMA = {
    'type': 'object',
    'properties': {
        'letters': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'subject': {'type': 'string'}, 'body': {'type': 'string'}},
                'required': ['subject', 'body'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['letters'],
    'additionalProperties': False,
}

CHECK_SCHEMA = {
    'type': 'object',
    'properties': {
        'unsupported_claims': {'type': 'array', 'items': {'type': 'string'}},
        'missing_background': {'type': 'array', 'items': {'type': 'string'}},
        'opening_problem': {'type': 'string'},
        'call_to_action_problem': {'type': 'string'},
    },
    'required': ['unsupported_claims', 'missing_background', 'opening_problem', 'call_to_action_problem'],
    'additionalProperties': False,
}

NO_CHECKER_ANSWER = 'the checker gave no usable answer'
THINK_END = '</think>'


@dataclass(frozen=True)
class Reply:
    value: Any
    reasoning: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def parse_json(content: str | None) -> dict | None:
    """Reads a JSON reply, tolerating a leading <think> block and code fences from endpoints that ignore response_format."""
    if not content:
        return None
    text = re.sub(r'^\s*<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def letters_from(data: dict | None) -> list[dict] | None:
    letters = data.get('letters') if isinstance(data, dict) else None
    if not isinstance(letters, list):
        return None
    return [letter for letter in letters
            if isinstance(letter, dict) and isinstance(letter.get('subject'), str) and isinstance(letter.get('body'), str)]


def problems_from(data: dict | None) -> list[str] | None:
    """Turns a checker reply into a list of problems; an empty list means the draft passed."""
    if not isinstance(data, dict):
        return None
    claims, missing = data.get('unsupported_claims'), data.get('missing_background')
    opening, action = data.get('opening_problem'), data.get('call_to_action_problem')
    if not all(isinstance(v, list) for v in (claims, missing)) or not all(isinstance(v, str) for v in (opening, action)):
        return None
    clean = lambda items: [item.strip() for item in items if isinstance(item, str) and item.strip()]
    return ([f'unsupported claim: {claim}' for claim in clean(claims)]
            + [f'missing background: {note}' for note in clean(missing)]
            + ([f'opening: {opening.strip()}'] if opening.strip() else [])
            + ([f'call to action: {action.strip()}'] if action.strip() else []))


def parse_letters(content: str | None) -> list[dict] | None:
    return letters_from(parse_json(content))


def reasoning_of(message) -> str:
    # vLLM returns thinking as `reasoning` (older releases: `reasoning_content`) when it runs a reasoning parser.
    return getattr(message, 'reasoning', None) or getattr(message, 'reasoning_content', None) or ''


def request_json(client, model: str, messages: list[dict], *, schema_name: str, schema: dict,
                 extract: Callable[[dict | None], Any], extra_body: dict | None = None) -> Reply | None:
    """Asks for schema-shaped JSON, retrying refusals, unreadable replies and server errors up to three times."""
    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={'type': 'json_schema', 'json_schema': {'name': schema_name, 'strict': True, 'schema': schema}},
                extra_body=extra_body,
            )
        except openai.AuthenticationError as error:
            raise RuntimeError('Authentication failed: set OPENAI_API_KEY for this endpoint.') from error
        except openai.BadRequestError:
            raise
        except openai.APIError as error:
            print(f'  API error {getattr(error, "status_code", "")} on attempt {attempt}: {error}', file=sys.stderr)
            continue
        choice = response.choices[0]
        if getattr(choice.message, 'refusal', None):
            print(f'  {schema_name} declined ({choice.message.refusal}), attempt {attempt}', file=sys.stderr)
            continue
        # Continuing a message that already holds the reasoning, some reasoning parsers file the answer as reasoning.
        value = extract(parse_json(choice.message.content or reasoning_of(choice.message)))
        if value is None:
            print(f'  {schema_name} reply was not usable (finish_reason {choice.finish_reason}), attempt {attempt}', file=sys.stderr)
            continue
        usage = getattr(response, 'usage', None)
        return Reply(value, reasoning_of(choice.message), getattr(usage, 'prompt_tokens', None), getattr(usage, 'completion_tokens', None))
    return None


def think(client, model: str, messages: list[dict], extra_body: dict | None, temperature: float) -> Reply | None:
    """Pass 1 of a two-pass request: only the model's reasoning, sampled at `temperature`, stopping where it closes
    its thinking. None when the server returns no reasoning, for example with thinking switched off."""
    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(model=model, messages=messages, stop=[THINK_END],
                                                      extra_body={**(extra_body or {}), 'temperature': temperature})
        except openai.AuthenticationError as error:
            raise RuntimeError('Authentication failed: set OPENAI_API_KEY for this endpoint.') from error
        except openai.BadRequestError:
            raise
        except openai.APIError as error:
            print(f'  API error {getattr(error, "status_code", "")} on thinking attempt {attempt}: {error}', file=sys.stderr)
            continue
        message = response.choices[0].message
        text = (reasoning_of(message) or message.content or '').replace('<think>', '').split(THINK_END)[0].strip()
        usage = getattr(response, 'usage', None)
        return Reply(text, text, getattr(usage, 'prompt_tokens', None), getattr(usage, 'completion_tokens', None)) if text else None
    return None


def request_letters(client, model: str, prompt: str, extra_body: dict | None = None,
                    think_temperature: float | None = None) -> Reply | None:
    """Asks for letters. With `think_temperature`, the reasoning is sampled at that temperature in one request and
    the letters at extra_body's temperature in a second that continues from it, since vLLM applies one temperature
    to a whole response."""
    messages = build_messages(prompt)
    ask = lambda msgs, body: request_json(client, model, msgs, schema_name='letter_batch', schema=BATCH_SCHEMA,
                                          extract=letters_from, extra_body=body)
    if think_temperature is None:
        return ask(messages, extra_body)
    thought = think(client, model, messages, extra_body, think_temperature)
    if thought is None:
        print('  thinking pass returned no reasoning; writing in one request instead', file=sys.stderr)
        return ask(messages, extra_body)
    continued = [*messages, {'role': 'assistant', 'content': f'<think>\n{thought.value}\n{THINK_END}\n\n'}]
    reply = ask(continued, {**(extra_body or {}), 'continue_final_message': True, 'add_generation_prompt': False})
    if reply is None:
        return None
    completion = (None if thought.completion_tokens is None or reply.completion_tokens is None
                  else thought.completion_tokens + reply.completion_tokens)
    return Reply(reply.value, '\n'.join(filter(None, [thought.value, reply.reasoning])), thought.prompt_tokens, completion)


def check_letter(client, model: str, original: dict, letter: dict, extra_body: dict | None = None) -> Reply | None:
    """Asks the model for unsupported claims, missing background and call-to-action problems in a draft."""
    return request_json(client, model, build_messages(check_request(original, letter), CHECK_PROMPT), schema_name='letter_check',
                        schema=CHECK_SCHEMA, extract=problems_from, extra_body=extra_body)


def checker_problems(reply: Reply | None) -> list[str]:
    """What stops a letter passing the checker; an empty list means it passed."""
    return [NO_CHECKER_ANSWER] if reply is None else reply.value


def screen(client, model: str, original: dict, letters: list[dict], extra_body: dict | None = None, workers: int = 4):
    """Splits letters into those the checker passes and those with problems (or no checker answer)."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        replies = list(pool.map(lambda letter: check_letter(client, model, original, letter, extra_body), letters))
    passed, failed = [], []
    for letter, reply in zip(letters, replies):
        problems = checker_problems(reply)
        if problems:
            failed.append({'letter': letter, 'errors': problems})
        else:
            passed.append(letter)
    return passed, failed


def add_model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--model', default=os.environ.get('OPENAI_MODEL'))
    parser.add_argument('--base-url', default=os.environ.get('OPENAI_BASE_URL'))
    parser.add_argument('--extra-body', default='{}', help='JSON object merged into every request body')
    parser.add_argument('--temperature-range', type=float, nargs=2, metavar=('LOW', 'HIGH'),
                        help='pick each request\'s temperature at random from this range (overrides any in --extra-body)')
    parser.add_argument('--think-temperature', type=float,
                        help='sample the reasoning at this temperature in a separate request, then write at the usual one')
    parser.add_argument('--check', action=argparse.BooleanOptionalAction, default=True,
                        help='check each letter against the original with a second request (default: on)')


def finish_model_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> argparse.Namespace:
    """Validates the shared options, turning --extra-body into a dict."""
    if not args.model:
        parser.error('set --model or OPENAI_MODEL')
    try:
        args.extra_body = json.loads(args.extra_body)
    except json.JSONDecodeError as error:
        parser.error(f'--extra-body is not valid JSON: {error}')
    if not isinstance(args.extra_body, dict):
        parser.error('--extra-body must be a JSON object')
    if args.temperature_range and args.temperature_range[0] > args.temperature_range[1]:
        parser.error('--temperature-range needs LOW no higher than HIGH')
    if args.think_temperature is not None and args.think_temperature <= 0:
        parser.error('--think-temperature must be above 0')
    return args


def random_temperature(rng, temperature_range: tuple[float, float]) -> float:
    return round(rng.uniform(*temperature_range), 2)


def make_client(args: argparse.Namespace) -> openai.OpenAI:
    # Local servers often need no key, but the client refuses to start without one.
    return openai.OpenAI(base_url=args.base_url, api_key=os.environ.get('OPENAI_API_KEY') or 'unused')
