"""Reading and writing the letter library in server/letters.json."""
import json
import subprocess
from pathlib import Path

from .content import ORIGINALS

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / 'server' / 'letters.json'
VALIDATOR = ROOT / 'scripts' / 'validate-letters.mjs'


def load_library() -> list[dict]:
    return json.loads(LIBRARY.read_text(encoding='utf-8'))


def find_original(library: list[dict], kind: str) -> dict:
    original = next((letter for letter in library if letter['id'] == ORIGINALS[kind]), None)
    if original is None:
        raise RuntimeError(f'Original letter {ORIGINALS[kind]} is missing from the library')
    return original


def write_library(out: Path, letters: list[dict]) -> Path:
    """Writes the library only if the whole of it passes release validation, so a bad run never replaces a good file."""
    out = out.resolve()
    tmp = out.with_name(out.name + '.tmp')
    tmp.write_text(json.dumps(letters, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    check = subprocess.run(['node', str(VALIDATOR), '--release', str(tmp)], capture_output=True, text=True, check=False)
    if check.returncode != 0:
        tmp.unlink()
        raise RuntimeError(f'Generated library failed validation:\n{check.stderr.strip()}')
    tmp.replace(out)
    return out
