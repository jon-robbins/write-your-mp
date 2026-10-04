import tempfile
import unittest
import unittest.mock
from pathlib import Path

from letter_fixtures import FakeClient, allow_similar_letters, checker_says, completion, letter_reply, originals, schema_of
from lettergen.content import BEATS, COMMENTARY, OPENING_LEADS, STANCES
from trial_letters import (SEPARATOR, ReportWriter, beats_found, format_report, openings_line, parse_args, plan_trials,
                           repeated_phrases_line, request_trial, run)

_similarity = allow_similar_letters()


def setUpModule():
    _similarity.start()


def tearDownModule():
    _similarity.stop()


def quiet_run(*args, **kwargs):
    with unittest.mock.patch('sys.stderr'):
        return run(*args, concurrency=1, log=lambda _: None, **kwargs)


class PlanTrialsTest(unittest.TestCase):
    def test_each_letter_gets_two_distinct_tones_and_a_listed_temperature(self):
        trials = plan_trials(100, 10, [0.8, 1.1], seed=1)
        self.assertEqual(len(trials), 100)
        self.assertEqual([t.number for t in trials], list(range(1, 101)))
        self.assertTrue(all(t.tones[0] != t.tones[1] for t in trials))
        self.assertEqual({t.temperature for t in trials}, {0.8, 1.1})
        self.assertEqual(sum(t.kind == 'home' for t in trials), 10)

    def test_no_tone_pair_and_temperature_repeats_until_all_are_used(self):
        trials = plan_trials(56, 0, [0.8, 1.1], seed=1)  # 28 tone pairs x 2 temperatures
        self.assertEqual(len({(t.tones, t.temperature) for t in trials}), 56)

    def test_each_letter_gets_its_own_beat_order(self):
        trials = plan_trials(40, 0, [0.6], seed=1)
        self.assertTrue(all(sorted(t.beats) == sorted(BEATS) for t in trials))
        self.assertEqual({t.beats[0] for t in trials}, set(BEATS))
        self.assertEqual({t.lead for t in trials}, set(OPENING_LEADS))
        self.assertEqual({t.stance for t in trials}, set(STANCES))

    def test_a_temperature_range_gives_each_letter_a_random_temperature_from_it(self):
        trials = plan_trials(30, 0, [0.6], seed=1, temperature_range=(0.68, 0.75))
        self.assertTrue(all(0.68 <= t.temperature <= 0.75 for t in trials))
        self.assertGreater(len({t.temperature for t in trials}), 4)

    def test_concurrency_has_a_short_flag(self):
        self.assertEqual(parse_args(['--model', 'm', '--out', 'r.txt', '-c', '12']).concurrency, 12)

    def test_the_plan_is_repeatable_for_a_seed(self):
        self.assertEqual(plan_trials(10, 2, [0.9], seed=3), plan_trials(10, 2, [0.9], seed=3))


class BeatsFoundTest(unittest.TestCase):
    def test_reports_beats_in_the_order_they_appear(self):
        body = 'His sponsors have been ready since March 2026. He lives in Lisbon. He has waited in security screening.'
        self.assertEqual(beats_found({'body': body}), ('sponsors', 'stateless', 'application'))


class OpeningsLineTest(unittest.TestCase):
    def test_counts_distinct_openings_and_names_the_most_common(self):
        letters = [{'body': f'Dear {{mpName}},\n\n{text}\n\nSincerely,'} for text in
                   ['I am a constituent of {riding}, writing.', 'I am a constituent of {riding}, asking.', 'Teo Castell needs his application moved.']]
        self.assertEqual(openings_line(letters),
                         'Opening words: 2 distinct first five words among 3 letters; most common "I am a constituent of" (2)')


class ReportWriterTest(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / 'report.txt'
        self.trials = plan_trials(3, 0, [0.7], seed=1)

    def test_letters_are_written_as_they_finish_and_summarised_at_the_end(self):
        report = ReportWriter(self.out, 'm', False, None, len(self.trials))
        seen = [self.out.read_text(encoding='utf-8')]
        add = report.add
        report.add = lambda result: (add(result), seen.append(self.out.read_text(encoding='utf-8')))
        quiet_run(FakeClient(lambda call, _: letter_reply(f'Opening {call}.')), 'm', originals, self.trials, {}, check=False, report=report)
        self.assertIn('in progress', seen[0])
        self.assertNotIn('Letter 1 of 3', seen[0])
        self.assertIn('Letter 1 of 3', seen[1])
        self.assertIn('Letter 2 of 3', seen[2])
        self.assertNotIn('All letters:', seen[2])
        final = self.out.read_text(encoding='utf-8')
        self.assertIn('All letters: 3/3 accepted', final)
        self.assertNotIn('in progress', final)
        self.assertLess(final.index('Letter 1 of 3'), final.index('Letter 3 of 3'))

    def test_stopping_keeps_the_finished_letters_with_their_summary(self):
        def respond(call, _):
            if call == 2:
                raise KeyboardInterrupt
            return letter_reply(f'Opening {call}.')
        report = ReportWriter(self.out, 'm', False, None, len(self.trials))
        with self.assertRaises(KeyboardInterrupt):
            quiet_run(FakeClient(respond), 'm', originals, self.trials, {}, check=False, report=report)
        final = self.out.read_text(encoding='utf-8')
        self.assertIn('stopped early: 1 of 3 letters finished', final)
        self.assertIn('Letter 1 of 3', final)
        self.assertIn('All letters: 1/1 accepted', final)


class RepeatedPhrasesTest(unittest.TestCase):
    def test_names_the_stock_lines_letters_share_but_not_required_names(self):
        letters = [{'body': f'Dear {{mpName}},\n\n{text} Teo Castell needs Northbridge Newcomer Alliance heard.\n\nSincerely,'} for text in
                   ['This is a shame and we must act now.', 'This is a shame and we must act today.', 'Something else entirely here.']]
        line = repeated_phrases_line(letters)
        self.assertRegex(line, r'^Most repeated phrases: "[^"]*shame[^"]*" \(2 of 3\)$')
        self.assertNotIn('castell', line)

    def test_says_so_when_nothing_repeats(self):
        self.assertEqual(repeated_phrases_line([{'body': 'one two three four five six'}]), 'Most repeated phrases: none shared by two letters')


class RecentOpeningsTest(unittest.TestCase):
    def test_a_trial_letter_steers_away_from_openings_and_wordings_earlier_letters_used(self):
        client = FakeClient(lambda *_: letter_reply('Hello.'))
        earlier = [{'body': f'Dear {{mpName}},\n\nOpening {n}. We must stand by stateless people without delay.\n\nSincerely,'}
                   for n in range(3)]
        request_trial(client, 'm', originals, plan_trials(1, 0, [0.7], seed=1)[0], {}, check=False, finished=earlier)
        prompt = client.calls[0]['messages'][1]['content']
        self.assertIn('Do not reuse these openings, which earlier letters already used:\n- Opening 0.', prompt)
        self.assertIn('These wordings already appear in many letters', prompt)
        self.assertIn('stand by stateless people', prompt)


class RunTest(unittest.TestCase):
    def test_report_records_tones_prompt_settings_reasoning_checker_and_output(self):
        def respond(call, params):
            return checker_says() if schema_of(params) == 'letter_check' else letter_reply(f'Opening number {call}.')
        client = FakeClient(respond)
        trials = plan_trials(2, 0, [0.6], seed=1)
        results = quiet_run(client, 'test-model', originals, trials, {'top_p': 0.95})
        letter_calls = [c for c in client.calls if schema_of(c) == 'letter_batch']
        check_calls = [c for c in client.calls if schema_of(c) == 'letter_check']
        self.assertEqual([c['extra_body'] for c in letter_calls], [{'top_p': 0.95, 'temperature': 0.6}] * 2)
        self.assertEqual([c['extra_body'] for c in check_calls], [{'top_p': 0.95}] * 2)
        self.assertIn(trials[0].tones[0], letter_calls[0]['messages'][1]['content'])
        self.assertIn(COMMENTARY[0], letter_calls[0]['messages'][1]['content'])
        self.assertIn(BEATS[trials[0].beats[0]][0], letter_calls[0]['messages'][1]['content'])
        self.assertIn(OPENING_LEADS[trials[0].lead], letter_calls[0]['messages'][1]['content'])

        sections = format_report(results, 'test-model', check=True).split(f'\n{SEPARATOR}\n')
        self.assertEqual(len(sections), 3)
        for text in ['All letters: 2/2 accepted, 2 passed validation, 0 rejected by the checker', 'temperature 0.6: 2/2 accepted',
                     '--- System prompt (sent with every letter) ---', '--- Checker prompt ---',
                     'Shared phrasing between accepted letters: average',
                     'Detail order in accepted letters: 1 distinct orders among 2 letters',
                     'Opening words: 2 distinct first five words among 2 letters']:
            self.assertIn(text, sections[0])
        for text in ['accepted as gen-001', f'Tones: {trials[0].tones[0]} + {trials[0].tones[1]}', '"temperature": 0.6',
                     'Reasoning: 18 characters (checker: 0)', 'Checker: no problems', 'Write one letter.', 'Subject: Please help resolve',
                     f"Detail order asked: {', '.join(trials[0].beats)}", 'Detail order found: application, sponsors, stateless',
                     f'Opening lead: {trials[0].lead}; stance: {trials[0].stance}']:
            self.assertIn(text, sections[1])

    def test_checker_problems_reject_a_letter_that_passed_validation(self):
        def respond(_, params):
            return checker_says('a model citizen') if schema_of(params) == 'letter_check' else letter_reply('Hello.')
        results = quiet_run(FakeClient(respond), 'm', originals, plan_trials(1, 0, [0.6], seed=1), {})
        self.assertEqual(results[0].verdict, 'rejected by the checker')
        self.assertIn('Checker found:\n  - unsupported claim: a model citizen', format_report(results, 'm', check=True))

    def test_duplicates_and_missing_letters_are_reported_not_dropped(self):
        client = FakeClient(lambda call, _: letter_reply('Same opening.') if call < 3 else completion('not json'))
        results = quiet_run(client, 'm', originals, plan_trials(3, 0, [1.0], seed=1), {}, check=False)
        self.assertEqual(results[0].verdict, 'accepted as gen-001')
        self.assertEqual(results[1].verdict, 'rejected by validation')
        self.assertIn('duplicates an existing letter', results[1].validation_errors)
        self.assertEqual(results[2].verdict, 'no usable letter returned')
        self.assertIn('(none)', format_report(results, 'm', check=False))

    def test_suspect_phrases_are_listed_without_rejecting(self):
        client = FakeClient(lambda *_: letter_reply('He is a talented man who has lived safely.'))
        results = quiet_run(client, 'm', originals, plan_trials(1, 0, [0.6], seed=1), {}, check=False)
        self.assertTrue(results[0].accepted)
        self.assertEqual(results[0].suspects, ('talented', 'safely'))
        self.assertIn('Suspect phrases: talented, safely', format_report(results, 'm', check=False))

    def test_a_think_temperature_is_used_and_reported(self):
        def respond(call, params):
            if 'stop' in params:
                return completion(None, reasoning='A plan.')
            return letter_reply(f'Opening {call}.')
        client = FakeClient(respond)
        results = quiet_run(client, 'm', originals, plan_trials(1, 0, [0.7], seed=1), {}, check=False, think_temperature=0.95)
        self.assertEqual([c['extra_body']['temperature'] for c in client.calls], [0.95, 0.7])
        self.assertIn('reasoning sampled at temperature 0.95 in a separate request before each letter',
                      format_report(results, 'm', check=False, think_temperature=0.95))

    def test_report_warns_when_no_reasoning_comes_back(self):
        client = FakeClient(lambda *_: letter_reply('Hello.', reasoning=None))
        results = quiet_run(client, 'm', originals, plan_trials(1, 0, [0.6], seed=1), {}, check=False)
        self.assertIn('Warning: no reasoning came back', format_report(results, 'm', check=False))


if __name__ == '__main__':
    unittest.main()
