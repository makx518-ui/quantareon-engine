"""Real natal regressions: ownership, coverage, hostile editor and export parity."""
import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'natal-test-deps')]
from engine import machine_natal as MN, kosmogramma as K, chitatel as C
from engine import natal_export as E, karta_html
from engine.af import kod360

N = json.loads((ROOT/'tests/fixtures/natal_moscow_1981.json').read_text(encoding='utf-8'))['moscow']
POINTS = {n: K.точка(n, p['abs_degree'], p['retrograde']) for n, p in N['planets'].items()}
CUSPS = N['cusps']


def editor(system, messages, **kwargs):
    packet = json.loads(messages[0]['content'])
    return json.dumps({'order': {k: list(reversed(v)) for k, v in packet['groups'].items()},
                       'style': 'connected'}, ensure_ascii=False)


class MachineNatalTest(unittest.TestCase):
    def test_real_chart_complete_and_codes_owned_by_exact_point(self):
        machine = MN.build(POINTS, CUSPS)
        self.assertEqual(len(machine['points']), 17)
        self.assertEqual(len(machine['aspects']), 41)
        for name, p in machine['points'].items():
            with self.subTest(name=name):
                self.assertEqual(p['code']['tag'], kod360.code_by_abs(p['longitude'])['tag'])
                self.assertIn(f"[{p['code']['tag']}]", p['text'])
                self.assertEqual(p['ruler'], {'MC': 'Меркурий', 'Меркурий': 'Венера'}.get(name, p['ruler']))
        result = MN.read(POINTS, CUSPS, ask=editor)
        self.assertEqual(result['machine_natal']['mode'], 'ai_order')
        for row in machine['aspects']:
            self.assertEqual(result['tekst'].count(row['text']), 1)
            for owner in (row['A'], row['B']):
                self.assertIn(machine['points'][owner]['code']['tag'], row['text'])

    def test_real_mercury_opposition_is_never_reassigned_to_mc(self):
        rows = MN.build(POINTS, CUSPS)['aspects']
        mercury = next(r for r in rows if {r['A'], r['B']} == {'Меркурий', 'Белая Луна'})
        mc = next(r for r in rows if {r['A'], r['B']} == {'MC', 'Белая Луна'})
        self.assertEqual(mercury['kind'], 'оппозиция')
        self.assertEqual(mc['kind'], 'секстиль')
        self.assertTrue(mercury['direct'])
        self.assertTrue(mc['direct'])

    def test_input_and_reading_are_not_mutated(self):
        before = copy.deepcopy(POINTS)
        MN.read(POINTS, CUSPS, ask=editor)
        self.assertEqual(POINTS, before)
        self.assertEqual(len(CUSPS), 12)

    def test_missing_or_nonfinite_planet_fails_before_editor(self):
        for bad in (None, {}, {n: p for n, p in POINTS.items() if n != 'Луна'}):
            with self.subTest(bad=type(bad).__name__), patch.object(C, '_спросить') as ask:
                with self.assertRaises(ValueError):
                    C.прочитать('', точки=bad, куспиды=CUSPS)
                ask.assert_not_called()
        for value in (float('nan'), float('inf'), True, '16.2'):
            bad = copy.deepcopy(POINTS)
            bad['Солнце']['градус'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                MN.build(bad, CUSPS)

    def test_bad_cusps_are_not_silently_used(self):
        for cusps in ([], CUSPS[:10], [0]*12, CUSPS[::-1], [float('nan')]*12):
            with self.subTest(cusps=cusps[:2]), self.assertRaises(ValueError):
                MN.build(POINTS, cusps)

    def test_unknown_time_does_not_inherit_supplied_angles_or_houses(self):
        with patch.object(C, '_спросить', side_effect=editor):
            result = C.прочитать('', заказ='kosmogramma', точки=POINTS, куспиды=CUSPS,
                                углы={'ASC': 42, 'MC': 55})
        self.assertEqual(result['machine_natal']['points'], 15)
        self.assertEqual(result['machine_natal']['houses'], 0)
        self.assertNotIn('p:ASC', result['machine_natal']['rendered_ids'])
        self.assertNotIn('p:MC', result['machine_natal']['rendered_ids'])
        self.assertNotIn('дом 1', result['tekst'])
        for r in MN.aspect_records(POINTS, CUSPS, known=False):
            self.assertFalse({'ASC', 'MC'} & {r['A'], r['B']})

    def test_editor_inventions_never_enter_delivered_text(self):
        groups = MN.build(POINTS, CUSPS)['groups']
        valid = {'order': copy.deepcopy(groups), 'style': 'connected'}
        variants = []
        extra = copy.deepcopy(valid); extra['text'] = 'Уран—Нептун: трин 120°, жизнь гарантированно успешна'
        variants.append(json.dumps(extra, ensure_ascii=False))
        missing = copy.deepcopy(valid); missing['order']['aspects'].pop(); variants.append(json.dumps(missing))
        duplicate = copy.deepcopy(valid); duplicate['order']['aspects'][0] = duplicate['order']['aspects'][1]
        variants.append(json.dumps(duplicate))
        foreign = copy.deepcopy(valid); foreign['order']['aspects'][0] = 'a:Уран|Нептун:трин'
        variants.append(json.dumps(foreign, ensure_ascii=False))
        moved = copy.deepcopy(valid); moved['order']['tools'][0], moved['order']['foundation'][0] = \
            moved['order']['foundation'][0], moved['order']['tools'][0]
        variants.append(json.dumps(moved))
        variants += ['## Чужой текст\nСолнце в Овне', '', 'null', '[]', 'x'*24001,
                     '{"order":{},"order":{},"style":"connected"}',
                     json.dumps({'order': groups, 'style': ['connected']})]
        baseline = MN.read(POINTS, CUSPS)
        for raw in variants:
            with self.subTest(raw=raw[:70]):
                result = MN.read(POINTS, CUSPS, ask=lambda *a, **k: raw)
                self.assertEqual(result['tekst'], baseline['tekst'])
                self.assertEqual(result['machine_natal']['rendered_ids'], baseline['machine_natal']['rendered_ids'])
                self.assertEqual(result['storozh'], [])

    def test_json_fence_is_only_a_wrapper_and_cannot_carry_prose(self):
        groups = MN.build(POINTS, CUSPS)['groups']
        valid = json.dumps({'order': groups, 'style': 'connected'}, ensure_ascii=False)
        self.assertEqual(MN.validate_plan('```json\n'+valid+'\n```', groups)['order'], groups)
        with self.assertRaises(ValueError):
            MN.validate_plan('Солнце в Овне.\n```json\n'+valid+'\n```', groups)

    def test_unavailable_editor_still_produces_all_cards(self):
        for exc in (TimeoutError('secret-provider-token'), RuntimeError('broken upstream')):
            with self.subTest(exc=type(exc).__name__):
                def unavailable(*a, **k):
                    raise exc
                result = MN.read(POINTS, CUSPS, ask=unavailable)
                self.assertEqual(result['machine_natal']['aspects'], 41)
                self.assertEqual(result['machine_natal']['fallback_reason'], type(exc).__name__)
                self.assertNotIn(str(exc), result['tekst'])

    def test_optional_editor_has_one_bounded_attempt_without_retry_sleep(self):
        with patch.object(C, '_спросить_раз', side_effect=TimeoutError('offline')) as ask, \
             patch('time.sleep', side_effect=AssertionError('retry should not sleep')):
            result = C.прочитать('', точки=POINTS, куспиды=CUSPS)
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(ask.call_args.kwargs['timeout'], 45)
        self.assertEqual(result['machine_natal']['aspects'], 41)

    def test_natal_never_runs_prose_guard_or_free_ai_corrector(self):
        with patch.object(C, '_спросить', side_effect=editor) as ask, \
             patch('engine.storozh_faktov.сторожить', side_effect=AssertionError('old guard called')), \
             patch('engine.razvertka.откорректировать', side_effect=AssertionError('free prose called')):
            result = C.прочитать('', точки=POINTS, куспиды=CUSPS)
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(result['storozh'], [])
        self.assertEqual(result['razbor'], result['tekst'])

    def test_linked_aspects_are_explicit_not_exact_or_direct(self):
        points = copy.deepcopy(POINTS)
        # Uranus square Saturn (4°) extends to Mars via their conjunction (2°).
        # Uranus—Mars alone is outside the adopted 5° direct orb (6°).
        for name, degree in [('Марс', 0), ('Сатурн', 2), ('Уран', 96)]:
            points[name]['градус'] = degree
        linked = [r for r in MN.build(points, CUSPS)['aspects'] if not r['direct']]
        self.assertTrue(linked)
        self.assertTrue(any({r['A'], r['B']} == {'Марс', 'Уран'} for r in linked))
        for r in linked:
            self.assertFalse(r['exact'])
            self.assertIn('не прямой аспект', r['text'])
            self.assertIn(r['note'], r['text'])
            self.assertIsNone(r['limit'])

    def test_chart_uses_same_adopted_aspects_including_angles(self):
        machine = MN.build(POINTS, CUSPS)
        rows = MN.chart_aspects(POINTS, CUSPS)
        self.assertEqual(len(rows), len(machine['aspects']))
        for row, expected in zip(rows, machine['aspects']):
            self.assertEqual({row['а'], row['б']}, {expected['A'], expected['B']})
            self.assertEqual(row['аспект'], expected['kind'])
            self.assertEqual(row['прямой'], expected['direct'])
        svg = E.render_chart({'tochki': POINTS, 'kuspidy': CUSPS, 'vremya_izvestno': True, 'aspekty': rows}, {})
        self.assertEqual(svg.count('opacity=".65"'), sum(r['direct'] for r in machine['aspects']))
        self.assertTrue(any('MC' in {r['а'], r['б']} and r['прямой'] for r in rows))

    def test_speeds_determine_application_not_planet_name_or_retro_flag(self):
        p = {'Солнце': {'градус': 0, 'скорость': 1}, 'Луна': {'градус': 119, 'скорость': 13}}
        self.assertEqual(MN._motion('Солнце', 'Луна', 'трин', p), 'сходящийся')
        p['Луна']['градус'] = 121
        self.assertEqual(MN._motion('Солнце', 'Луна', 'трин', p), 'расходящийся')
        p['Луна']['градус'] = 359
        self.assertEqual(MN._motion('Солнце', 'Луна', 'соединение', p), 'сходящийся')
        self.assertIn('нет скоростей', MN._motion('ASC', 'Луна', 'трин', p))

    def test_html_export_contains_machine_cards_and_escapes_birth_input(self):
        result = MN.read(POINTS, CUSPS, birth={'место': '<script>alert(1)</script>'}, name='Александр')
        snapshot = {'tochki': POINTS, 'kuspidy': CUSPS, 'vremya_izvestno': True,
                    'aspekty': MN.chart_aspects(POINTS, CUSPS)}
        html = karta_html.карта_клиенту(result['razdely'], 'Александр', расчёт_карты=snapshot)
        self.assertIn('<svg', html)
        self.assertIn('Аспектный каркас', html)
        self.assertIn('Двенадцать областей', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('Меркурий — Белая Луна: оппозиция', html)

    def test_paid_builder_uses_machine_reader_and_same_export_snapshot(self):
        import importlib
        from datetime import datetime
        from engine import arhiv
        with patch.object(threading.Thread, 'start'):
            kl = importlib.import_module('api.klassika_api')
        import api_vhod
        snapshot = {'tochki': POINTS, 'kuspidy': CUSPS, 'vremya_izvestno': True,
                    'rozhdenie': datetime.fromisoformat('1981-11-09T00:15:00+00:00')}
        card = {'tarif': 'klassika_natal', 'имя': 'Александр',
                'dannye': {'тип': 'натал', 'дата': '09.11.1981', 'время': '03:15',
                           'место': 'Россия, Москва', '_shirota': 55.75204, '_dolgota': 37.61781, '_gmt': 3}}
        with patch.object(api_vhod, 'расчёт', return_value=snapshot), \
             patch.object(arhiv, 'положить_карту', return_value='preview/natal.html'), \
             patch.object(C, '_спросить', side_effect=editor), \
             patch('engine.storozh_faktov.сторожить', side_effect=AssertionError('old guard called')):
            html, filename = kl._построить_натал_или_соляр(card, lambda *a: None)
        self.assertIn('<svg', html)
        self.assertEqual(html.count('opacity=".65"'), 41)
        self.assertIn('Александр', filename)
        self.assertEqual(card['storozh'], [])
        self.assertEqual(card['machine_natal']['aspects'], 41)
        self.assertEqual(card['arhiv'], 'preview/natal.html')

    def test_full_library_rules_are_available_to_editor_without_mutable_output(self):
        def inspect(system, messages, **kwargs):
            packet = json.loads(messages[0]['content'])
            self.assertEqual(len(packet['aspects']), 41)
            for p in packet['cards']:
                self.assertTrue(p['code']['суть'])
                self.assertTrue(p['code']['действие'])
                self.assertIn(p['position'], p['text'])
            for r in packet['aspects']:
                self.assertIn('Синтез градусов', r['text'])
            return json.dumps({'order': packet['groups'], 'style': 'reference'}, ensure_ascii=False)
        result = MN.read(POINTS, CUSPS, ask=inspect)
        self.assertEqual(result['machine_natal']['mode'], 'ai_order')

    def test_lunar_day_is_never_claimed_with_unknown_time(self):
        known = MN.read(POINTS, CUSPS, lunar_day=13)
        unknown = MN.read(POINTS, CUSPS, known=False, lunar_day=13)
        self.assertIn('Лунный день по месту рождения: 13.', known['tekst'])
        self.assertNotIn('Лунный день по месту рождения', unknown['tekst'])
        self.assertIn('Фаза условного момента', unknown['tekst'])

    def test_yod_keeps_both_base_points_and_vertex_without_legacy_prediction(self):
        points = copy.deepcopy(POINTS)
        for name, degree in [('Солнце', 0), ('Луна', 60), ('Марс', 210)]:
            points[name]['градус'] = degree
        text = MN._configuration_text(MN.bridge(points, CUSPS))
        yod = next(line for line in text.splitlines() if 'основание Солнце' in line and 'вершина Марс' in line)
        self.assertIn('Луна', yod)
        self.assertNotIn('особое поручение', text)
        self.assertIn('150°', text)
        self.assertIn('отдельно от пяти основных аспектов', text)


if __name__ == '__main__':
    unittest.main()
