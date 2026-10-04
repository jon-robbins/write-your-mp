import json
import unittest
import unittest.mock
from types import SimpleNamespace

from letter_fixtures import FakeClient, checker_says, completion, good, original, schema_of
from lettergen.model import check_letter, parse_letters, request_letters, screen


class ParseLettersTest(unittest.TestCase):
    def test_accepts_fenced_json_and_drops_malformed_entries(self):
        content = '```json\n{"letters": [{"subject": "s", "body": "b"}, {"subject": 1}]}\n```'
        self.assertEqual(parse_letters(content), [{'subject': 's', 'body': 'b'}])

    def test_ignores_a_leading_think_block(self):
        content = '<think>Let me check the rules first.</think>\n{"letters": [{"subject": "s", "body": "b"}]}'
        self.assertEqual(parse_letters(content), [{'subject': 's', 'body': 'b'}])

    def test_returns_none_for_unparsable_content(self):
        self.assertIsNone(parse_letters('not json'))
        self.assertIsNone(parse_letters(None))
        self.assertIsNone(parse_letters('{"other": []}'))


class UsageTest(unittest.TestCase):
    def test_replies_carry_the_token_counts_the_server_reports(self):
        reply_with_usage = completion(json.dumps({'letters': [good('Hello.')]}))
        reply_with_usage.usage = SimpleNamespace(prompt_tokens=950, completion_tokens=7200)
        reply = request_letters(FakeClient(lambda *_: reply_with_usage), 'm', 'prompt')
        self.assertEqual((reply.prompt_tokens, reply.completion_tokens), (950, 7200))
        bare = request_letters(FakeClient(lambda *_: completion(json.dumps({'letters': [good('Hello.')]}))), 'm', 'prompt')
        self.assertEqual((bare.prompt_tokens, bare.completion_tokens), (None, None))


def with_usage(response, prompt, completion_tokens):
    response.usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion_tokens)
    return response


class TwoPassTest(unittest.TestCase):
    def test_reasoning_is_sampled_hot_then_the_letter_continues_from_it_at_its_own_temperature(self):
        def respond(call, _):
            if call == 1:
                return with_usage(completion(None, reasoning='Plan: open with the ask, then the application.'), 900, 6000)
            return with_usage(completion(json.dumps({'letters': [good('Hello.')]})), 7000, 400)
        client = FakeClient(respond)
        reply = request_letters(client, 'm', 'the user prompt', {'top_p': 0.95, 'temperature': 0.7}, think_temperature=0.9)

        think, answer = client.calls
        self.assertEqual(think['stop'], ['</think>'])
        self.assertEqual(think['extra_body'], {'top_p': 0.95, 'temperature': 0.9})
        self.assertNotIn('response_format', think)
        self.assertEqual(answer['messages'][-1], {'role': 'assistant', 'content': '<think>\nPlan: open with the ask, then the application.\n</think>\n\n'})
        self.assertEqual(answer['extra_body'], {'top_p': 0.95, 'temperature': 0.7, 'continue_final_message': True,
                                                'add_generation_prompt': False})
        self.assertEqual(schema_of(answer), 'letter_batch')
        self.assertIn('Hello.', reply.value[0]['body'])
        self.assertEqual(reply.reasoning, 'Plan: open with the ask, then the application.')
        self.assertEqual((reply.prompt_tokens, reply.completion_tokens), (900, 6400))

    def test_falls_back_to_one_request_when_no_reasoning_comes_back(self):
        client = FakeClient(lambda call, _: completion('') if call == 1 else completion(json.dumps({'letters': [good('Hello.')]})))
        with unittest.mock.patch('sys.stderr'):
            reply = request_letters(client, 'm', 'prompt', {'temperature': 0.7}, think_temperature=0.9)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1]['extra_body'], {'temperature': 0.7})
        self.assertEqual(len(client.calls[1]['messages']), 2)
        self.assertIn('Hello.', reply.value[0]['body'])

    def test_reads_the_letters_when_the_server_files_them_as_reasoning(self):
        def respond(call, _):
            if call == 1:
                return completion(None, reasoning='A plan.')
            return completion(None, reasoning=json.dumps({'letters': [good('Hello.')]}))
        reply = request_letters(FakeClient(respond), 'm', 'prompt', {}, think_temperature=0.9)
        self.assertIn('Hello.', reply.value[0]['body'])


class CheckerTest(unittest.TestCase):
    def test_check_letter_sends_original_and_draft_and_returns_problems_with_reasoning(self):
        client = FakeClient(lambda *_: checker_says('a model citizen', ' ', missing=['March 2026'], opening='Lisbon first',
                                                    action='asks twice', reasoning='thinking'))
        reply = check_letter(client, 'm', original, good('Hello.'), {'top_p': 0.95})
        self.assertEqual(reply.value, ['unsupported claim: a model citizen', 'missing background: March 2026',
                                       'opening: Lisbon first', 'call to action: asks twice'])
        self.assertEqual(reply.reasoning, 'thinking')
        user = client.calls[0]['messages'][1]['content']
        self.assertIn(original['body'], user)
        self.assertIn('Hello.', user)
        self.assertEqual(schema_of(client.calls[0]), 'letter_check')
        self.assertEqual(client.calls[0]['extra_body'], {'top_p': 0.95})

    def test_screen_rejects_letters_with_problems_or_no_checker_answer(self):
        replies = {'Clean.': checker_says(), 'Embellished.': checker_says('acclaimed'), 'Thin.': checker_says(missing=['Lisbon']),
                   'Pushy.': checker_says(action='asks in two places'), 'Garbled.': completion('not json')}
        client = FakeClient(lambda _, params: replies[next(k for k in replies if k in params['messages'][1]['content'])])
        with unittest.mock.patch('sys.stderr'):
            passed, failed = screen(client, 'm', original, [good(k) for k in replies], workers=1)
        self.assertEqual(len(passed), 1)
        self.assertIn('Clean.', passed[0]['body'])
        self.assertEqual([f['errors'] for f in failed],
                         [['unsupported claim: acclaimed'], ['missing background: Lisbon'], ['call to action: asks in two places'],
                          ['the checker gave no usable answer']])


if __name__ == '__main__':
    unittest.main()
