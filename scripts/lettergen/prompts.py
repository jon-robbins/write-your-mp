"""The prompts sent to the model: a system prompt shared by every letter request, a user prompt per
request, and the checker's prompt."""
from .content import (AUDIENCE, BACKGROUND, BEATS, CALL_TO_ACTION, COMMENTARY, EXACT_TERMS, OPENING, OPENING_LEADS, SIGNATURE,
                      STANCES, LetterPlan)


def notes(lines: list[str]) -> str:
    return '\n'.join(f'- {line}' for line in lines)


SYSTEM_PROMPT = f"""You write constituent letters for an advocacy campaign by Northbridge Newcomer Alliance, a Canadian nonprofit. Each letter is a draft that a real constituent will review, edit and send to their MP from their own email, under their own name. It must read as a natural letter from an individual.

The notes in each request are written in clipped shorthand on purpose. Never copy their wording or their style: turn them into full, natural sentences in your own words. Keep these exactly as written: {EXACT_TERMS}.

Every letter follows this outline, using the notes the request gives for each part:

1. Opening. The first paragraph says the sender is a constituent of {{riding}}, who Teo Castell is, and that they are asking for the MP's help moving his application forward, so the reader knows the whole problem from the start. Lead with the part the request names. Keep it to two or three sentences.

2. Details. Cover every detail beat, in the order the request gives. Do not turn each note into its own sentence: combine and reword the facts so they read as one connected account. State each fact once in the letter; later parts may refer back to it but not repeat it.

3. Why it matters. Express the stance the request gives. It is a theme, not a phrase: put it in your own words, and never write "It is a shame" or "This is a shame". Then use one to three of the commentary points offered, as opinion. They add no new facts.

4. Call to action. Every letter ends with exactly one call to action, as its last paragraph. It may also ask to hear back from the MP's office. After it, the letter may close with one or two short lines, such as a thank-you or a final word of feeling in your own words, before the sign-off. Apart from the brief ask in the opening, make no other requests anywhere in the letter.

Never write any of the following. Earlier drafts invented them:
- Praise the notes do not give, such as "model citizen", "hard-working", "talented" or "an asset to any community".
- Descriptions of his record or risk, such as "vetted", a "clean" or "safe" travel history, "without incident", "low-risk", "poses no risk" or "a history of compliance".
- That information was or was not "requested". No additional information has been provided; that is all that is known.
- A job offer, family in Canada, an appeal, or any immigration program other than private sponsorship for permanent residence.
- Anything about the sender's own life: that they volunteer, donate, have sponsored refugees themselves, or any other personal history. The sender is simply a constituent.
- New dates, numbers, places, people, quotes, statistics or events.

Format:
- Plain text only: no Markdown, asterisks or italics.
- Keep {{mpName}} in the greeting and {{riding}} in the opening, braces included.
- End with a sign-off line such as "Sincerely,", then a blank line, then exactly:
{SIGNATURE}
- Use Canadian spelling.
- Reply with only a JSON object of the form {{"letters": [{{"subject": "...", "body": "..."}}]}}."""

CHECK_PROMPT = f"""You check a draft campaign letter. It rewords an original letter, and may also use the approved notes below, which count as supported. Report four things.

unsupported_claims: every claim in the draft that neither the original nor the approved notes make or directly support: praise or descriptions of Teo beyond the notes; statements about his record, risk or vetting; what officials did or did not request; job offers, family, appeals or immigration programs; anything about the sender's own life or habits; and any new date, number, place, person, event, quote or statistic. Quote each briefly from the draft. Do not list opinions, appeals or requests that follow from the facts, differences in wording or order, or the placeholders in braces.

missing_background: each background fact the draft leaves out or gets wrong, in a few words. The stance counts however it is worded. Judge facts, not wording: "his sponsors" covers Northbridge Newcomer Alliance once it has been named, and a fact counts wherever in the letter it appears.

opening_problem: an empty string if the first paragraph, on its own, tells the reader the whole problem: the sender is a constituent, who Teo Castell is, and that they want the MP's help moving his application forward. Otherwise, what is missing or out of place in a few words, for example details such as where he lives coming before the problem is stated.

call_to_action_problem: an empty string if the draft ends with exactly one call to action (asking the MP to contact Immigration, Refugees and Citizenship Canada and the Minister of Immigration's office) as its last paragraph. These are fine and not problems: a brief ask for the MP's help in the opening paragraph, saying the MP can help, asking to hear back from the MP's office, and one or two short closing lines after the call to action such as thanks or a final word of feeling. Otherwise, the problem in a few words.

Approved notes, written in shorthand:
Background (every letter needs all of it):
{notes(BACKGROUND)}
Commentary (a letter may use some):
{notes(COMMENTARY)}
Call to action, for MPs other than Ottawa Centre's:
- {CALL_TO_ACTION['general']}
Call to action, for the MP for Ottawa Centre (the sponsors' own riding):
- {CALL_TO_ACTION['home']}

Reply with only a JSON object of the form {{"unsupported_claims": ["..."], "missing_background": ["..."], "opening_problem": "", "call_to_action_problem": ""}}."""


def beats_block(order: tuple[str, ...] | list[str]) -> str:
    return notes([note for beat in order for note in BEATS[beat]])


def build_prompt(*, kind: str, tone: str, plans: list[LetterPlan], avoid: list[str], overused: list[str] = ()) -> str:
    """The request for len(plans) letters, each with its own opening lead, order of detail beats and stance. `avoid`
    lists openings already used; `overused`, wordings already common across letters, to be said differently."""
    count = len(plans)
    if count == 1:
        plan = plans[0]
        request = 'Write one letter.'
        opening = f'1. Opening. {OPENING_LEADS[plan.lead]}\n{notes(OPENING)}'
        details = f'2. Details, in this order:\n{beats_block(plan.order)}'
        stance = f'3. Why it matters. Stance:\n- {STANCES[plan.stance]}'
        choose = 'use one to three of these'
    else:
        request = f'Write {count} distinct letters.'
        labelled = lambda options: '\n'.join(f'[{key}] {text}' for key, text in options.items())
        beats = '\n'.join(f'[{beat}]\n{beats_block([beat])}' for beat in BEATS)
        per_letter = '\n'.join(f'- Letter {n}: opening lead {plan.lead}; details {", ".join(plan.order)}; stance {plan.stance}'
                                for n, plan in enumerate(plans, start=1))
        opening = f'1. Opening:\n{notes(OPENING)}\nOpening leads:\n{labelled(OPENING_LEADS)}'
        details = f'2. Details. Every letter covers all of these beats:\n{beats}'
        stance = f'3. Why it matters. Stances:\n{labelled(STANCES)}\n\nEach letter\'s plan:\n{per_letter}'
        choose = 'use one to three of these, choosing a different mix for each letter'
    avoid_block = f'\nDo not reuse these openings, which earlier letters already used:\n{notes(avoid)}\n' if avoid else ''
    if overused:
        avoid_block += (f'\nThese wordings already appear in many letters. Say the same things in different words, '
                        f'so this letter does not read like a copy:\n{notes(list(overused))}\n')
    return f"""{request}

{AUDIENCE[kind]}

Tone: {tone}.

{opening}

{details}

{stance}
Commentary, {choose}:
{notes(COMMENTARY)}

4. Call to action, as the last paragraph:
- {CALL_TO_ACTION[kind]}

Vary the subject line, the wording of the opening, sentence structure and length (150 to 380 words).
{avoid_block}"""


def check_request(original: dict, letter: dict) -> str:
    return (f"Original letter:\nSubject: {original['subject']}\n\n{original['body']}\n\n"
            f"Draft:\nSubject: {letter['subject']}\n\n{letter['body']}")


def build_messages(prompt: str, system: str = SYSTEM_PROMPT) -> list[dict]:
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]
