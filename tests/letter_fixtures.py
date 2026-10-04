"""Shared fixtures for the letter generator tests: a letter that passes every rule, a fake
OpenAI-compatible client, and canned replies."""
import json
import sys
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

from lettergen import rules  # noqa: E402

library = json.loads((Path(__file__).resolve().parent.parent / 'server' / 'letters.json').read_text(encoding='utf-8'))
originals = [letter for letter in library if not letter.get('generated')]
original = next(letter for letter in library if letter['id'] == 'original')
sig = '{firstName} {lastName}\n{street}\n{city}, {province} {postalCode}'


def good(opening: str) -> dict:
    """A letter that passes release validation and ends with the call to action."""
    return {
        'subject': 'Please help resolve Teo Castell’s application delay',
        'body': f'Dear {{mpName}},\n\n{opening} As a constituent of {{riding}}, I ask for your help with the application of Teo Castell, a stateless man privately sponsored by Northbridge Newcomer Alliance. His permanent residence application has been in security screening for 11 months, and his sponsors have been ready since March 2026. He lives in Lisbon. Please contact Immigration, Refugees and Citizenship Canada and the Minister of Immigration’s office.\n\nSincerely,\n\n{sig}',
    }


def completion(content, refusal=None, finish_reason='stop', reasoning=None):
    message = SimpleNamespace(content=content, refusal=refusal, reasoning=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def letter_reply(text, reasoning='thought it through'):
    return completion(json.dumps({'letters': [good(text)]}), reasoning=reasoning)


def checker_says(*claims, missing=(), opening='', action='', reasoning=None):
    return completion(json.dumps({'unsupported_claims': list(claims), 'missing_background': list(missing),
                                  'opening_problem': opening, 'call_to_action_problem': action}), reasoning=reasoning)


class FakeClient:
    """Records each chat completion request and answers with respond(call_number, params)."""

    def __init__(self, respond):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._respond = respond

    def _create(self, **params):
        self.calls.append(params)
        return self._respond(len(self.calls), params)


def schema_of(params) -> str:
    return params['response_format']['json_schema']['name']


def counter(prefix):
    serials = iter(range(1, 1000))
    return lambda: f'{prefix}-{next(serials)}'


def allow_similar_letters():
    """Fixture letters share most of their wording on purpose; the similarity rule has its own test.
    Start the returned patcher in setUpModule and stop it in tearDownModule."""
    return unittest.mock.patch.object(rules, 'MAX_SHARED_PHRASING', 1.0)
