"""Server-owned location choices for the existing klassika chat."""
import copy
import secrets
import threading
import time
from datetime import date
from .routes import service


class Collection:
    def __init__(self, search=service):
        self.search=search
        self.sessions={}
        self.lock=threading.Lock()

    def start(self, marker):
        marker=copy.deepcopy(marker)
        kind=marker['тип']
        people=[marker] if kind in ('натал','соляр') else [marker.get('первый',{}),marker.get('второй',{})]
        tasks=[]
        for i,person in enumerate(people):
            raw=person.get('место') or ''
            parts=[p.strip() for p in raw.split('/') if p.strip()]
            if len(parts)<2:return {'ok':True,'reply':'Укажи страну и населённый пункт рождения. Область и прежний район можно оставить как помнишь.'}
            try:
                d,m,y=map(int,person['дата'].split('.'));iso=date(y,m,d).isoformat()
            except (ValueError,KeyError,TypeError):return {'ok':True,'reply':'Проверь дату рождения.'}
            tasks.append(dict(raw=raw,parts=parts,date=iso,birth_time=person.get('время') or '',label='Место рождения' if len(people)==1 else f'Место рождения {i+1}-го человека'))
        if kind=='соляр':
            raw=marker.get('текущее_место') or marker['место']
            parts=[p.strip() for p in raw.split('/') if p.strip()]
            if len(parts)<2:return {'ok':True,'reply':'Укажи страну и населённый пункт, где встретишь день рождения.'}
            tasks.append(dict(raw=raw,parts=parts,date=date.today().isoformat(),birth_time='',label='Место встречи дня рождения'))
        token=secrets.token_urlsafe(24)
        session=dict(marker=marker,tasks=tasks,index=0,places=[],expires=time.monotonic()+3600,busy=False)
        with self.lock:
            self.sessions={k:v for k,v in self.sessions.items() if v['expires']>time.monotonic()}
            if len(self.sessions)>=256:return {'ok':True,'reply':'Поиск сейчас занят. Повтори сообщение чуть позже.'}
            self.sessions[token]=session
        return self._next(token,session)

    def _next(self,token,session):
        if session['index']==len(session['tasks']):
            with self.lock:self.sessions.pop(token,None)
            return {'_ready':session['marker'],'_places':session['places']}
        task=session['tasks'][session['index']];parts=task['parts']
        middle=parts[1:-1]
        region=middle[-1] if middle else ''
        district=', '.join(middle[:-1]) if len(middle)>1 else ''
        if len(middle)==1 and 'район' in middle[0].lower():district=region;region=''
        result=self.search.search(parts[0],parts[-1],region,district)
        if not result.get('candidates'):
            return {'ok':True,'reply':result['message']}
        session['search_token']=result['token']
        return {'ok':True,'reply':task['label']+'. '+result['message'],
                'location_choice':dict(result,token=token,time_known=bool(session['marker'].get('время')) if task['label']=='Место встречи дня рождения' else bool(task['birth_time']))}

    def choose(self,token,selected,kind):
        with self.lock:
            session=self.sessions.get(token) if isinstance(token,str) else None
            if not session or session['expires']<time.monotonic() or session['marker']['тип']!=kind:
                return {'ok':True,'reply':'Выбор места устарел. Повтори данные рождения.'}
            if session['busy']:return {'ok':True,'reply':'Подтверждение уже выполняется. Подожди его завершения.'}
            session['busy']=True
        try:
            task=session['tasks'][session['index']]
            result=self.search.confirm(session.get('search_token'),selected,task['date'],task['birth_time'])
            if result['status']!='confirmed':return {'ok':True,'reply':result['message']}
            c=next(c for c in self.search.sessions[session['search_token']]['candidates'] if c['id']==selected)
            session['places'].append(dict(latitude=result['latitude'],longitude=result['longitude'],timezone_name=result['timezone_name'],utc_offset=result['gmt'],address=result['address'],changes=c['changes']))
            session['index']+=1
            return self._next(token,session)
        finally:
            with self.lock:session['busy']=False


collection=Collection()
