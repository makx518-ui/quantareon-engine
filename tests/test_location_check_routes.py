import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
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

if __name__=='__main__':unittest.main()
