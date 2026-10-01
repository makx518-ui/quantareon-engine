"""Regressions from Alexander's real export and reader prompt boundaries; offline."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'natal-test-deps')]
from engine import chitatel as C, kosmogramma as K, most as M, klassika_natal as KN
from engine.af import kod360
from engine.natal_reading import данные_прочтения
from engine.storozh_faktov import сторожить

N = json.loads((ROOT / 'tests/fixtures/natal_moscow_1981.json').read_text(encoding='utf-8'))['moscow']
POINTS = {n: K.точка(n, p['abs_degree'], p['retrograde']) for n, p in N['planets'].items()}
ANGLES = {'ASC': N['cusps'][0], 'MC': N['cusps'][9]}
BRIDGE = M.Мост(POINTS, N['cusps'], ANGLES)
SHELF = C._полка_без_ядер(M.полочка_натала(POINTS, N['cusps'], ANGLES, реальные=True))
CODES = KN._коды_полки(SHELF)


def check(text):
    return сторожить(text, POINTS, N['cusps'], ANGLES, SHELF)


class NatalReadingTest(unittest.TestCase):
    cases = [
        ('Чёрная Луна', 'Тень этой карты расположилась в 5°08′ Стрельца; направляет её Юпитер.', 'Юпитер'),
        ('Белая Луна', 'Благодать пребывает в 29°03′ Овна; её хозяин — волевой Марс.', 'Марс'),
        ('Хирон', 'Рана замерла в 20°33′ Тельца; управляет этой точкой Венера.', 'Венера'),
        ('ASC', 'Точка входа зафиксирована в 29°38′ Девы; её хозяин — Меркурий.', 'Меркурий'),
        ('MC', 'Точка высшей цели указывает на 29°30′ Близнецов; её диспозитор — Меркурий.', 'Меркурий'),
    ]

    def test_five_correct_codes_survive_mentions_of_rulers(self):
        for name, opening, ruler in self.cases:
            with self.subTest(name=name):
                text = f'## {name}\n{opening} Код этой точки — [{CODES[name][0]}].'
                fixed, changes = check(text)
                self.assertEqual(fixed, text)
                self.assertEqual(changes, [])

    def test_five_wrong_ruler_codes_are_repaired_for_the_actual_owner(self):
        for name, opening, ruler in self.cases:
            with self.subTest(name=name):
                wrong = f'## {name}\n{opening} Код этой точки — [{CODES[ruler][0]}].'
                fixed, changes = check(wrong)
                self.assertIn(f'[{CODES[name][0]}]', fixed)
                self.assertEqual(len(changes), 1)
                self.assertTrue(changes[0].startswith(name + ':'))
                self.assertEqual(check(fixed), (fixed, []))

    def test_mc_direct_ruler_is_not_mercurs_ruler(self):
        correct = '## Вершина призвания — MC\nТочка высшей цели в Близнецах; её диспозитор — Меркурий.'
        self.assertEqual(check(correct), (correct, []))
        wrong = correct.replace('— Меркурий.', '— Венера.')
        fixed, changes = check(wrong)
        self.assertEqual(fixed, correct)
        self.assertEqual(changes, ['MC: диспозитор «Венера» → «Меркурий»'])

    def test_explicit_code_owner_can_differ_from_section(self):
        text = f'## MC\nКод Меркурия — [{CODES["Меркурий"][0]}].'
        self.assertEqual(check(text), (text, []))

    def test_new_explicit_subject_overrides_previous_section(self):
        text = (f'## ASC\nМеркурий стоит в Весах. Его диспозитор — Венера. '
                f'Код Меркурия — [{CODES["Меркурий"][0]}].')
        self.assertEqual(check(text), (text, []))

    def test_ambiguous_two_planet_code_is_not_guessed(self):
        text = f'Меркурий и Юпитер взаимодействуют; код этой связи — [{CODES["MC"][0]}].'
        self.assertEqual(check(text), (text, []))

    def test_precision_correction_survives(self):
        fixed, changes = check('Меркурий в точном соединении с Юпитером.')
        self.assertEqual(fixed, 'Меркурий в соединении с Юпитером.')
        self.assertTrue(any('2.93' in x for x in changes))

    def test_cards_use_own_af_dictionary_and_direct_rulers(self):
        raw = данные_прочтения(BRIDGE, SHELF)
        payload = json.loads(raw.split('\n', 1)[1])
        points = {p['имя']: p for p in payload['точки']}
        for name, degree in BRIDGE.flat.items():
            with self.subTest(name=name):
                self.assertEqual(points[name]['код_градуса']['tag'], CODES[name][0])
                self.assertEqual(points[name]['символ_градуса'], int(degree % 30) + 1)
                self.assertNotIn('ядро', points[name])
        self.assertEqual(points['MC']['непосредственный_диспозитор'], 'Меркурий')
        self.assertEqual(points['Меркурий']['непосредственный_диспозитор'], 'Венера')
        self.assertFalse(any({x['A'], x['B']} == {'Уран', 'Нептун'} for x in payload['аспекты']))
        conjunction = next(x for x in payload['аспекты'] if {x['A'], x['B']} == {'Меркурий', 'Юпитер'})
        self.assertEqual(conjunction['вид'], 'соединение')
        self.assertEqual(conjunction['номинальный_угол'], 0)
        self.assertAlmostEqual(conjunction['реальный_угол'], 2.9308, places=4)

    def test_unknown_time_never_gets_houses_or_angles(self):
        bridge = M.Мост(POINTS, [])
        payload = json.loads(данные_прочтения(bridge).split('\n', 1)[1])
        self.assertFalse(any(p['имя'] in ('ASC', 'MC') for p in payload['точки']))
        self.assertTrue(all('дом' not in p and 'управляет_домами' not in p for p in payload['точки']))

    def test_conflicting_degree_code_has_no_invented_meaning(self):
        shelf = SHELF.replace(CODES['MC'][0], CODES['Меркурий'][0])
        payload = json.loads(данные_прочтения(BRIDGE, shelf).split('\n', 1)[1])
        point = next(p for p in payload['точки'] if p['имя'] == 'MC')
        self.assertIn('противоречие_кода', point)
        self.assertNotIn('код_градуса', point)

    def test_chapter_cards_do_not_repeat_other_points_or_aspect_table(self):
        payload = json.loads(данные_прочтения(
            BRIDGE, SHELF, имена=M.ТОЧКИ_БЛОКА['инструменты'], с_аспектами=False).split('\n', 1)[1])
        self.assertEqual({p['имя'] for p in payload['точки']}, set(M.ТОЧКИ_БЛОКА['инструменты']))
        self.assertEqual(payload['аспекты'], [])

    def test_teaching_example_math_and_codes_are_separate_from_current_chart(self):
        prompt = (ROOT / 'data/chitatel/NATAL_READING.md').read_text(encoding='utf-8')
        self.assertEqual(KN._разн(40.25, 160.25), 120)
        for degree in (40.25, 160.25):
            self.assertIn('[' + kod360.code_by_abs(degree)['tag'] + ']', prompt)
        self.assertIn('НЕ ДАННЫЕ КЛИЕНТА', prompt)

    def test_natal_rules_do_not_change_other_product_system_prompt(self):
        general = C._система()
        natal = C._система(натал=True)
        self.assertNotIn('Учебный образец: Уран', general)
        self.assertIn('Учебный образец: Уран', natal)
        self.assertTrue(natal.endswith(C._правила_машинных_фактов()))

    def test_natal_calls_only_order_editor_and_rejects_free_prose(self):
        calls = []
        def model(system, messages, *args, **kwargs):
            calls.append((system, messages[0]['content']))
            return '## Проверяемый раздел\nСодержательный текст без расчётных утверждений.'
        with patch.object(C, '_спросить', side_effect=model), \
             patch.object(C, '_спросить_целиком', side_effect=model), \
             patch('engine.razvertka.откорректировать', side_effect=lambda text, fn: (text, 0)):
            result = C.прочитать('', заказ='natal', точки=POINTS, куспиды=N['cusps'], углы=ANGLES)
        self.assertEqual(len(calls), 1)
        self.assertIn('Верни только JSON', calls[0][0])
        packet = json.loads(calls[0][1])
        self.assertEqual(len(packet['cards']), 17)
        self.assertEqual(len(packet['aspects']), 41)
        self.assertNotIn('Содержательный текст без расчётных утверждений.', result['tekst'])
        self.assertEqual(result['machine_natal']['mode'], 'machine')
        self.assertEqual(result['machine_natal']['aspects'], 41)

    def test_solar_reader_does_not_receive_natal_contract_or_new_scenario(self):
        calls = []
        def model(system, messages, *args, **kwargs):
            calls.append((system, messages[0]['content']))
            return '## Проверяемый раздел\nСодержательный текст.'
        with patch.object(C, '_спросить', side_effect=model), \
             patch.object(C, '_спросить_целиком', side_effect=model), \
             patch('engine.razvertka.откорректировать', side_effect=lambda text, fn: (text, 0)):
            C.прочитать('', заказ='solar', точки=POINTS, куспиды=N['cusps'], углы=ANGLES)
        self.assertEqual(len(calls), 4)
        for system, request in calls:
            self.assertNotIn('Учебный образец: Уран', system)
            self.assertNotIn('ДАННЫЕ СМЫСЛОВОГО ПРОЧТЕНИЯ', request)
            self.assertNotIn('вход → потребность → действие', request)


if __name__ == '__main__':
    unittest.main()
