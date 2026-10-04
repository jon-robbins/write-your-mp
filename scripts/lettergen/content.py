"""What the letters say, for the fictional demo campaign: a stateless man, privately sponsored by a Canadian
nonprofit, whose application to come to Canada is stuck. The original letter is split into three parts: all of
the background, some of the commentary, and one call to action at the end. The notes are clipped on purpose:
when the model was given polished sentences, it copied them into every letter. To run a different campaign,
replace this file, the facts in scripts/validate-letters.mjs and the originals in server/letters.json."""
import random
from dataclasses import dataclass

ORIGINALS = {'general': 'original', 'home': 'home-original'}
SIGNATURE = '{firstName} {lastName}\n{street}\n{city}, {province} {postalCode}'

TONES = [
    'formal and concise',
    'warm and personal, without saying anything about the sender beyond being a constituent',
    'direct and urgent',
    'measured and focused on fairness in the process',
    'brief: under 200 words',
    'respectful and conversational',
    'emphasising what each month of delay costs him',
    'emphasising that he has no country to return to, using only the facts given',
]

# Each letter follows the same outline: an opening that says who is writing, who Teo is and what they
# ask; the details; why it matters; and the call to action. The opening is fixed so every letter makes
# sense from its first lines. The details come in beats, shuffled per letter, which varies the letters
# without leaving the reader lost: a fully shuffled background read incoherently.
OPENING = [
    'Sender: constituent of {riding}.',
    'Teo Castell: stateless, no citizenship anywhere. Northbridge Newcomer Alliance, Canadian nonprofit, sponsors him '
    'to come to Canada.',
    'Ask: MP help move his application forward.',
]
# Ways into the opening. With one fixed opening, every letter began "I am a constituent of {riding}",
# so each letter leads with a different part of it; the paragraph still covers all three.
OPENING_LEADS = {
    'ask': 'Lead with the request: the MP\'s help moving Teo\'s application forward. Then who he is, and that the sender is a constituent of {riding}.',
    'person': 'Lead with who Teo is: a stateless man with no citizenship anywhere. Then the request, and that the sender is a constituent of {riding}.',
    'sponsor': ('Lead with the sponsorship: Northbridge Newcomer Alliance, a Canadian nonprofit, is sponsoring Teo to come to '
                'Canada. Then who Teo is, the request, and that the sender is a constituent of {riding}.'),
}
BEATS = {
    'application': ['Permanent residence application, private sponsorship: submitted complete.',
                    '11 months: stuck. Security screening.',
                    'Additional information from government: none provided.'],
    'sponsors': ['Sponsors ready since March 2026: housing, settlement support in place.'],
    'stateless': ['Stateless since birth: no passport, no citizenship. Lives in Lisbon on temporary humanitarian permit, '
                  'renewed each year.'],
}
# The stance is a theme, not a line: given one fixed note, most letters repeated it word for word.
# Each letter gets one framing of the theme to put in its own words.
STANCES = {
    'welcome': 'Stance: Canada should keep its door open to stateless people.',
    'must': 'Stance: we must stand by people with no country to call home.',
    'better': 'Stance: Canada can do better by stateless people.',
    'fails': 'Stance: this delay fails someone who has no other country to turn to.',
}
# What the checker requires, however the letter words it.
STANCE = 'Stance, in any wording: Canada should help stateless people find a home.'
BACKGROUND = [*OPENING, *(line for lines in BEATS.values() for line in lines), STANCE]

COMMENTARY = [
    'Without citizenship: cannot travel freely, work securely, or plan a future.',
    'Every month of delay: another month without protection.',
    'Canada proud record: welcoming refugees through private sponsorship.',
    'Why so hard for him to reach Canada when sponsors stand ready?',
    'Community ready to welcome him. MP can help.',
]

CALL_TO_ACTION = {
    'general': ("Contact Immigration, Refugees and Citizenship Canada and Minister of Immigration's office: status, "
                'review application as soon as possible.'),
    'home': ("As MP for the riding where the sponsors are based, contact Immigration, Refugees and Citizenship Canada and "
             "Minister of Immigration's office: status, review application as soon as possible."),
}

AUDIENCE = {
    'general': 'These letters go to MPs other than the MP for Ottawa Centre.',
    'home': ('These letters go to the MP for Ottawa Centre, the riding where Northbridge Newcomer Alliance is based. Work '
             'that naturally into the opening. Do not refer to the MP in the third person.'),
}

EXACT_TERMS = ('Teo Castell, Northbridge Newcomer Alliance, permanent residence, 11 months, March 2026, Lisbon, '
               "Immigration, Refugees and Citizenship Canada, and the Minister of Immigration's office")


ID_PREFIX = {'general': 'gen', 'home': 'gen-home'}


@dataclass(frozen=True)
class LetterPlan:
    """The choices made for one letter before the model writes it."""
    lead: str
    order: tuple[str, ...]
    stance: str


def plan_letter(rng: random.Random) -> LetterPlan:
    """A random opening lead, order of detail beats and stance for one letter."""
    return LetterPlan(rng.choice(list(OPENING_LEADS)), tuple(rng.sample(list(BEATS), len(BEATS))), rng.choice(list(STANCES)))
