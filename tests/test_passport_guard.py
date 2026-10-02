"""Offline adversarial contract and paragraph repair tests, not live model evals."""
import json
import unittest
from engine.passport_guard import guard, validate, passport, AUDIT_RULE


class PassportGuardTest(unittest.TestCase):
    def setUp(self):
        self.document = {'facts': {'p:Нептун:house': '3'}}

    def report(self, text, issues=None):
        return json.dumps({'paragraphs': [{'index': i, 'claims': [], 'issues': issues or []}
                                         for i, _ in enumerate(text)]}, ensure_ascii=False)

    def test_missing_paragraph_blocks(self):
        with self.assertRaises(ValueError):
            validate(self.report(['a']), ['a', 'b'], self.document['facts'])

    def test_wrong_provenance_blocks(self):
        for evidence in ([{'id': 'foreign', 'value': '3'}],
                         [{'id': 'p:Нептун:house', 'value': '4'}], []):
            raw = json.dumps({'paragraphs': [{'index': 0, 'claims': [
                {'quote': 'Нептун', 'evidence': evidence}], 'issues': []}]})
            with self.assertRaises(ValueError):
                validate(raw, ['Нептун'], self.document['facts'])

    def test_transport_and_invalid_json_block(self):
        for raw in ('не JSON', '{"paragraphs":[],"paragraphs":[]}'):
            with self.assertRaises(ValueError):
                guard('Текст', self.document, lambda *_: raw)

    def test_exact_evidence_accepted(self):
        raw = json.dumps({'paragraphs': [{'index': 0, 'claims': [{
            'quote': 'Нептун в третьем доме', 'evidence': [
                {'id': 'p:Нептун:house', 'value': '3'}]}], 'issues': []}]})
        self.assertEqual(len(validate(raw, ['Нептун в третьем доме'], self.document['facts'])), 1)

    def test_actual_failure_fragments_rewrite_only_rejected_paragraph(self):
        for bad in ('Нептун прямо на куспиде.', 'Точное слияние Меркурия с Хироном.',
                    'Ведущий фиксированный крест.'):
            calls = []
            def ask(system, messages):
                payload = json.loads(messages[0]['content'])
                calls.append(payload)
                if system == AUDIT_RULE:
                    paragraphs = payload['paragraphs']
                    rows = []
                    for i, p in enumerate(paragraphs):
                        issues = ([{'quote': bad, 'reason': 'Нет машинного основания',
                                    'basis': ['p:Нептун:house']}] if p == bad else [])
                        rows.append({'index': i, 'claims': [], 'issues': issues})
                    return json.dumps({'paragraphs': rows}, ensure_ascii=False)
                self.assertEqual(payload['paragraph'], bad)
                self.assertEqual(payload['machine_basis'], self.document['facts'])
                return 'Чуткость помогает понимать подтекст общения.'
            text, repairs = guard('Сохранённый абзац.\n\n'+bad, self.document, ask)
            self.assertTrue(text.startswith('Сохранённый абзац.\n\n'))
            self.assertNotIn(bad, text)
            self.assertEqual(len(repairs), 1)
            self.assertEqual(len(calls), 3)

    def test_unresolved_error_blocks(self):
        def ask(system, messages):
            payload = json.loads(messages[0]['content'])
            if system != AUDIT_RULE:
                return 'Ошибка.'
            return self.report(payload['paragraphs'], [
                {'quote': 'Ошибка.', 'reason': 'Нет основания', 'basis': []}])
        with self.assertRaises(ValueError):
            guard('Ошибка.', self.document, ask)

    def test_deterministic_error_cannot_be_overridden_by_auditor(self):
        def ask(system, messages):
            if system == AUDIT_RULE:
                return self.report(json.loads(messages[0]['content'])['paragraphs'])
            return 'Исправленный смысл.'
        def detect(paragraph):
            return ([{'quote': paragraph, 'reason': 'Машинное противоречие',
                      'basis': ['p:Нептун:house']}] if paragraph == 'Ошибка.' else [])
        result, changes = guard('Ошибка.', self.document, ask, detect=detect)
        self.assertEqual(result, 'Исправленный смысл.')
        self.assertTrue(changes)

    def test_repair_preserves_basis_of_correct_claim_in_same_paragraph(self):
        document = {'facts': {'good': '3', 'replacement': 'false'}}
        def ask(system, messages):
            payload = json.loads(messages[0]['content'])
            if system == AUDIT_RULE:
                text = payload['paragraphs'][0]
                return json.dumps({'paragraphs': [{'index': 0, 'claims': [
                    {'quote': 'Верный смысл', 'evidence': [{'id': 'good', 'value': '3'}]}],
                    'issues': [{'quote': 'Ошибка', 'reason': 'Противоречие', 'basis': ['replacement']}]
                    if 'Ошибка' in text else []}]}, ensure_ascii=False)
            self.assertEqual(payload['fragment'], 'Ошибка')
            self.assertEqual(payload['machine_basis'], {'replacement': 'false'})
            return 'Исправленная мысль'
        result, _ = guard('Верный смысл. Ошибка.', document, ask)
        self.assertEqual(result, 'Верный смысл. Исправленная мысль.')

    def test_repeated_error_quote_blocks_ambiguous_replacement(self):
        raw = self.report(['Ошибка. Ошибка.'], [
            {'quote': 'Ошибка.', 'reason': 'Ошибка', 'basis': []}])
        with self.assertRaisesRegex(ValueError, 'Неоднозначный'):
            validate(raw, ['Ошибка. Ошибка.'], self.document['facts'])

    def test_aspect_repair_receives_own_meanings_of_both_endpoints(self):
        row = {'A': 'Солнце', 'B': 'Луна', 'kind': 'квадрат'}
        facts = {'a:pair': json.dumps(row), 'p:Солнце:code': 'смысл Солнца',
                 'p:Луна:code': 'смысл Луны'}
        def ask(system, messages):
            payload = json.loads(messages[0]['content'])
            if system == AUDIT_RULE:
                return self.report(payload['paragraphs'], [
                    {'quote': 'Ошибка.', 'reason': 'Неверная связь', 'basis': ['a:pair']}]
                    if 'Ошибка.' in payload['paragraphs'][0] else [])
            self.assertEqual(payload['machine_basis'], facts)
            return 'Исправленный смысл.'
        result, _ = guard('Ошибка. Соседняя мысль.', {'facts': facts}, ask)
        self.assertEqual(result, 'Исправленный смысл. Соседняя мысль.')

    def test_two_local_edits_preserve_all_surrounding_text(self):
        def ask(system, messages):
            payload = json.loads(messages[0]['content'])
            if system == AUDIT_RULE:
                text = payload['paragraphs'][0]
                issues = [{'quote': quote, 'reason': 'Ошибка', 'basis': ['p:Нептун:house']}
                          for quote in ('Ошибка А', 'Ошибка Б') if quote in text]
                return self.report([text], issues)
            return {'Ошибка А': 'Новая мысль А', 'Ошибка Б': 'Новая мысль Б'}[payload['fragment']]
        original = 'Живая мысль. Ошибка А. Связующий образ. Ошибка Б. Смысловой итог.'
        result, changes = guard(original, self.document, ask)
        self.assertEqual(result, original.replace('Ошибка А', 'Новая мысль А').replace('Ошибка Б', 'Новая мысль Б'))
        self.assertEqual(len(changes), 2)

    def test_initial_coordinates_and_previous_reading_are_sent_to_guard(self):
        for initial in (True, False):
            def ask(system, messages):
                payload = json.loads(messages[0]['content'])
                self.assertEqual(payload['initial_coordinates'], initial)
                self.assertEqual(payload['previous_text'], 'Ранее представленная точка.')
                return self.report(payload['paragraphs'])
            text, _ = guard('Содержательная трактовка.', self.document, ask,
                            initial_coordinates=initial, previous_text='Ранее представленная точка.')
            self.assertEqual(text, 'Содержательная трактовка.')

    def test_passport_does_not_recalculate_or_keep_bridge(self):
        machine = {'points': {'Нептун': {'id': 'p:Нептун', 'house': 3}},
                   'aspects': [], 'bridge': object()}
        result = passport(machine, {'balance': 'равенство'})
        self.assertEqual(result['facts']['p:Нептун:house'], '3')
        self.assertEqual(result['facts']['machine:balance:0'], 'равенство')
        json.dumps(result)

    def test_balance_tie_is_not_a_single_leader(self):
        from types import SimpleNamespace
        from engine import klassika_natal as KN
        names = KN.ПЛАНЕТЫ + ['ASC', 'MC']
        machine = SimpleNamespace(flat=dict(zip(names, range(0, 360, 30))))
        text = KN.баланс(machine)
        self.assertIn('ведущий крест: единственного ведущего нет', text)
        self.assertIn('ведущая стихия: единственного ведущего нет', text)


if __name__ == '__main__':
    unittest.main()
