"""Regression checks for collection, historical time, passport and final aspect gate."""
import ast
import asyncio
from datetime import datetime, date
from pathlib import Path
import runpy
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent/'natal-test-deps')]
source = ast.parse((ROOT/'api/klassika_api.py').read_text(encoding='utf-8-sig'))
names = {'_ОшибкаМеста','_момент_рождения','_исторический_пояс','_строка','_число',
         '_человек_годен','чистые_dannye','_по_русски','_разобрать_место','_геокод','_собрать_dannye','_дата_в_iso'}
nodes = [n for n in source.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name in names]
nodes += [n for n in source.body if isinstance(n,ast.Assign) and any(
    isinstance(t,ast.Name) and t.id in {'_ДАТА','_ВРЕМЯ','_ПОЛЯ_ЧЕЛОВЕКА','ТИП_ПО_ТАРИФУ'} for t in n.targets)]
ns = {'datetime':datetime,'re':__import__('re')}
async def pool(fn,*args): return fn(*args)
ns['run_in_threadpool']=pool
exec(compile(ast.Module(body=nodes,type_ignores=[]),'klassika_validation','exec'),ns)
from engine import kosmogramma as K
from engine.storozh_faktov import проверить_аспекты_строго

class CompletionTest(unittest.TestCase):
    def test_collect_confirm_and_export_same_coordinates(self):
        geo=dict(latitude=55.75204,longitude=37.61781,timezone_name='Europe/Moscow',utc_offset=999,
                 address='Москва · Россия',candidates=[{'population':12000000}])
        marker=dict(тип='натал',дата='09.11.1981',время='03:15',место='Москва / Россия',пол='M')
        with patch.dict(sys.modules,{'main':SimpleNamespace(geocode=lambda *a:geo)}):
            d=asyncio.run(ns['_собрать_dannye'](marker))
            self.assertEqual(d['_gmt'],3)
            self.assertEqual(geo['utc_offset'],999) # Never mutate geocoder cache.
            self.assertIsNone(ns['чистые_dannye']('klassika_natal',d))
            d['_подтверждено']=True
            clean=ns['чистые_dannye']('klassika_natal',d)
            data=runpy.run_path(str(ROOT/'tests/test_natal_export.py'),run_name='integration_fixture')
            html=data['render_chart'](data['SNAPSHOT'],dict(дата=clean['дата'],время=clean['время'],
                место=clean['место'],широта=clean['_shirota'],долгота=clean['_dolgota'],гмт=clean['_gmt']))
            self.assertIn('55.75204',html);self.assertIn('1981-11-09T00:15:00+00:00',html)
        with patch.dict(sys.modules,{'main':SimpleNamespace(geocode=lambda *a:dict(geo,candidates=[{'population':100}]))}):
            with self.assertRaises(ns['_ОшибкаМеста']): asyncio.run(ns['_геокод']('Москва / Россия'))
            with self.assertRaises(ns['_ОшибкаМеста']): asyncio.run(ns['_геокод']('Москва'))

    def test_moscow_1981_exact_time(self):
        self.assertEqual(ns['_исторический_пояс']({'timezone_name':'Europe/Moscow'},'09.11.1981','03:15'),3)

    def test_dst_nonexistent_and_ambiguous_stop(self):
        for day in ['31.03.2024','27.10.2024']:
            with self.assertRaises(ns['_ОшибкаМеста']):
                ns['_исторический_пояс']({'timezone_name':'Europe/Berlin'},day,'02:30')

    def test_invalid_calendar_and_time(self):
        for d,t in [('31.02.1981','03:15'),('09.11.1981','24:00'),('09.11.1981','03:60')]:
            with self.assertRaises(ns['_ОшибкаМеста']): ns['_момент_рождения'](d,t)

    def test_verified_address_preserves_region_country(self):
        self.assertEqual(ns['_по_русски']({'address':'Советское · район X · область Y · Казахстан'},'old'),
                         'Советское, район X, область Y, Казахстан')

    def test_payment_requires_explicit_confirmation(self):
        d=dict(тип='натал',дата='09.11.1981',время='03:15',место='Москва, Россия',пол='M',
               _shirota=55.75204,_dolgota=37.61781,_gmt=3)
        self.assertIsNone(ns['чистые_dannye']('klassika_natal',d))
        d['_подтверждено']=True
        self.assertIsNotNone(ns['чистые_dannye']('klassika_natal',d))
        d['дата']='31.02.1981'
        self.assertIsNone(ns['чистые_dannye']('klassika_natal',d))

    def test_unsupported_multi_target_stops(self):
        points={n:K.точка(n,d,False) for n,d in [('Уран',239.5386),('Нептун',263.2254),('Плутон',205.1455)]}
        with self.assertRaisesRegex(ValueError,'Уран–Нептун'):
            проверить_аспекты_строго('Уран в секстиле к Нептуну и Плутону.',points)

    def test_valid_aspect_and_negative_statement_pass(self):
        points={n:K.точка(n,d,False) for n,d in [('Уран',0),('Нептун',60),('Плутон',100)]}
        проверить_аспекты_строго('Уран в секстиле к Нептуну.',points)
        проверить_аспекты_строго('Уран не образует секстиль к Плутону.',points)
        with self.assertRaisesRegex(ValueError,'Уран–Плутон'):
            проверить_аспекты_строго('Уран в секстиле к Нептуну и Плутону.',points)

    def test_coordinated_aspects_keep_subject(self):
        points={n:K.точка(n,d,False) for n,d in [('Солнце',0),('Луна',120),('Марс',300)]}
        проверить_аспекты_строго('Солнце в трине к Луне и в секстиле к Марсу.',points)
        with self.assertRaisesRegex(ValueError,'Солнце–Марс'):
            проверить_аспекты_строго('Солнце в трине к Луне и в трине к Марсу.',points)
        with self.assertRaisesRegex(ValueError,'Луна–Марс'):
            проверить_аспекты_строго('Солнце в трине к Луне, а Луна в секстиле к Марсу.',points)

    def test_completed_age_before_and_on_birthday(self):
        points={'Солнце':K.точка('Солнце',226,False),'Луна':K.точка('Луна',5,False)}
        for today,age in [(date(2026,10,1),44),(date(2026,11,9),45)]:
            text='\n'.join(K.свод_натала(points,тж={'градус':70,'лет':44.9},
                                       дата_рождения=date(1981,11,9),на_дату=today))
            self.assertIn(f'{age} полных лет',text)

    def test_known_and_unknown_passport_labels(self):
        kw=dict(дата_р='09.11.1981',место_р='Москва',пояс_р='GMT+3',солнечный_час='03:15',расхождение_сек=None)
        known=K.паспорт(**kw,время_известно=True,время_рождения='03:15')
        self.assertIn('местное время рождения: 03:15',known)
        self.assertNotIn('условный',known)
        self.assertNotIn('0.0″',known)
        self.assertIn('не установленное время рождения',K.паспорт(**kw))

    def test_machine_prompt_connected_and_missing_file_stops(self):
        tree=ast.parse((ROOT/'engine/chitatel.py').read_text(encoding='utf-8-sig'))
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and
                   n.name in {'_система','_правила_машинных_фактов'}]
        space={'ЯДРО':'core','МЕТОДОЛОГИЯ':'method','МАШИННЫЕ_ФАКТЫ':'MACHINE_FACTS.md',
               '_файл':lambda name:(ROOT/'data/chitatel'/name).read_text(encoding='utf-8')
                   if name=='MACHINE_FACTS.md' else name}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'system_prompt','exec'),space)
        prompt=space['_система']('Образцы текста')
        self.assertTrue(prompt.endswith('без отчёта о внутренней самопроверке.\n'))
        self.assertIn('два отдельно подтверждённых секстиля',prompt)
        space['_файл']=lambda name:'' if name=='MACHINE_FACTS.md' else name
        with self.assertRaisesRegex(RuntimeError,'MACHINE_FACTS'):space['_система']()

if __name__=='__main__': unittest.main()
