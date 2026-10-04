"""What a generated letter must pass to be kept, without asking the model: the release validator
(scripts/validate-letters.mjs, so the rules live in one place), the call to action at the end, and
not reading as a copy of a letter already kept."""
import collections
import json
import re
import subprocess
from typing import Callable

from .library import VALIDATOR

# Two letters sharing more of their six-word phrases than this read as copies of each other. The
# varied trial's closest pair shared 27%; the repetitive one reached 34%.
MAX_SHARED_PHRASING = 0.30

# After the call to action a letter may close with up to two short lines: thanks, a request to hear
# back, or a last word of feeling such as "Canada can do better." Anything longer buries the ask.
CLOSING_LINES = 2
CLOSING_WORDS = 40
# Words of the names letters must keep exactly. Phrases containing them cannot be reworded, so they are not
# counted as repetition; everything else, facts included, can be said in many ways.
NAME_WORDS = re.compile(r"teo|castell|northbridge|newcomer|alliance|lisbon|immigration|refugees|citizenship|minister|"
                        r"permanent|residence|riding|mpname|march|2026|11", re.IGNORECASE)
# A wording already in this share of letters (and at least three) is passed to later requests to avoid.
OVERUSED_SHARE = 0.3
ASKS_FOR_CONTACT = re.compile(r'Minister of Immigration|Immigration, Refugees and Citizenship Canada|\bIRCC\b')

VALIDATE_EACH = """
import { validateLetters } from %s;
let input = '';
for await (const chunk of process.stdin) input += chunk;
const letters = JSON.parse(input);
console.log(JSON.stringify(letters.map((letter) => validateLetters([letter], { release: true }))));
"""


def normalise(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def opening(body: str) -> str:
    """The first line after the greeting."""
    return next((line.strip() for line in body.split('\n') if line.strip() and not re.match(r'dear\b', line.strip(), re.IGNORECASE)), '')


def letter_text(letter: dict) -> str:
    """The part of a letter that varies: everything before the signature block."""
    return letter['body'].split('\n{firstName}', 1)[0]


def phrases(text: str, size: int = 6) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def shared_phrasing(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def body_paragraphs(letter: dict) -> list[str]:
    """The paragraphs between the greeting and the signature block."""
    paragraphs = [p.strip() for p in letter_text(letter).split('\n\n') if p.strip()]
    if paragraphs and '{mpName}' in paragraphs[0] and len(paragraphs[0].split()) <= 6:
        paragraphs = paragraphs[1:]  # the greeting, with or without "Dear"
    return paragraphs


def opens_with_summary(letter: dict) -> bool:
    """True when the first paragraph says where the sender lives, names Teo and mentions his application."""
    paragraphs = body_paragraphs(letter)
    return bool(paragraphs) and all(re.search(p, paragraphs[0], re.IGNORECASE) for p in (r'\{riding\}', r'Teo|Castell', r'applica|sponsor'))


def shared_phrases(letters: list[dict], size: int = 5, top: int = 3) -> list[tuple[str, int]]:
    """The wordings most letters share, apart from exact names, most common first; overlapping phrases count once."""
    counts = collections.Counter(gram for letter in letters for gram in phrases(letter_text(letter), size)
                                 if not any(NAME_WORDS.fullmatch(word) for word in gram))
    picked: list[tuple[str, int]] = []
    for gram, times in sorted(counts.items(), key=lambda item: (-item[1], item[0])):  # ties alphabetically, for repeatability
        if times < 2 or len(picked) == top:
            break
        if not any(len(set(gram) & set(other.split())) >= size - 2 for other, _ in picked):
            picked.append((' '.join(gram), times))
    return picked


def overused_phrases(letters: list[dict], top: int = 8) -> list[str]:
    """Wordings so common among these letters that the next ones should say the same thing differently."""
    if len(letters) < 3:
        return []
    return [text for text, times in shared_phrases(letters, top=top) if times >= max(3, OVERUSED_SHARE * len(letters))]


def ends_with_call_to_action(letter: dict) -> bool:
    """True when the call to action (contact IRCC or the Minister) is the last paragraph, apart from short closing lines."""
    paragraphs = body_paragraphs(letter)
    if paragraphs and len(paragraphs[-1].split()) <= 4 and paragraphs[-1].endswith(','):
        paragraphs = paragraphs[:-1]  # the sign-off line
    for _ in range(CLOSING_LINES):
        if paragraphs and len(paragraphs[-1].split()) < CLOSING_WORDS and not ASKS_FOR_CONTACT.search(paragraphs[-1]):
            paragraphs = paragraphs[:-1]
    return bool(paragraphs) and bool(ASKS_FOR_CONTACT.search(paragraphs[-1]))


def validate_each(letters: list[dict]) -> list[list[str]]:
    """Release validation errors for each letter, from the JS validator."""
    if not letters:
        return []
    result = subprocess.run(['node', '--input-type=module', '-e', VALIDATE_EACH % json.dumps(VALIDATOR.as_uri())],
                            input=json.dumps(letters), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f'Letter validator failed: {result.stderr.strip()}')
    return json.loads(result.stdout)


class Seen:
    """The letters kept so far, for spotting duplicates and near-copies."""

    def __init__(self, letters: list[dict]):
        self.bodies, self.openings, self.phrasing = set(), set(), []
        for letter in letters:
            self.add(letter)

    def add(self, letter: dict) -> None:
        self.bodies.add(normalise(letter['body']))
        self.openings.add(normalise(opening(letter['body']))[:80])
        self.phrasing.append((letter['id'], phrases(letter_text(letter))))

    def problems(self, letter: dict, limit: float) -> list[str]:
        errors = []
        if normalise(letter['body']) in self.bodies or normalise(opening(letter['body']))[:80] in self.openings:
            errors.append('duplicates an existing letter')
        own = phrases(letter_text(letter))
        share, closest = max(((shared_phrasing(own, other), other_id) for other_id, other in self.phrasing), default=(0.0, ''))
        if share > limit:
            errors.append(f'too similar to {closest} ({share:.0%} shared phrasing)')
        return errors


def make_letter(candidate: dict, kind: str, letter_id: str) -> dict:
    return {
        'id': letter_id,
        'status': 'approved',
        'generated': True,
        **({'ridings': ['Ottawa Centre']} if kind == 'home' else {}),
        'subject': candidate['subject'].strip(),
        'body': candidate['body'].strip(),
    }


def accept_variants(candidates: list[dict], *, kind: str, existing: list[dict], next_id: Callable[[], str],
                    max_overlap: float | None = None):
    """Keeps only variants that pass release validation and are not copies of anything already kept."""
    limit = MAX_SHARED_PHRASING if max_overlap is None else max_overlap
    letters = [make_letter(candidate, kind, next_id()) for candidate in candidates]
    seen = Seen(existing)
    accepted, rejected = [], []
    for letter, validation_errors in zip(letters, validate_each(letters)):
        errors = list(validation_errors)
        if not opens_with_summary(letter):
            errors.append('does not open with the summary (riding, Teo and his application)')
        if not ends_with_call_to_action(letter):
            errors.append('does not end with the call to action')
        errors += seen.problems(letter, limit)
        if errors:
            rejected.append({'letter': letter, 'errors': errors})
        else:
            seen.add(letter)
            accepted.append(letter)
    return accepted, rejected
