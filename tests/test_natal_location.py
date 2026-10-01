"""Input-path regression tests; no voice models or live app startup required.

Run: python -m unittest discover -s tests -v
Dependencies: pydantic, pytz, geopy (same versions as the application).
GeoNames fixtures are public responses captured on 2026-10-01.
"""
import ast
import asyncio
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parents[1]

class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail

def load_input_path():
    # Execute the production definitions, without unrelated startup imports.
    tree = ast.parse((ROOT / 'api/main.py').read_text(encoding='utf-8'))
    wanted = {'_COUNTRY_ISO', '_HISTORIC_COUNTRY', '_translit_ru', '_geo_admin_key',
              '_geonames_api_fuzzy', '_strip_place_prefix', '_normalize_country',
              '_addr_from_admin', '_admin_at', '_geocode_once', 'geocode',
              'tz_offset_at', 'NatalRequest', 'natal_chart', 'geocode_city', 'KerykeionRequest'}
    nodes = []
    for node in tree.body:
        name = getattr(node, 'name', None)
        if isinstance(node, ast.Assign):
            name = next((t.id for t in node.targets if isinstance(t, ast.Name)), None)
        if name in wanted:
            if hasattr(node, 'decorator_list'):
                node.decorator_list = []
            nodes.append(node)
    ns = dict(_os_geo=os, Optional=Optional, BaseModel=BaseModel, Field=Field,
              datetime=datetime, HTTPException=HTTPError, model_validator=model_validator)
    exec(compile(ast.Module(nodes, type_ignores=[]), 'api/main.py', 'exec'), ns)
    return ns

class Response:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return json.dumps(self.data).encode('utf-8')

class LocationTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_input_path()
        self.exact = json.loads((ROOT/'tests/fixtures/moscow-exact.json').read_text(encoding='utf-8-sig'))
        # Real geographic zone is present in FULL response; offline finder absent here.
        self.finder = types.SimpleNamespace(TimezoneFinder=lambda: types.SimpleNamespace(timezone_at=lambda **kw: 'Europe/Moscow'))

    def lookup(self, query='Москва, Россия', cc='RU', data=None):
        self.requests = []
        def reply(req, **kwargs):
            self.requests.append(req.full_url)
            return Response(data if data is not None else self.exact)
        with patch('urllib.request.urlopen', reply), patch.dict(sys.modules, timezonefinder=self.finder):
            return self.ns['_geonames_api_fuzzy'](query, cc)

    def test_moscow_capital_with_live_fixture(self):
        result = self.lookup()
        self.assertAlmostEqual(result['lat'], 55.75204)
        self.assertAlmostEqual(result['lng'], 37.61781)
        self.assertEqual(result['tz'], 'Europe/Moscow')
        self.assertIn('name_equals=', self.requests[0])
        self.assertIn('lang=ru', self.requests[0])

    def test_tver_only_when_region_explicit(self):
        result = self.lookup('Москва, Тверская область, Россия')
        self.assertAlmostEqual(result['lat'], 56.91775)

    def test_wrong_region_is_not_ignored(self):
        self.assertIsNone(self.lookup('Москва, Несуществующая область, Россия'))

    def test_foreign_country_is_rejected(self):
        self.assertIsNone(self.lookup(cc='US'))

    def test_similar_names_are_not_exact_names(self):
        data = {'geonames': [r for r in self.exact['geonames'] if r['toponymName'] == 'Moskovka']}
        self.assertIsNone(self.lookup(data=data))

    def test_iso_country(self):
        self.assertAlmostEqual(self.lookup('Москва, RU')['lat'], 55.75204)

    def test_city_name_is_not_mistaken_for_prefix(self):
        from urllib.parse import urlparse, parse_qs
        self.lookup('Городец, Россия', data={'geonames': []})
        self.assertEqual(parse_qs(urlparse(self.requests[0]).query)['name_equals'], ['Городец'])

    def test_bad_lookup_date_rejected_before_search(self):
        self.ns['geocode'] = lambda *args: self.fail('Invalid date reached geocoder')
        with self.assertRaises(HTTPError) as ctx:
            asyncio.run(self.ns['geocode_city']('Москва','Россия','1961-02-30'))
        self.assertEqual(ctx.exception.status_code, 400)

    def fallback(self, kind='city', region='Москва', country='ru', timezone_name='Europe/Moscow'):
        import geopy.geocoders
        loc=types.SimpleNamespace(latitude=55.75204,longitude=37.61781,address='Москва',
            raw={'addresstype':kind,'namedetails':{'name':'Москва'},
                 'address':{'city':'Москва','state':region,'country_code':country,'country':'Россия'}})
        self.ns['_geonames_api_fuzzy']=lambda *args, **kw:None
        finder=types.SimpleNamespace(TimezoneFinder=lambda:types.SimpleNamespace(timezone_at=lambda **kw:timezone_name))
        with patch.object(geopy.geocoders.Nominatim,'geocode',return_value=loc), patch.dict(sys.modules,timezonefinder=finder):
            return self.ns['_geocode_once']('Москва, Россия', expect_cc='RU')

    def test_nominatim_fallback_accepts_city(self):
        self.assertEqual(self.fallback()['latitude'],55.75204)

    def test_fallback_rejects_street_unknown_country_and_unknown_zone(self):
        for fields in ({'kind':'road'},{'country':''},{'timezone_name':None}):
            with self.subTest(fields=fields):self.assertIsNone(self.fallback(**fields))

    def test_no_silent_dropping_of_region(self):
        attempts = []
        def once(q, date, expect_cc):
            attempts.append(q)
            return None
        self.ns['_geocode_once'] = once
        self.assertIn('error', self.ns['geocode']('Москва, Тверская область', 'Россия'))
        self.assertTrue(all('Тверская область' in q for q in attempts))

    def test_unknown_country_is_not_worldwide_search(self):
        self.ns['_geocode_once'] = lambda *args, **kw: self.fail('Unconstrained lookup')
        self.assertIn('error', self.ns['geocode']('Москва', 'Неверная страна'))

    def test_reverse_address_is_fetched_once(self):
        found = self.lookup()
        self.ns['_geonames_api_fuzzy'] = lambda *args, **kw: found
        calls=[]
        self.ns['_admin_at'] = lambda *args: calls.append(args) or {'place': 'Москва'}
        self.assertEqual(self.ns['_geocode_once']('Москва, Россия', expect_cc='RU')['address'], 'Москва')
        self.assertEqual(len(calls), 1)

    def birth(self, **changes):
        fields = dict(year=1961, month=1, day=30, hour=12, minute=0,
                      latitude=55.75204, longitude=37.61781, timezone_str='Europe/Moscow')
        fields.update(changes)
        self.ns['calculate_natal'] = lambda **kw: kw
        return asyncio.run(self.ns['natal_chart'](self.ns['NatalRequest'](**fields)))

    def test_city_resolves_historical_birth_offset(self):
        dates=[]
        def geo(city, country, date):
            dates.append(date)
            return dict(latitude=55.75204, longitude=37.61781,
                        timezone_name='Europe/Moscow', utc_offset=99)
        self.ns['geocode']=geo
        result=self.birth(latitude=0, longitude=0, city='Москва', timezone_str=None)
        self.assertEqual(dates, ['1961-01-30'])
        self.assertEqual(result['timezone'], 3)

    def test_zone_uses_birth_hour_on_transition_day(self):
        result=self.birth(year=2026, month=3, day=8, hour=1, timezone_str='America/New_York')
        self.assertEqual(result['timezone'], -5)

    def test_nonexistent_and_ambiguous_local_times_rejected(self):
        for month, day, hour in [(3, 8, 2), (11, 1, 1)]:
            with self.subTest(month=month), self.assertRaises(HTTPError) as ctx:
                self.birth(year=2026, month=month, day=day, hour=hour, timezone_str='America/New_York')
            self.assertEqual(ctx.exception.status_code, 400)

    def test_bad_calendar_date_rejected(self):
        with self.assertRaises(HTTPError) as ctx: self.birth(month=2, day=30)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_fields_rejected(self):
        for field, value in [('latitude',91),('longitude',181),('hour',24),('minute',60),('second',60),('latitude',float('nan'))]:
            with self.subTest(field=field), self.assertRaises(ValidationError): self.birth(**{field:value})

    def test_unknown_zone_rejected(self):
        with self.assertRaises(HTTPError) as ctx: self.birth(timezone_str='Invalid/Zone')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_fractional_gmt_wheel_and_tables_use_same_moment(self):
        from datetime import timedelta
        for offset in (5.5,5.75,-3.5,-9.5):
            with self.subTest(offset=offset):
                model=self.ns['KerykeionRequest'](year=2000,month=1,day=1,hour=1,minute=20,second=15,
                    timezone_str=None,timezone=offset,latitude=55,longitude=37)
                expected=datetime(2000,1,1,1,20,15)-timedelta(hours=offset)
                self.assertEqual(datetime(model.year,model.month,model.day,model.hour,model.minute,model.second),expected)
                self.assertEqual(model.timezone_str,'UTC')
                self.assertEqual(model.timezone,0)

    def test_named_zone_keeps_birth_local_date(self):
        model=self.ns['KerykeionRequest'](year=2000,month=1,day=1,hour=1,
            timezone_str='Asia/Kolkata',timezone=5.5,latitude=28,longitude=77)
        self.assertEqual((model.year,model.month,model.day,model.hour),(2000,1,1,1))
        self.assertEqual(model.timezone_str,'Asia/Kolkata')

if __name__ == '__main__': unittest.main()
