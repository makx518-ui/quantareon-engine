"""Isolated place-search prototype. Does not create orders or call reading models."""
import json, re, time, threading, secrets, unicodedata, math
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).parent
COUNTRIES = json.loads((ROOT/'countries.json').read_text(encoding='utf-8'))

def key(value):
    value=unicodedata.normalize('NFKC', str(value or '')).casefold().replace('ё','е')
    value=re.sub(r'\b(?:район|района|область|области|district|region|oblast|край)\b',' ',value)
    return ' '.join(re.sub(r'[^\w]+',' ',value).split())

def place_key(value):
    return key(re.sub(r'^(?:село|город|деревня|пос[её]лок|зерносовхоз|совхоз|с\.|г\.)\s+', '', str(value),flags=re.I))

def admin_key(value, cc=''):
    result=key(value).replace(' ','')
    if cc=='KZ' and result=='ско':return 'североказахстанская'
    return result

def search_address(request, cc):
    """Separate an explicitly supplied administrative suffix from the place name."""
    parts=[p.strip() for p in request['place'].split(',')]
    query=dict(request)
    query['place']=re.sub(r'^(?:(?:село|город|деревня|пос[её]лок|зерносовхоз|совхоз)\s+|(?:с\.|г\.)\s*)', '', parts[0],flags=re.I).strip()
    for suffix in parts[1:]:
        if not suffix:continue
        if COUNTRIES.get(suffix.casefold())==cc:continue
        if cc=='KZ' and admin_key(suffix,cc)=='североказахстанская':
            if query['region'] and admin_key(query['region'],cc)!=admin_key(suffix,cc):return None
            query['region']='Северо-Казахстанская область'
        elif any(query[field] and admin_key(suffix,cc)==admin_key(query[field],cc) for field in ('region','district')):continue
        else:return None
    return query if query['place'] else None

def coordinates(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
            return None
        return lat, lon
    except (ValueError,TypeError):return None

class Unavailable(Exception): pass

class Service:
    def __init__(self, transport=None):
        self.transport=transport or self._network
        self.cache={}; self.sessions={}; self.lock=threading.Lock(); self.osm_lock=threading.Lock(); self.next_osm=0

    def _network(self, source, params):
        base={'geonames':'https://secure.geonames.org/searchJSON',
              'reverse':'https://nominatim.openstreetmap.org/reverse',
              'search':'https://nominatim.openstreetmap.org/search'}[source]
        if source=='geonames':params=dict(params,username='vladm_oracle')
        cache_key=source+urlencode(sorted(params.items()))
        with self.lock:
            hit=self.cache.get(cache_key)
            if hit and hit[0]>time.monotonic():return hit[1]
        last=None
        for attempt in range(2):
            try:
                req=Request(base+'?'+urlencode(params),headers={'User-Agent':'QUANTAREON-location-check/1.0 (https://voice.quantareon.com/location-check)'})
                if source!='geonames':
                    # Serialize actual request starts, including concurrent users.
                    with self.osm_lock:
                        delay=max(0,self.next_osm-time.monotonic())
                        if delay:time.sleep(delay)
                        self.next_osm=time.monotonic()+1.1
                        with urlopen(req,timeout=8) as response:data=json.load(response)
                else:
                    with urlopen(req,timeout=8) as response:data=json.load(response)
                if isinstance(data,dict) and data.get('status'):raise Unavailable('provider_status')
                if source=='geonames' and (not isinstance(data,dict) or not isinstance(data.get('geonames'),list)):raise Unavailable('invalid_response')
                if source=='search' and not isinstance(data,list):raise Unavailable('invalid_response')
                if source=='reverse' and (not isinstance(data,dict) or not isinstance(data.get('address'),dict)):raise Unavailable('invalid_response')
                with self.lock:self.cache[cache_key]=(time.monotonic()+3600,data)
                return data
            except Exception as e:
                last=e
                if attempt==0:time.sleep(1.1)
        raise Unavailable(type(last).__name__)

    def search(self, place, country, region='', district=''):
        if any(not isinstance(v,str) or len(v)>300 for v in (place,country,region,district)):
            return dict(status='invalid',message='Поля адреса должны содержать текст длиной до 300 символов.')
        request=dict(place=str(place).strip(),country=str(country).strip(),region=str(region).strip(),district=str(district).strip())
        if not request['place']:return dict(status='invalid',message='Укажите населённый пункт.')
        cc=COUNTRIES.get(request['country'].casefold())
        if not cc:return dict(status='invalid',message='Страна не распознана. Выберите её из списка.')
        query_request=search_address(request,cc)
        if query_request is None:return dict(status='needs_detail',message='Не удалось согласовать части адреса в поле города с областью, районом и страной. Проверьте эти части; введённые данные сохранены.')
        warnings=[]; rows=[]; failed=False
        try:
            data=self.transport('geonames',dict(name_equals=query_request['place'],country=cc,lang='ru',style='FULL',featureClass='P',maxRows=100))
            for r in data.get('geonames',[]):
                if not isinstance(r,dict):failed=True;continue
                names=[r.get('name'),r.get('toponymName'),r.get('asciiName')]+[a.get('name') for a in r.get('alternateNames',[]) if isinstance(a,dict) and a.get('lang')!='link']
                if r.get('countryCode')==cc and place_key(query_request['place']) in {place_key(n) for n in names if n}:
                    rows.append(r)
            if data.get('totalResultsCount',0)>100:
                return dict(status='needs_detail',message='Совпадений слишком много. Укажите область или район; выбор ещё не сделан.')
        except Unavailable:
            failed=True;warnings.append('Основной справочник не ответил; использован запасной поиск.')
        candidates=[]
        if query_request['region']:
            matching=[r for r in rows if admin_key(r.get('adminName1'),cc)==admin_key(query_request['region'],cc)]
            # Keep all when an administrative name may be historical; never silently choose one.
            if matching:rows=matching
        if len(rows)>8:
            return dict(status='needs_detail',message='Найдено много одноимённых мест. Укажите область, чтобы сузить выбор.')
        for r in rows:
            coords=coordinates(r.get('lat'),r.get('lng'))
            if coords is None:failed=True;continue
            lat,lon=coords
            admin=dict(place=r.get('name') or r.get('toponymName'),district=r.get('adminName2') or '',region=r.get('adminName1') or '',country=r.get('countryName') or request['country'])
            if not admin['district'] or request['district'] or request['region']:
                try:
                    reverse=self.transport('reverse',dict(lat=lat,lon=lon,format='jsonv2',addressdetails=1,zoom=13,**{'accept-language':'ru'}))
                    a=reverse.get('address') or {}
                    # Reverse lookup supplies administrative labels, never replaces the exact village name.
                    if a.get('country_code','').upper()==cc:
                        admin.update(district=a.get('county') or admin['district'],region=a.get('state') or a.get('region') or admin['region'])
                except Unavailable:
                    warnings.append('Не удалось дополнительно проверить район этой находки.')
            candidates.append(dict(latitude=lat,longitude=lon,admin=admin,source='GeoNames',geoname_id=r.get('geonameId'),country_code=cc))
        if not candidates:
            query=', '.join(v for v in (query_request['place'],query_request['district'],query_request['region'],query_request['country']) if v)
            try:
                data=self.transport('search',dict(q=query,format='jsonv2',addressdetails=1,namedetails=1,countrycodes=cc.lower(),limit=8,**{'accept-language':'ru'}))
                if len(data)>=8:
                    return dict(status='needs_detail',message='Запасной поиск достиг предела выдачи. Укажите область или район, чтобы проверить место точнее.')
                for r in data:
                    if not isinstance(r,dict):failed=True;continue
                    a=r.get('address') or {}; named=r.get('namedetails') or {}
                    names=[r.get('name')]+list(named.values())+[a.get(k) for k in ('city','town','village','hamlet')]
                    names=[n for value in names if isinstance(value,str) for n in value.split(';')]
                    if a.get('country_code','').upper()!=cc or r.get('addresstype') not in ('city','town','village','hamlet','municipality'):continue
                    if place_key(query_request['place']) not in {place_key(n) for n in names}:continue
                    coords=coordinates(r.get('lat'),r.get('lon'))
                    if coords is None:failed=True;continue
                    candidates.append(dict(latitude=coords[0],longitude=coords[1],source='OpenStreetMap',country_code=cc,
                        admin=dict(place=r.get('name') or request['place'],district=a.get('county') or '',region=a.get('state') or a.get('region') or '',country=a.get('country') or request['country'])))
                if not candidates and failed:return dict(status='unavailable',message='Один из справочников недоступен. Поиск не завершён; данные сохранены, попробуйте повторить.')
            except Unavailable:
                return dict(status='unavailable',message='Не удалось завершить проверку места из-за связи с картами. Введённые данные сохранены; повторите поиск.')
        if not candidates:return dict(status='not_found',message='Совпадение не найдено. Проверьте написание или укажите ближайший город; данные сохранены.')
        if request['district']:
            matched=[c for c in candidates if key(c['admin']['district'])==key(request['district'])]
            if matched:candidates=matched
        seen=set(); unique=[]
        for c in candidates:
            k=(round(c['latitude'],4),round(c['longitude'],4))
            if k not in seen:seen.add(k);unique.append(c)
        for c in unique:
            c['address']=' · '.join(v for v in c['admin'].values() if v)
            c['changes']=[]
            for field,label in [('place','населённый пункт'),('district','район'),('region','область')]:
                was=query_request[field] if field=='place' else request[field];now=c['admin'][field]
                normalize=place_key if field=='place' else lambda value:admin_key(value,cc)
                if was and normalize(was)!=normalize(now):
                    c['changes'].append(f'Вы указали {label}: «{was}». '+
                        (f'В нынешнем адресе найденного места {label} указан как «{now}». Поэтому адрес отличается от введённого. Подтвердите, что это ваше место рождения. Историческое переименование пока не подтверждено.' if now else 'Справочник не подтвердил нынешнее название этой территории. Требуется ваша проверка места.'))
            c['id']=secrets.token_urlsafe(12)
        token=secrets.token_urlsafe(20)
        with self.lock:
            self.sessions={k:v for k,v in self.sessions.items() if v['expires']>time.monotonic()}
            self.sessions[token]=dict(request=request,candidates=unique,expires=time.monotonic()+3600)
        return dict(status='ambiguous' if len(unique)>1 else 'confirmation',request=request,token=token,candidates=unique,warnings=list(dict.fromkeys(warnings)),
            message='Найдено несколько мест. Выберите своё и подтвердите.' if len(unique)>1 else 'Место найдено. Проверьте адрес и подтвердите.')

    def confirm(self, token, selected, date, birth_time):
        if not all(isinstance(v,str) for v in (token,selected,date,birth_time)):
            return dict(status='invalid',message='Проверьте данные подтверждения.')
        with self.lock:session=self.sessions.get(token)
        if not session or session['expires']<time.monotonic():return dict(status='invalid',message='Поиск устарел. Найдите место ещё раз.')
        candidate=next((c for c in session['candidates'] if c['id']==selected),None)
        if not candidate:return dict(status='invalid',message='Выберите найденное место.')
        try:
            from datetime import datetime
            import pytz
            from timezonefinder import TimezoneFinder
            local=datetime.strptime(date+' '+(birth_time or '12:00'),'%Y-%m-%d %H:%M:%S' if birth_time.count(':')==2 else '%Y-%m-%d %H:%M')
            zone=TimezoneFinder().timezone_at(lat=candidate['latitude'],lng=candidate['longitude'])
            if not zone:raise ValueError('timezone')
            offset=pytz.timezone(zone).localize(local,is_dst=None).utcoffset().total_seconds()/3600
        except Exception:
            return dict(status='invalid',message='Не удалось однозначно подтвердить дату, время или исторический часовой пояс. Расчёт остановлен.')
        return dict(status='confirmed',original_address=session['request'],address=candidate['address'],latitude=candidate['latitude'],longitude=candidate['longitude'],timezone_name=zone,gmt=offset,gmt_reference_time=birth_time or '12:00',date=date,birth_time=birth_time or None,time_known=bool(birth_time),
            message='Место подтверждено. Эти координаты можно передать в расчёт. В песочнице заказ и карта не создаются.')
