"""Identity regressions and contextual machine shelves; no network or paid calls."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent/'natal-test-deps')]
from engine import machine_natal as MN, kosmogramma as K, chitatel as C
from engine.natal_facts import check

N = json.loads((ROOT/'tests/fixtures/natal_moscow_1981.json').read_text(encoding='utf-8'))['moscow']
POINTS = {name: K.точка(name, p['abs_degree'], p['retrograde']) for name, p in N['planets'].items()}
MACHINE = MN.build(POINTS, N['cusps'])


class NatalFactsTest(unittest.TestCase):
    def test_both_real_aspects_and_cross_references_are_preserved(self):
        text = ('## MC\nMC управляется Меркурием. Меркурий в оппозиции к Белой Луне, '
                'а MC в секстиле к Белой Луне. Это разные связи с разными задачами.')
        self.assertEqual(check(text, MACHINE), (text, []))

    def test_foreign_code_replaces_whole_claim_not_only_its_label(self):
        wrong = MACHINE['points']['Солнце']['code']['tag']
        text = f'Код MC — [{wrong}]. Последующий рассказ сохранён.'
        fixed, report = check(text, MACHINE)
        self.assertEqual(len(report), 1)
        self.assertTrue(report[0].startswith('MC:'))
        self.assertNotIn(wrong, fixed)
        self.assertIn(MACHINE['points']['MC']['code']['действие'], fixed)
        self.assertIn('Последующий рассказ сохранён.', fixed)
        self.assertEqual(check(fixed, MACHINE), (fixed, []))

    def test_code_of_named_ruler_is_not_reassigned_to_section(self):
        text = '## MC\nКод Меркурия — ['+MACHINE['points']['Меркурий']['code']['tag']+'].'
        self.assertEqual(check(text, MACHINE), (text, []))

    def test_ambiguous_code_is_never_guessed_from_last_name(self):
        text = 'Солнце и Юпитер связаны; код этой связи — ['+MACHINE['points']['MC']['code']['tag']+'].'
        self.assertEqual(check(text, MACHINE), (text, []))

    def test_wrong_aspect_removes_its_dependent_interpretation(self):
        text = 'Меркурий в секстиле к Белой Луне, поэтому здесь неизбежный успех.'
        fixed, report = check(text, MACHINE)
        self.assertEqual(len(report), 1)
        self.assertIn('Меркурий — Белая Луна: оппозиция', fixed)
        self.assertNotIn('неизбежный успех', fixed)
        self.assertEqual(check(fixed, MACHINE), (fixed, []))

    def test_absent_aspect_and_its_interpretation_are_removed(self):
        fixed, report = check('Уран в трине к Нептуну, что обещает успех. Другой рассказ.', MACHINE)
        self.assertEqual(len(report), 1)
        self.assertNotIn('обещает успех', fixed)
        self.assertIn('Другой рассказ.', fixed)

    def test_hypothetical_or_negated_aspect_is_not_changed(self):
        for text in ('Если Уран в трине к Нептуну, это лишь учебный пример.',
                     'Уран не образует трин с Нептуном.'):
            self.assertEqual(check(text, MACHINE), (text, []))

    def test_foreign_coordinate_is_corrected_only_for_explicit_owner(self):
        fixed, report = check('Солнце стоит в 15°00′ Рыб, поэтому это другой характер.', MACHINE)
        self.assertEqual(len(report), 1)
        self.assertIn(MACHINE['points']['Солнце']['position'], fixed)
        self.assertNotIn('другой характер', fixed)
        self.assertEqual(check(fixed, MACHINE), (fixed, []))

    def test_partner_coordinate_is_not_assigned_to_the_subject(self):
        text = ('Второе слияние связывает Меркурий с Плутоном в 25°08′ Весов '
                'во втором доме. Это отдельное положение Плутона.')
        self.assertEqual(check(text, MACHINE), (text, []))

    def test_later_aspect_partner_does_not_inherit_mc_coordinate_owner(self):
        text = ('Трин Меркурия в 29°14′ Весов к MC в 29°30′ Близнецов '
                'и его секстиль к Белой Луне в 29°03′ Овна.')
        self.assertEqual(check(text, MACHINE), (text, []))

    def test_packet_keeps_house_ruler_separate_from_dispositor(self):
        packet = json.loads(MN.reader_packet(MACHINE).split('\n', 1)[1])
        self.assertEqual(len(packet['points']), 17)
        self.assertEqual(len(packet['aspects']), 41)
        cards = {p['name']: p for p in packet['points']}
        for point in cards.values():
            self.assertTrue(point['house_ruler_position'])
            self.assertTrue(point['code']['суть'])
            self.assertIn('house_meaning', point)
        for row in packet['aspects']:
            self.assertEqual(row['endpoint_ids'], [cards[row['A']]['id'], cards[row['B']]['id']])
            self.assertEqual(row['degree_actions'][row['A']], cards[row['A']]['code']['действие'])
            self.assertEqual(row['degree_actions'][row['B']], cards[row['B']]['code']['действие'])

    def test_unknown_time_packet_never_inherits_houses_or_angles(self):
        packet = json.loads(MN.reader_packet(MN.build(POINTS, N['cusps'], known=False)).split('\n', 1)[1])
        self.assertFalse(packet['known_birth_time'])
        self.assertFalse(any(p['name'] in ('ASC', 'MC') for p in packet['points']))
        self.assertTrue(all('house' not in p and 'house_ruler' not in p for p in packet['points']))
        self.assertTrue(all('life_domains' not in a for a in packet['aspects']))

    def test_unknown_time_does_not_allow_invented_angle_or_house(self):
        unknown = MN.build(POINTS, N['cusps'], known=False)
        for text in ('ASC стоит в 12°00′ Девы.', 'Солнце находится в пятом доме.'):
            fixed, report = check(text, unknown)
            self.assertEqual(len(report), 1)
            self.assertNotIn('12°00′', fixed)
            self.assertNotIn('пятом доме', fixed)

    def test_explicit_house_is_bound_to_its_planet_not_the_section(self):
        actual = MACHINE['points']['Солнце']['house']
        good = f'## MC\nСолнце находится в {actual} доме.'
        self.assertEqual(check(good, MACHINE), (good, []))
        wrong = f'Солнце находится в {actual%12+1} доме, что даёт другую сферу.'
        fixed, report = check(wrong, MACHINE)
        self.assertEqual(len(report), 1)
        self.assertNotIn('другую сферу', fixed)
        self.assertEqual(check(fixed, MACHINE), (fixed, []))

    def test_facts_are_checked_after_last_grammar_correction(self):
        def correct(text, fn):
            return text.replace('оппозиции', 'секстиле'), 1
        from engine.passport_guard import AUDIT_RULE, REPAIR_RULE
        def ask(system, messages, **kwargs):
            if system == AUDIT_RULE:
                paragraphs = json.loads(messages[0]['content'])['paragraphs']
                return json.dumps({'paragraphs': [{'index': i, 'claims': [], 'issues': [
                    {'quote': 'Меркурий в секстиле к Белой Луне.', 'reason': 'Неверный аспект',
                     'basis': [r['id'] for r in MACHINE['aspects']
                               if {r['A'], r['B']} == {'Меркурий', 'Белая Луна'}]}]
                    if 'Меркурий в секстиле к Белой Луне.' in p else []}
                    for i, p in enumerate(paragraphs)]}, ensure_ascii=False)
            if system == REPAIR_RULE:
                return 'Меркурий — Белая Луна: оппозиция. Их взаимодействие требует осмысленного выбора.'
            return '## Связь\nМеркурий в оппозиции к Белой Луне.'
        with patch.object(C, '_спросить', side_effect=ask), \
             patch('engine.razvertka.откорректировать', side_effect=correct):
            result = C.прочитать('', точки=POINTS, куспиды=N['cusps'])
        self.assertIn('Меркурий — Белая Луна: оппозиция', result['tekst'])
        self.assertNotIn('в секстиле к Белой Луне', result['tekst'])
        self.assertEqual(result['machine_natal']['mode'], 'two_pass_narrative')
        self.assertTrue(result['storozh'])

    def test_saved_reading_is_reused_when_only_guard_format_failed(self):
        from engine.passport_guard import AUDIT_RULE, AuditResponseError
        checkpoint = {}
        generation = []
        broken = [True]
        def ask(system, messages, **kwargs):
            if system == AUDIT_RULE:
                if broken[0]:
                    return 'Не JSON'
                paragraphs = json.loads(messages[0]['content'])['paragraphs']
                return json.dumps({'paragraphs': [{'index': i, 'claims': [], 'issues': []}
                                                 for i in range(len(paragraphs))]})
            generation.append(system)
            return '## Прочтение\nСвязный смысловой рассказ.'
        with patch.object(C, '_спросить', side_effect=ask), \
             patch('engine.razvertka.откорректировать', side_effect=lambda text, fn: (text, 0)):
            with self.assertRaises(AuditResponseError):
                C.прочитать('', точки=POINTS, куспиды=N['cusps'], checkpoint=checkpoint)
            first_count = len(generation)
            self.assertTrue(checkpoint['drafts']['кармика'])
            broken[0] = False
            result = C.прочитать('', точки=POINTS, куспиды=N['cusps'], checkpoint=checkpoint)
        self.assertEqual(first_count, 2)  # hologram + first chapter, both saved
        self.assertEqual(len(generation), 5)  # remaining three chapters only
        self.assertIn('Связный смысловой рассказ.', result['tekst'])


if __name__ == '__main__':
    unittest.main()
