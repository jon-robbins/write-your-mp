import random
import unittest

from letter_fixtures import original, sig
from lettergen.content import (BACKGROUND, BEATS, CALL_TO_ACTION, COMMENTARY, OPENING, OPENING_LEADS, STANCE, STANCES, LetterPlan,
                               plan_letter)
from lettergen.prompts import CHECK_PROMPT, SYSTEM_PROMPT, build_messages, build_prompt, check_request

ORDER = ('sponsors', 'stateless', 'application')
PLAN = LetterPlan('ask', ORDER, 'welcome')


class PlanTest(unittest.TestCase):
    def test_plans_vary_the_lead_detail_order_and_stance(self):
        rng = random.Random(1)
        plans = [plan_letter(rng) for _ in range(60)]
        self.assertTrue(all(sorted(plan.order) == sorted(BEATS) for plan in plans))
        self.assertEqual({plan.order[0] for plan in plans}, set(BEATS))
        self.assertEqual({plan.lead for plan in plans}, set(OPENING_LEADS))
        self.assertEqual({plan.stance for plan in plans}, set(STANCES))


class BuildPromptTest(unittest.TestCase):
    def test_follows_the_outline_opening_details_why_it_matters_call_to_action(self):
        prompt = build_prompt(kind='general', tone='formal and concise', plans=[PLAN], avoid=[])
        self.assertIn('Write one letter.', prompt)
        sections = [f"1. Opening. {OPENING_LEADS['ask']}", OPENING[0], '2. Details, in this order:', '3. Why it matters. Stance:',
                    STANCES['welcome'], '4. Call to action, as the last paragraph:']
        positions = [prompt.index(section) for section in sections]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(all(note in prompt for note in [*OPENING, *(line for lines in BEATS.values() for line in lines)]))
        self.assertTrue(all(STANCES[other] not in prompt for other in STANCES if other != 'welcome'))

    def test_one_letter_lists_the_details_in_its_own_order(self):
        prompt = build_prompt(kind='general', tone='t', plans=[PLAN], avoid=[])
        positions = [prompt.index(BEATS[beat][0]) for beat in ORDER]
        self.assertEqual(positions, sorted(positions))

    def test_a_batch_gives_each_letter_its_own_plan(self):
        plans = [LetterPlan('person', ORDER, 'must'), LetterPlan('sponsor', tuple(reversed(ORDER)), 'fails')]
        prompt = build_prompt(kind='general', tone='formal and concise', plans=plans, avoid=['An earlier opening'])
        self.assertIn('Write 2 distinct letters.', prompt)
        self.assertIn('- Letter 1: opening lead person; details sponsors, stateless, application; stance must', prompt)
        self.assertIn('- Letter 2: opening lead sponsor; details application, stateless, sponsors; stance fails', prompt)
        self.assertTrue(all(f'[{lead}] {text}' in prompt for lead, text in OPENING_LEADS.items()))
        self.assertTrue(all(f'[{key}] {text}' in prompt for key, text in STANCES.items()))
        self.assertTrue(all(f'[{beat}]' in prompt for beat in BEATS))
        self.assertIn('An earlier opening', prompt)
        self.assertIn('choosing a different mix for each letter', prompt)

    def test_carries_the_tone_commentary_and_call_to_action(self):
        prompt = build_prompt(kind='general', tone='formal and concise', plans=[PLAN], avoid=[])
        self.assertIn('Tone: formal and concise.', prompt)
        for point in COMMENTARY:
            self.assertIn(point, prompt)
        self.assertIn(f"4. Call to action, as the last paragraph:\n- {CALL_TO_ACTION['general']}", prompt)
        self.assertIn('MPs other than the MP for Ottawa Centre', prompt)
        self.assertNotIn(original['body'], prompt)

    def test_commentary_ends_on_the_community_ready_to_welcome_him(self):
        self.assertTrue(any('ready to welcome him' in point and 'MP can help' in point for point in COMMENTARY))

    def test_wordings_already_common_are_passed_on_to_be_said_differently(self):
        prompt = build_prompt(kind='general', tone='t', plans=[PLAN], avoid=[], overused=['i am a constituent of'])
        self.assertIn('These wordings already appear in many letters. Say the same things in different words', prompt)
        self.assertIn('- i am a constituent of', prompt)
        self.assertNotIn('already appear in many letters', build_prompt(kind='general', tone='t', plans=[PLAN], avoid=[]))

    def test_home_prompt_tells_the_mp_the_sponsors_are_in_their_riding(self):
        prompt = build_prompt(kind='home', tone='t', plans=[PLAN], avoid=[])
        self.assertIn('the riding where Northbridge Newcomer Alliance is based', prompt)
        self.assertIn('Do not refer to the MP in the third person', prompt)
        self.assertIn(CALL_TO_ACTION['home'], prompt)
        self.assertNotIn(CALL_TO_ACTION['general'], prompt)


class SystemPromptTest(unittest.TestCase):
    def test_the_shared_rules_go_in_the_system_message(self):
        messages = build_messages('the user prompt')
        self.assertEqual([m['role'] for m in messages], ['system', 'user'])
        self.assertEqual(messages[1]['content'], 'the user prompt')
        for text in [sig, '{mpName}', '{riding}', '"model citizen"', '"vetted"', '"requested"', 'no Markdown', 'Never copy their wording',
                     'exactly one call to action', 'The first paragraph says the sender is a constituent of {riding}',
                     'Do not turn each note into its own sentence', 'Apart from the brief ask in the opening',
                     'State each fact once in the letter', 'Lead with the part the request names',
                     'It is a theme, not a phrase', 'never write "It is a shame" or "This is a shame"']:
            self.assertIn(text, SYSTEM_PROMPT)
        self.assertNotIn(BACKGROUND[0], SYSTEM_PROMPT)
        self.assertNotIn(COMMENTARY[0], SYSTEM_PROMPT)

    def test_no_example_wording_or_instructions_written_as_notes(self):
        # Trials copied the example "Canada can do better.", wrote "Can ask hear back" into a letter, and repeated
        # "life abroad already described" from a note that carried an instruction.
        self.assertNotIn('Canada can do better', SYSTEM_PROMPT)
        for text in [*CALL_TO_ACTION.values(), *COMMENTARY]:
            self.assertNotIn('Can ', text)
            self.assertNotIn('described', text)

    def test_the_checker_sees_every_approved_note_and_both_letters(self):
        for note in [*BACKGROUND, *COMMENTARY, CALL_TO_ACTION['general'], CALL_TO_ACTION['home']]:
            self.assertIn(note, CHECK_PROMPT)
        self.assertIn(STANCE, CHECK_PROMPT)
        for allowed in ['a brief ask for the MP\'s help in the opening paragraph', 'asking to hear back from the MP\'s office',
                        'saying the MP can help', 'The stance counts however it is worded',
                        'opening_problem: an empty string if the first paragraph, on its own, tells the reader the whole problem',
                        'Judge facts, not wording']:
            self.assertIn(allowed, CHECK_PROMPT)
        request = check_request(original, {'subject': 'S', 'body': 'Draft body.'})
        self.assertIn(original['body'], request)
        self.assertIn('Subject: S\n\nDraft body.', request)


if __name__ == '__main__':
    unittest.main()
