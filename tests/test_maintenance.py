import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.maintenance import MaintenanceGate

class MaintenanceTest(unittest.TestCase):
    def test_closed_mode_blocks_generation_and_voice_but_keeps_saved_results(self):
        app = FastAPI()
        calls = []
        @app.post('/api/klassika/chat')
        def chat():
            calls.append('chat')
            return {'ok': True}
        @app.get('/health')
        def health():
            return {'ok': True}
        @app.get('/api/klassika/fayl')
        def file():
            return {'saved': True}
        app.add_middleware(MaintenanceGate)
        with patch('api.maintenance.enabled', return_value=True), TestClient(app) as client:
            self.assertEqual(client.get('/').status_code, 503)
            self.assertIn('Сайт временно не работает', client.get('/').text)
            self.assertEqual(client.post('/api/klassika/chat').status_code, 503)
            self.assertEqual(client.post('/chat').status_code, 503)
            self.assertEqual(client.get('/health').status_code, 200)
            self.assertEqual(client.get('/api/klassika/fayl').status_code, 200)
            with self.assertRaises(Exception) as error:
                with client.websocket_connect('/ws/voice'):
                    pass
            self.assertEqual(error.exception.code, 1013)
            self.assertEqual(calls, [])
        with patch('api.maintenance.enabled', return_value=False), TestClient(app) as client:
            self.assertEqual(client.post('/api/klassika/chat').status_code, 200)
            self.assertEqual(calls, ['chat'])

    def test_background_recovery_is_paused(self):
        import threading
        with patch.object(threading.Thread, 'start'):
            from api import klassika_api, srok_api
        for module in (klassika_api, srok_api):
            with patch('api.maintenance.enabled', return_value=True), \
                 patch.object(module, '_карточка', side_effect=AssertionError('Recovery must remain paused')):
                self.assertFalse(module._обход())
                self.assertFalse(module._пустить('abcdef1234567890', {}))
