import unittest
import ast
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import RedirectResponse, Response
from api.location_check import routes

class Routes(unittest.TestCase):
    def setUp(self):
        routes._calls.clear()
        app=FastAPI();app.include_router(routes.router)
        self.client=TestClient(app)
    def test_page_and_complete_countries(self):
        page=self.client.get('/location-check')
        self.assertEqual(page.status_code,200)
        self.assertIn('/api/location-check/search',page.text)
        self.assertIn('карта и заказ не создаются',page.text)
        self.assertGreater(len(self.client.get('/api/location-check/countries').json()),250)
    def test_search_dispatch_without_order(self):
        with patch.object(routes.service,'search',return_value={'status':'confirmation'}) as search:
            r=self.client.post('/api/location-check/search',json={'place':'Москва','country':'RU'})
            self.assertEqual(r.json()['status'],'confirmation')
            search.assert_called_once_with(place='Москва',country='RU')
    def test_confirm_dispatch(self):
        data={'token':'a','selected':'b','date':'1961-01-30','birth_time':'21:00'}
        with patch.object(routes.service,'confirm',return_value={'status':'confirmed'}) as confirm:
            self.assertEqual(self.client.post('/api/location-check/confirm',json=data).json()['status'],'confirmed')
            confirm.assert_called_once_with(**data)
    def test_bad_shapes_do_not_call_search(self):
        with patch.object(routes.service,'search') as search:
            for data in [[],{}, {'place':'x','country':'RU','unknown':'x'},{'place':{},'country':'RU'}]:
                self.assertEqual(self.client.post('/api/location-check/search',json=data).status_code,400)
            search.assert_not_called()
    def test_oversized_body(self):
        self.assertEqual(self.client.post('/api/location-check/search',content=b'x'*12001).status_code,400)
    def test_exception_and_busy_leave_slot_available(self):
        with patch.object(routes.service,'search',side_effect=RuntimeError()):
            self.assertEqual(self.client.post('/api/location-check/search',json={'place':'x','country':'RU'}).status_code,503)
        self.assertTrue(routes._slots.acquire(blocking=False));routes._slots.release()
    def test_rate_limit(self):
        with patch.object(routes.service,'search',return_value={'status':'confirmation'}):
            for _ in range(30):self.client.post('/api/location-check/search',json={'place':'x','country':'RU'})
        self.assertEqual(self.client.post('/api/location-check/search',json={'place':'x','country':'RU'}).status_code,429)

class Gate(unittest.TestCase):
    def setUp(self):
        # Execute the actual production gate without starting unrelated voice models.
        tree=ast.parse((Path(__file__).parents[1]/'api/main.py').read_text(encoding='utf-8'))
        nodes=[]
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_LOCATION_CHECK_PUBLIC' for t in node.targets):nodes.append(node)
            if isinstance(node,ast.AsyncFunctionDef) and node.name=='gate':
                node.decorator_list=[];nodes.append(node)
        ns=dict(Request=routes.Request,RedirectResponse=RedirectResponse,Response=Response,
                _СЧЁТЧИК_БЕЗ_ПАРОЛЯ=(),_ПОЧТА_БЕЗ_ПАРОЛЯ=(),_РЕНДЕР_БЕЗ_ПАРОЛЯ=(),_ok=lambda token:False,COOKIE='qtok')
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'api/main.py','exec'),ns)
        app=FastAPI();app.include_router(routes.router);app.middleware('http')(ns['gate'])
        routes._calls.clear();self.client=TestClient(app,follow_redirects=False)
    def test_preview_and_search_available_without_engine_password(self):
        self.assertEqual(self.client.get('/location-check',headers={'accept':'text/html'}).status_code,200)
        self.assertEqual(self.client.get('/api/location-check/countries').status_code,200)
        with patch.object(routes.service,'search',return_value={'status':'confirmation'}):
            self.assertEqual(self.client.post('/api/location-check/search',json={'place':'x','country':'RU'}).status_code,200)
        with patch.object(routes.service,'confirm',return_value={'status':'confirmed'}):
            self.assertEqual(self.client.post('/api/location-check/confirm',json={'token':'x','selected':'x','date':'2000-01-01','birth_time':''}).status_code,200)
    def test_other_paths_and_similar_prefixes_remain_protected(self):
        for path in ['/','/natal','/geocode','/location-check-private','/api/location-check/search-private']:
            self.assertEqual(self.client.get(path).status_code,401)

if __name__=='__main__':unittest.main()
