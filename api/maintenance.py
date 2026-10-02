"""Reversible pause: no new API/voice work; saved results remain readable."""
import json
from pathlib import Path
from starlette.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parents[1]

def enabled():
    try:
        return json.loads((ROOT / 'maintenance.json').read_text(encoding='utf-8')).get('enabled') is True
    except FileNotFoundError:
        return False
    except (ValueError, OSError):
        return True

READ_ONLY = frozenset(('/api/klassika/status', '/api/klassika/fayl',
                       '/api/srok/status', '/api/srok/fayl',
                       '/api/kniga/status', '/api/kniga/fayl'))

class MaintenanceGate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket') or not enabled():
            return await self.app(scope, receive, send)
        path = scope.get('path', '')
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1013})
        if scope.get('method') in ('GET', 'HEAD') and (path == '/health' or path in READ_ONLY):
            return await self.app(scope, receive, send)
        headers = {'Cache-Control': 'no-store', 'Retry-After': '86400'}
        if path.startswith('/api/') or scope.get('method') not in ('GET', 'HEAD'):
            response = JSONResponse({'ok': False, 'maintenance': True,
                                     'message': 'Сайт временно не работает'}, status_code=503, headers=headers)
        else:
            response = HTMLResponse((ROOT / 'maintenance.html').read_text(encoding='utf-8'),
                                    status_code=503, headers=headers)
        return await response(scope, receive, send)
