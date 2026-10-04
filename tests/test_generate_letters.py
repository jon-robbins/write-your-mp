import json
import unittest
import unittest.mock

from letter_fixtures import FakeClient, allow_similar_letters, checker_says, completion, good, library, schema_of
from generate_letters import generate, parse_args
from lettergen.library import LIBRARY

_similarity = allow_similar_letters()


def setUpModule():
    _similarity.start()


def tearDownModule():
    _similarity.stop()


def quiet_generate(*args, **kwargs):
    with unittest.mock.patch('sys.stderr'):
        return generate(*args, log=lambda _: None, **kwargs)


def batch_of(*openings):
    return completion(json.dumps({'letters': [good(opening) for opening in openings]}))


class GenerateTest(unittest.TestCase):
    def test_batches_until_the_target_is_met_skipping_declined_batches(self):
        client = FakeClient(lambda call, _: completion(None, refusal='declined') if call == 1 else
                            batch_of(f'Opening number {call}a.', f'Opening number {call}b.'))
        letters = quiet_generate(client, 'test-model', library, kind='general', target=3, batch_size=2)
        self.assertEqual([letter['id'] for letter in letters], ['gen-001', 'gen-002', 'gen-003'])
        self.assertTrue(all(call['model'] == 'test-model' for call in client.calls))
        self.assertEqual(client.calls[0]['response_format']['type'], 'json_schema')
        self.assertEqual([m['role'] for m in client.calls[0]['messages']], ['system', 'user'])

    def test_passes_extra_body_through_to_every_request(self):
        client = FakeClient(lambda call, _: batch_of(f'Opening {call}.'))
        extra = {'chat_template_kwargs': {'enable_thinking': False}, 'temperature': 0.7}
        quiet_generate(client, 'test-model', library, kind='general', target=2, batch_size=1, extra_body=extra)
        self.assertEqual([call['extra_body'] for call in client.calls], [extra, extra])

    def test_a_temperature_range_gives_each_batch_its_own_temperature(self):
        client = FakeClient(lambda call, _: batch_of(f'Opening {call}.'))
        quiet_generate(client, 'm', library, kind='general', target=3, batch_size=1, extra_body={'top_p': 0.95},
                       temperature_range=(0.68, 0.75))
        temperatures = [call['extra_body']['temperature'] for call in client.calls]
        self.assertTrue(all(0.68 <= t <= 0.75 for t in temperatures))
        self.assertTrue(all(call['extra_body']['top_p'] == 0.95 for call in client.calls))

    def test_a_think_temperature_makes_two_requests_per_batch(self):
        def respond(call, params):
            if 'stop' in params:
                return completion(None, reasoning=f'Plan {call}.')
            return batch_of(f'Opening {call}.')
        client = FakeClient(respond)
        quiet_generate(client, 'm', library, kind='general', target=2, batch_size=1, extra_body={'temperature': 0.7}, think_temperature=0.9)
        self.assertEqual([c['extra_body']['temperature'] for c in client.calls], [0.9, 0.7, 0.9, 0.7])
        self.assertEqual(sum('stop' in c for c in client.calls), 2)

    def test_concurrency_requests_a_wave_of_batches_at_once(self):
        client = FakeClient(lambda call, _: batch_of(f'Opening {call}a.', f'Opening {call}b.'))
        letters = quiet_generate(client, 'm', library, kind='general', target=4, batch_size=2, concurrency=2)
        self.assertEqual([letter['id'] for letter in letters], ['gen-001', 'gen-002', 'gen-003', 'gen-004'])
        self.assertEqual(len(client.calls), 2)

    def test_a_wave_still_rejects_copies_of_letters_from_an_earlier_batch_in_it(self):
        client = FakeClient(lambda *_: batch_of('The same opening.'))
        letters = quiet_generate(client, 'm', library, kind='general', target=2, batch_size=1, concurrency=2)
        self.assertEqual(len(letters), 1)

    def test_a_wave_drops_letters_the_checker_flags(self):
        def respond(call, params):
            if schema_of(params) == 'letter_check':
                return checker_says('acclaimed') if 'Flagged' in params['messages'][1]['content'] else checker_says()
            return batch_of('Flagged.' if call == 1 else f'Fine {call}.')
        letters = quiet_generate(FakeClient(respond), 'm', library, kind='general', target=2, batch_size=1, concurrency=2, check=True)
        self.assertEqual(len(letters), 2)
        self.assertFalse(any('Flagged.' in letter['body'] for letter in letters))

    def test_later_batches_are_told_which_wordings_are_already_common(self):
        client = FakeClient(lambda call, _: batch_of(f'Opening {call}.'))
        quiet_generate(client, 'm', library, kind='general', target=4, batch_size=1)
        prompts = [call['messages'][1]['content'] for call in client.calls]
        self.assertNotIn('already appear in many letters', prompts[0])
        self.assertIn('These wordings already appear in many letters', prompts[3])

    def test_stops_after_three_batches_in_a_row_produce_nothing_usable(self):
        client = FakeClient(lambda *_: completion(json.dumps({'letters': [{'subject': 's', 'body': 'no facts'}]})))
        self.assertEqual(quiet_generate(client, 'test-model', library, kind='general', target=5, batch_size=1), [])
        self.assertEqual(len(client.calls), 3)

    def test_with_check_keeps_only_letters_the_checker_passes(self):
        def respond(call, params):
            if schema_of(params) == 'letter_check':
                return checker_says('acclaimed') if 'Opening 1b.' in params['messages'][1]['content'] else checker_says()
            return batch_of(f'Opening {call}a.', f'Opening {call}b.')
        letters = quiet_generate(FakeClient(respond), 'm', library, kind='general', target=1, batch_size=2, check=True)
        self.assertEqual(len(letters), 1)
        self.assertIn('Opening 1a.', letters[0]['body'])


class ParseArgsTest(unittest.TestCase):
    def test_defaults_write_to_the_server_library_with_the_checker_on(self):
        args = parse_args(['--model', 'm'])
        self.assertEqual(args.out, LIBRARY)
        self.assertEqual(args.extra_body, {})
        self.assertIs(args.check, True)
        self.assertIs(parse_args(['--model', 'm', '--no-check']).check, False)

    def test_reads_extra_body_json_and_rejects_non_objects(self):
        self.assertEqual(parse_args(['--model', 'm', '--extra-body', '{"top_p": 0.8}']).extra_body, {'top_p': 0.8})
        for bad in ['[1]', '{bad']:
            with self.assertRaises(SystemExit), unittest.mock.patch('sys.stderr'):
                parse_args(['--model', 'm', '--extra-body', bad])

    def test_reads_a_temperature_range_and_rejects_one_that_runs_backwards(self):
        self.assertEqual(parse_args(['--model', 'm', '--temperature-range', '0.68', '0.75']).temperature_range, [0.68, 0.75])
        with self.assertRaises(SystemExit), unittest.mock.patch('sys.stderr'):
            parse_args(['--model', 'm', '--temperature-range', '0.8', '0.7'])

    def test_reads_concurrency_with_a_short_flag(self):
        self.assertEqual(parse_args(['--model', 'm']).concurrency, 1)
        self.assertEqual(parse_args(['--model', 'm', '-c', '4']).concurrency, 4)

    def test_reads_a_think_temperature_above_zero(self):
        self.assertIsNone(parse_args(['--model', 'm']).think_temperature)
        self.assertEqual(parse_args(['--model', 'm', '--think-temperature', '0.9']).think_temperature, 0.9)
        with self.assertRaises(SystemExit), unittest.mock.patch('sys.stderr'):
            parse_args(['--model', 'm', '--think-temperature', '0'])

    def test_requires_a_model(self):
        with self.assertRaises(SystemExit), unittest.mock.patch('sys.stderr'), unittest.mock.patch.dict('os.environ', {}, clear=True):
            parse_args([])


if __name__ == '__main__':
    unittest.main()
