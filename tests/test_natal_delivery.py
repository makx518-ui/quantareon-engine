"""Exercise the actual worker and HTTP delivery; external transports are replaced."""
import importlib
import sys
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent/'natal-test-deps')]
with patch.object(threading.Thread, 'start'):
    KL = importlib.import_module('api.klassika_api')
from engine import chitatel
from fastapi import FastAPI
from fastapi.testclient import TestClient

class DeliveryTest(unittest.TestCase):
    def setUp(self):
        KL.ЗАДАЧИ.clear()
        self.number = 'abcdef1234567890'
        self.card = dict(tarif='klassika_natal', почта='test@example.invalid', lang='ru',
                         имя='Александр', состояние='в очереди', dannye={})
        self.mails, self.files, self.saved, self.alerts = [], [], [], []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(KL, '_записать', side_effect=lambda n,c:self.saved.append(dict(c))))
        self.stack.enter_context(patch.object(KL, '_открыт'))
        self.stack.enter_context(patch.object(KL, '_в_облако'))
        self.stack.enter_context(patch.object(KL, '_в_телеграм', side_effect=lambda t:self.alerts.append(t) or True))
        self.stack.enter_context(patch.dict(sys.modules, {'pochta': SimpleNamespace(
            отправить_текст=lambda *a:self.mails.append(a) or True,
            отправить_файл=lambda *a:self.files.append(a) or True)}))
        app = FastAPI()
        app.include_router(KL.роутер)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def worker(self):
        with patch.object(threading.Thread, 'start'):
            KL._в_фоне(self.number,self.card)

    def test_elapsed_time_uses_server_start_and_survives_cloud_reload(self):
        for state in ('в работе', 'в очереди'):
            card = dict(self.card, состояние=state, создан=1000)
            with patch.object(KL, '_карточка', return_value=card), patch.object(KL.time, 'time', return_value=1091):
                response = self.client.get('/api/klassika/status', params={'nomer': self.number}).json()
            self.assertEqual(response['elapsed_seconds'], 91)
        KL.ЗАДАЧИ[self.number] = {'gotovo': False, 'etap': 'читает', 'started_at': 1000}
        with patch.object(KL.time, 'time', return_value=1120):
            response = self.client.get('/api/klassika/status', params={'nomer': self.number}).json()
        self.assertEqual(response['elapsed_seconds'], 120)

    def test_interrupted_order_can_resume_after_five_minutes(self):
        card = dict(self.card, состояние='в работе', обновлён=1000)
        with patch('engine.arhiv.перечислить', return_value=['open/'+self.number]), \
             patch.object(KL, '_карточка', return_value=card), \
             patch.object(KL, '_пустить', return_value=True) as start:
            with patch.object(KL.time, 'time', return_value=1299):
                KL._обход()
            start.assert_not_called()
            with patch.object(KL.time, 'time', return_value=1300):
                KL._обход()
            start.assert_called_once()
        self.assertLessEqual(KL.ОБХОД, 15)

    def test_factual_error_stops_without_file_and_notifies(self):
        with patch.object(KL, '_построить_натал_или_соляр', side_effect=ValueError('Неподтверждённые аспекты в тексте: Уран–Нептун')):
            self.worker()
        self.assertEqual(self.card['состояние'], 'сбой')
        self.assertEqual(self.card['попыток'], 1)
        self.assertEqual(len(self.mails), 1)
        self.assertEqual(self.files, [])
        self.assertIn('Повторно оформлять или оплачивать заказ не нужно', self.mails[0][2])
        KL._уведомить_задержку(self.number,self.card,окончательно=True)
        self.assertEqual(len(self.mails),1)
        self.assertTrue(self.saved[-1]['уведомление_проверка'])
        self.assertEqual(self.client.get('/api/klassika/fayl',params={'nomer':self.number}).status_code,404)

    def test_temporary_failure_keeps_retry(self):
        with patch.object(KL, '_построить_натал_или_соляр', side_effect=RuntimeError('temporary provider failure')):
            self.worker()
        self.assertEqual(self.card['состояние'],'ждёт повтора')
        self.assertIn('повтор_после',self.card)
        self.assertEqual(len(self.mails),1)
        self.assertEqual(self.files,[])

    def test_transport_failure_does_not_release_invalid_file(self):
        with patch.dict(sys.modules,{'pochta':SimpleNamespace(отправить_текст=lambda *a:False)}):
            with patch.object(KL,'_построить_натал_или_соляр',side_effect=ValueError('Корректор аспектов вернул пустой текст')):
                self.worker()
        self.assertEqual(self.card['состояние'],'сбой')
        self.assertFalse(self.card['уведомление_проверка'])
        self.assertEqual(self.files,[])

    def test_worker_http_download_and_restart_recovery(self):
        html='<html><svg viewBox="0 0 800 800"></svg>Москва</html>'
        with patch.object(KL,'_построить_натал_или_соляр',return_value=(html,'Натальная карта.html')):
            self.worker()
        self.assertEqual(self.card['состояние'],'готово')
        self.assertEqual(self.files[0][-1],html)
        response=self.client.get('/api/klassika/fayl',params={'nomer':self.number})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.text,html)
        self.assertIn('attachment;',response.headers['content-disposition'])
        KL.ЗАДАЧИ.clear()
        with patch.object(KL,'_карточка',return_value=self.card), patch('engine.arhiv._взять',return_value=html):
            response=self.client.get('/api/klassika/status',params={'nomer':self.number})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['html'],html)

    def test_real_calculation_reader_snapshot_export_and_download(self):
        import swisseph as swe
        from engine import arhiv
        original = swe.houses
        def compatible(*args,**kw):
            cusps,angles=original(*args,**kw)
            return (cusps[1:] if len(cusps)==13 else cusps),angles
        self.card['dannye']=dict(тип='натал',дата='09.11.1981',время='03:15',
            место='Москва, Россия',пол='M',_shirota=55.75204,_dolgota=37.61781,_gmt=3)
        with patch.object(swe,'houses',compatible), \
             patch.object(arhiv,'положить_кухню',return_value='test/kitchen.json'), \
             patch.object(arhiv,'положить_карту',return_value='test/chart.html'), \
             patch.object(chitatel,'прочитать',return_value={'razdely':[('Проверка','Контрольный текст')],'storozh':[]}) as reader:
            self.worker()
        self.assertEqual(self.card['состояние'],'готово',self.card.get('ошибка'))
        response=self.client.get('/api/klassika/fayl',params={'nomer':self.number})
        self.assertEqual(response.status_code,200)
        for text in ['<svg','55.75204','37.61781','1981-11-09T00:15:00+00:00','Дева 29°38′17″']:
            self.assertIn(text,response.text)
        self.assertIn('Контрольный текст',response.text)
        self.assertEqual(self.files[0][-1],response.text)
        self.assertIsNotNone(reader.call_args.kwargs['точки'])

    def test_real_calculation_narrative_is_delivered_after_explicit_fact_repair(self):
        import swisseph as swe
        from engine import arhiv
        original = swe.houses
        def compatible(*args, **kwargs):
            cusps, angles = original(*args, **kwargs)
            return (cusps[1:] if len(cusps) == 13 else cusps), angles
        self.card['dannye'] = dict(тип='натал', дата='09.11.1981', время='03:15',
            место='Москва, Россия', пол='M', _shirota=55.75204, _dolgota=37.61781, _gmt=3)
        with patch.object(swe, 'houses', compatible), \
             patch.object(arhiv, 'положить_кухню', return_value='test/kitchen.json'), \
             patch.object(arhiv, 'положить_карту', return_value='test/chart.html'), \
             patch.object(chitatel, '_спросить', return_value='## Чтение\nУран в трине к Нептуну, что обещает успех. Содержательный рассказ.'), \
             patch('engine.passport_guard.guard', side_effect=lambda text, doc, ask, **kwargs:
                   (text.replace('Уран в трине к Нептуну, что обещает успех. ', ''),
                    ['Неподтверждённая связь исключена'])), \
             patch('engine.razvertka.откорректировать', side_effect=lambda text, fn: (text, 0)):
            self.worker()
        self.assertEqual(self.card['состояние'], 'готово', self.card.get('ошибка'))
        self.assertEqual(self.card['machine_natal']['aspects'], 41)
        self.assertEqual(self.card['machine_natal']['mode'], 'two_pass_narrative')
        self.assertTrue(self.card['storozh'])
        response = self.client.get('/api/klassika/fayl', params={'nomer': self.number})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('что обещает успех', response.text)
        self.assertIn('Содержательный рассказ.', response.text)
        self.assertEqual(self.files[0][-1], response.text)
        self.assertIn('Дева 29°38′17″', response.text)

    def test_chat_confirmation_admin_order_actual_cash_worker_and_file(self):
        import os
        import swisseph as swe
        from engine import arhiv, chat_klassika
        PA=importlib.import_module('api.oplata_api')
        self.client.app.include_router(PA.роутер)
        database={'заказы':[]}
        async def reply(*args,**kw):
            return '[LAUNCH_ASTRO_NATAL: 09.11.1981, TIME: 03:15, PLACE: Москва / Россия, GENDER: M]'
        def start(n,c):
            with patch.object(threading.Thread,'start'): KL._в_фоне(n,c)
        original=swe.houses
        def compatible(*args,**kw):
            cusps,angles=original(*args,**kw)
            return (cusps[1:] if len(cusps)==13 else cusps),angles
        geo={'latitude':55.75204,'longitude':37.61781,'timezone_name':'Europe/Moscow',
             'address':'Москва · Россия','candidates':[{'population':12000000}]}
        from api.location_check.collection import Collection
        from api.location_check.world_search import Service
        def lookup(source,params):
            if source=='geonames':return {'geonames':[dict(name='Москва',lat='55.75204',lng='37.61781',countryCode='RU',countryName='Россия',adminName1='Москва',adminName2='Москва')]}
            return []
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{'klassika_api':KL,'main':SimpleNamespace(geocode=lambda *a:geo)}))
            stack.enter_context(patch.dict(os.environ,{'QUANTAREON_ADMIN_KEY':'local-test-key-0001'}))
            stack.enter_context(patch.object(chat_klassika,'klassika_chat_reply',reply))
            stack.enter_context(patch('api.location_check.collection.collection',Collection(Service(lookup))))
            stack.enter_context(patch.object(PA,'_читать',return_value=database))
            stack.enter_context(patch.object(PA,'_писать'))
            stack.enter_context(patch.object(PA,'_в_телеграм',return_value=True))
            stack.enter_context(patch.dict(PA.ПОЛУЧАТЕЛЬ,{'telefon':'test-only'}))
            stack.enter_context(patch.object(KL,'_карточка',return_value=None))
            stack.enter_context(patch.object(KL,'_пустить',side_effect=start))
            stack.enter_context(patch.object(swe,'houses',compatible))
            stack.enter_context(patch.object(arhiv,'положить_кухню',return_value='test/kitchen.json'))
            stack.enter_context(patch.object(arhiv,'положить_карту',return_value='test/chart.html'))
            stack.enter_context(patch.object(chitatel,'прочитать',return_value={'razdely':[('Проверка','Контрольный текст')]}))
            r=self.client.post('/api/klassika/chat',json={'tarif':'klassika_natal','text':'Данные Александра','history':[]})
            self.assertEqual(r.status_code,200,r.text)
            choice=r.json()['location_choice']
            self.assertNotIn('dannye',r.json())
            self.assertEqual(database['заказы'],[])
            r=self.client.post('/api/klassika/chat',json={'tarif':'klassika_natal','text':'Подтверждаю место','location_token':choice['token'],'selected':choice['candidates'][0]['id'],'history':[]})
            self.assertEqual(r.status_code,200,r.text)
            d=r.json()['dannye']
            payload={'pochta':'test@example.invalid','tarif':'klassika_natal','admin':'local-test-key-0001','astro_dannye':d}
            self.assertEqual(self.client.post('/api/oplata/zakaz',json=payload).status_code,400)
            self.assertEqual(database['заказы'],[])
            d['_подтверждено']=True
            r=self.client.post('/api/oplata/zakaz',json=payload)
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(database['заказы'][0]['состояние'],'оплачен')
            key=database['заказы'][0]['ключ']
            n=key.removeprefix('QN-').replace('-','').lower()
            r=self.client.get('/api/klassika/fayl',params={'nomer':n})
            self.assertEqual(r.status_code,200,r.text)
            self.assertIn('Дева 29°38′17″',r.text)
            self.assertIn('55.75204',r.text)
            self.assertTrue(self.files)
