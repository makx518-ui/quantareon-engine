"""Verify exported numerical facts, offline SVG, unknown time and snapshot reuse."""
import ast
import copy
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / 'natal-test-deps'))
from engine.natal_export import render_chart, position, house
from engine.karta_html import карта_клиенту
from engine import kosmogramma as K

SOURCE = json.loads((ROOT / 'tests/fixtures/natal_moscow_1981.json').read_text(encoding='utf-8'))
NATAL = SOURCE['moscow']
POINTS = {name: K.точка(name, p['abs_degree'], p['retrograde']) for name,p in NATAL['planets'].items()}
SNAPSHOT = dict(tochki=POINTS, kuspidy=NATAL['cusps'], vremya_izvestno=True,
                rozhdenie=SOURCE['utc'], aspekty=K.аспекты_космограммы(POINTS))
BIRTH = dict(дата='09.11.1981', время='03:15', место='Москва', широта=55.75204, долгота=37.61781, гмт=3)


class NatalExportTest(unittest.TestCase):
    def test_moscow_facts_match_engine(self):
        result = render_chart(SNAPSHOT, BIRTH)
        for name,p in NATAL['planets'].items():
            if name == 'ТЖ':
                continue
            # Dispatcher stores degrees to four decimal places (<= 0.18 arcseconds).
            self.assertLessEqual(abs(POINTS[name]['градус']-p['abs_degree']), .000051)
            self.assertIn(position(POINTS[name]['градус']), result, name)
            self.assertEqual(house(p['abs_degree'],NATAL['cusps']), p['house'])
        self.assertIn('Дева 29°38′17″',result)
        self.assertIn('Близнецы 29°30′05″',result)
        for value in ['55.75204','37.61781','+3 ч',SOURCE['utc']]:
            self.assertIn(value,result)

    def test_svg_is_valid_offline_and_accessible(self):
        result = render_chart(SNAPSHOT, BIRTH)
        svg = result[result.index('<svg'):result.index('</svg>')+6]
        tree = ET.fromstring(svg)
        self.assertEqual(tree.attrib['viewBox'],'0 0 800 800')
        self.assertEqual(tree.attrib['role'],'img')
        self.assertNotIn('href=',svg)
        self.assertNotIn('<script',svg)

    def test_unknown_time_never_draws_houses(self):
        snapshot = dict(SNAPSHOT, vremya_izvestno=False)
        result = render_chart(snapshot,BIRTH)
        self.assertIn('Космограмма',result)
        self.assertNotIn('>ASC<',result)
        self.assertNotIn('>MC<',result)
        self.assertNotIn('Фортуна',result)
        self.assertNotIn('Вертекс',result)
        self.assertIn('не указано',result)
        self.assertIn('условная космограмма',result)

    def test_invalid_snapshot_is_rejected(self):
        for cusps in [None, [0]*12, NATAL['cusps'][:11], [float('nan')]+NATAL['cusps'][1:]]:
            with self.assertRaises(ValueError):
                render_chart(dict(SNAPSHOT,kuspidy=cusps),BIRTH)

    def test_rounding_and_house_wrap(self):
        self.assertEqual(position(359.999999),'Овен 0°00′00″')
        self.assertEqual(position(29.999999),'Телец 0°00′00″')
        cusps = [(350+i*30)%360 for i in range(12)]
        self.assertEqual(house(0,cusps),1)
        self.assertEqual(house(20,cusps),2)

    def test_escape_place_and_planet_names(self):
        snapshot = copy.deepcopy(SNAPSHOT)
        snapshot['tochki']['<img src=x onerror=alert(1)>'] = dict(градус=1)
        result=render_chart(snapshot,dict(BIRTH,место='<script>alert(1)</script>'))
        self.assertNotIn('<script>',result)
        self.assertNotIn('<img',result)
        self.assertIn('&lt;script&gt;',result)

    def test_client_html_embeds_chart_before_reading(self):
        result=карта_клиенту([('Проверка','Текст разбора')],'Александр',
                            данные_рождения=BIRTH,расчёт_карты=SNAPSHOT)
        self.assertLess(result.index('id="natal-facts"'),result.index('id="r0"'))
        self.assertIn('.natal-table',result)
        other=карта_клиенту([('Проверка','Текст')],'Александр',заказ='solyar',расчёт_карты=SNAPSHOT)
        self.assertNotIn('<svg',other)

    def test_export_reuses_snapshot_without_second_calculation(self):
        # Execute the actual export entry point; replace only archive I/O and dispatcher.
        source=ast.parse((ROOT/'api_vhod.py').read_text(encoding='utf-8'))
        defs=[node for node in source.body if isinstance(node,ast.FunctionDef) and node.name in
              ('карта_файлом','_разобрать_дату','_разобрать_время')]
        dispatcher=SimpleNamespace(разобрать=lambda **kw: self.fail('Unexpected recalculation'))
        namespace={'D':dispatcher}
        exec(compile(ast.Module(body=defs,type_ignores=[]),'api_vhod.py','exec'),namespace)
        archive=SimpleNamespace(положить_карту=lambda *args,**kwargs:'local-preview.html')
        request=dict(zakaz='natal',data='09.11.1981',vremya='03:15',mesto='Москва',imya='Александр',
                     shirota=55.75204,dolgota=37.61781,gmt=3)
        with patch.dict(sys.modules,{'engine.arhiv':archive}):
            result=namespace['карта_файлом'](request,[('Проверка','Текст')],SNAPSHOT)
        self.assertIn('55.75204',result['html'])
        self.assertIn('<svg',result['html'])
        from engine import dispetcher
        import swisseph as swe
        original=swe.houses
        def houses_compatible(*args,**kwargs):
            cusps,angles=original(*args,**kwargs)
            return (cusps[1:] if len(cusps)==13 else cusps),angles
        namespace['D']=dispetcher
        with patch.dict(sys.modules,{'engine.arhiv':archive}), patch.object(swe,'houses',houses_compatible):
            result=namespace['карта_файлом'](request,[('Проверка','Текст')])
            self.assertIn('1981-11-09T00:15:00+00:00',result['html'])
            self.assertIn('Дева 29°38′17″',result['html'])
            unknown=namespace['карта_файлом'](dict(request,vremya=None),[('Проверка','Текст')])
            self.assertIn('Космограмма',unknown['html'])
            self.assertNotIn('>ASC<',unknown['html'])


if __name__ == '__main__':
    unittest.main()
