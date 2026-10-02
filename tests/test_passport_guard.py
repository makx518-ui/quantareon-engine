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
            self.assertEqual(payload['machine_basis'], document['facts'])
            return 'Верный смысл сохранён.'
        result, _ = guard('Верный смысл. Ошибка.', document, ask)
        self.assertEqual(result, 'Верный смысл сохранён.')

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
