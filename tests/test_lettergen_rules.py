import unittest

from letter_fixtures import counter, good, original, sig
from lettergen.rules import CLOSING_WORDS, accept_variants, ends_with_call_to_action, opens_with_summary, overused_phrases, shared_phrases


class AcceptVariantsTest(unittest.TestCase):
    def test_keeps_valid_letters_and_rejects_missing_facts_and_duplicates(self):
        missing = good('Another start.')
        missing = {**missing, 'body': missing['body'].replace('Northbridge Newcomer Alliance', 'a nonprofit')}
        accepted, rejected = accept_variants(
            [good('I am writing today.'), good('I am writing today.'), missing],
            kind='general', existing=[original], next_id=counter('gen'), max_overlap=1.0,
        )
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]['status'], 'approved')
        self.assertIs(accepted[0]['generated'], True)
        self.assertEqual(len(rejected), 2)
        self.assertTrue(any('duplicate' in e for r in rejected for e in r['errors']))
        self.assertTrue(any('Northbridge Newcomer Alliance' in e for r in rejected for e in r['errors']))

    def test_rejects_letters_whose_last_paragraph_is_not_the_call_to_action(self):
        base = good('I am writing today.')
        moved = {**base, 'body': base['body'].replace('\n\nSincerely,', '\n\n' + ' '.join(['commentary'] * CLOSING_WORDS) + '\n\nSincerely,')}
        accepted, rejected = accept_variants([moved], kind='general', existing=[], next_id=counter('gen'))
        self.assertEqual(accepted, [])
        self.assertIn('does not end with the call to action', rejected[0]['errors'])

    def test_rejects_letters_that_share_too_much_phrasing_with_a_kept_one(self):
        base = good('I am writing today.')
        near = {**base, 'body': base['body'].replace('I ask for your help', 'I am asking for your help')}
        fresh = {**base, 'body': 'Dear {mpName},\n\nEntirely different wording about the same case from a constituent of {riding}, covering each required point in fresh sentences.\n\nPlease write to the Minister of Immigration for me.\n\nSincerely,\n\n' + sig}
        accepted, rejected = accept_variants([base, near, fresh], kind='general', existing=[], next_id=counter('gen'), max_overlap=0.3)
        self.assertEqual([letter['id'] for letter in accepted], ['gen-1'])
        self.assertTrue(any(e.startswith('too similar to gen-1') for e in rejected[0]['errors']))
        self.assertFalse(any(e.startswith('too similar') for e in rejected[1]['errors']))

    def test_home_variants_are_tagged_with_the_home_riding(self):
        accepted, _ = accept_variants([good('His sponsors are in your riding.')], kind='home', existing=[], next_id=counter('gen-home'))
        self.assertEqual(accepted[0]['ridings'], ['Ottawa Centre'])
        self.assertEqual(accepted[0]['id'], 'gen-home-1')


class OpeningTest(unittest.TestCase):
    def test_the_first_paragraph_names_the_riding_teo_and_his_application(self):
        self.assertTrue(opens_with_summary(good('Hello.')))
        late = good('Hello.')
        late = {**late, 'body': late['body'].replace('Dear {mpName},\n\n', 'Dear {mpName},\n\nHe lives in Lisbon.\n\n')}
        self.assertFalse(opens_with_summary(late))
        accepted, rejected = accept_variants([late], kind='general', existing=[], next_id=counter('gen'))
        self.assertEqual(accepted, [])
        self.assertIn('does not open with the summary (riding, Teo and his application)', rejected[0]['errors'])

    def test_a_greeting_without_dear_is_not_taken_for_the_opening(self):
        bare = good('Hello.')
        bare = {**bare, 'body': bare['body'].replace('Dear {mpName},', '{mpName}')}
        self.assertTrue(opens_with_summary(bare))


def letters_saying(*texts):
    return [{'body': f'Dear {{mpName}},\n\n{text}\n\nSincerely,\n\n{sig}'} for text in texts]


class SharedPhrasesTest(unittest.TestCase):
    def test_counts_wordings_letters_share_but_not_exact_names(self):
        letters = letters_saying('I am a constituent of the riding, worried about Teo Castell and Northbridge Newcomer Alliance.',
                                 'I am a constituent of the riding and Teo Castell needs Northbridge Newcomer Alliance heard.',
                                 'Another letter entirely.')
        picked = shared_phrases(letters)
        self.assertIn('constituent of the', picked[0][0])
        self.assertEqual(picked[0][1], 2)
        self.assertFalse(any('castell' in text or 'northbridge' in text for text, _ in picked))

    def test_overused_means_in_at_least_three_letters_and_thirty_percent(self):
        stock = 'We must stand by stateless people in every way we can.'
        own = ['Red kites circle over quiet valleys.', 'Bread rises slowly on cold mornings.', 'Trains hum through distant tunnels.',
               'Gardens wake after long rain.', 'Candles flicker in quiet windows.', 'Owls call across frozen fields.',
               'Rivers carve patient stone canyons.', 'Kettles sing in crowded kitchens.']
        self.assertEqual(overused_phrases(letters_saying(stock, stock)), [])
        three_of_ten = overused_phrases(letters_saying(*([stock] * 3), *own[:7]))
        self.assertTrue(three_of_ten and all('stateless' in text or 'every way we' in text for text in three_of_ten))
        self.assertEqual(overused_phrases(letters_saying(*([stock] * 2), *own)), [])


class CallToActionTest(unittest.TestCase):
    def test_the_last_paragraph_must_ask_for_contact_with_ircc_or_the_minister(self):
        self.assertTrue(ends_with_call_to_action(good('Hello.')))
        thanked = good('Hello.')
        thanked = {**thanked, 'body': thanked['body'].replace('\n\nSincerely,', '\n\nThank you for your time and service.\n\nSincerely,')}
        self.assertTrue(ends_with_call_to_action(thanked))
        passionate = {**thanked, 'body': thanked['body'].replace('Thank you for your time and service.', 'Canada can do better.\n\nThank you.')}
        self.assertTrue(ends_with_call_to_action(passionate))
        buried = {**thanked, 'body': thanked['body'].replace('Thank you for your time and service.', ' '.join(['commentary'] * CLOSING_WORDS))}
        self.assertFalse(ends_with_call_to_action(buried))


if __name__ == '__main__':
    unittest.main()
