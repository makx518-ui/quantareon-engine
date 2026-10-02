"""Independent server-side search preview. No order or chart endpoints are called."""
import json
import threading
import time
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from .world_search import Service, COUNTRIES, ROOT

router = APIRouter()
service = Service()
_slots = threading.BoundedSemaphore(2)
_lock = threading.Lock()
_calls = {}


@router.get('/location-check', include_in_schema=False)
def page():
    return FileResponse(ROOT/'index.html', headers={'Cache-Control':'no-store'})


@router.get('/api/location-check/countries')
def countries():
    return sorted(COUNTRIES)


@router.post('/api/location-check/{action}')
async def operate(action: str, request: Request):
    if action not in ('search', 'confirm'):
        return JSONResponse({'status':'invalid','message':'Неизвестный запрос.'},status_code=404)
    client = request.client.host if request.client else 'unknown'
    now=time.monotonic()
    with _lock:
        expired=[ip for ip,(since,_) in _calls.items() if now-since>=60]
        for ip in expired:del _calls[ip]
        since,count=_calls.get(client,(now,0))
        if count>=30 or (client not in _calls and len(_calls)>=1000):
            return JSONResponse({'status':'unavailable','message':'Слишком много запросов. Подождите минуту; введённые данные сохранены.'},status_code=429)
        _calls[client]=(since,count+1)
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>12000:
            return JSONResponse({'status':'invalid','message':'Запрос слишком большой.'},status_code=400)
    expected={'place','country','region','district'} if action=='search' else {'token','selected','date','birth_time'}
    required={'place','country'} if action=='search' else expected
    try:
        data=json.loads(body)
        if not isinstance(data,dict) or not required<=data.keys() or not data.keys()<=expected:
            raise ValueError()
        if any(not isinstance(v,str) or len(v)>300 for v in data.values()):raise ValueError()
    except (ValueError,UnicodeError):
        return JSONResponse({'status':'invalid','message':'Проверьте заполнение полей.'},status_code=400)
    if not _slots.acquire(blocking=False):
        return JSONResponse({'status':'unavailable','message':'Поиск сейчас занят. Данные сохранены; повторите попытку.'},status_code=503)
    try:
        return await run_in_threadpool(getattr(service,action),**data)
    except Exception:
        return JSONResponse({'status':'unavailable','message':'Не удалось завершить проверку. Данные сохранены; повторите попытку.'},status_code=503)
    finally:
        _slots.release()
