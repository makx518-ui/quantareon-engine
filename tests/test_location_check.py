import unittest
import io,json,time
from unittest.mock import patch
from api.location_check.world_search import Service, COUNTRIES, Unavailable

def row(name='Советское',lon='70.34393',cc='KZ'):
    return dict(name=name,toponymName=name,lat='54.42957',lng=lon,countryCode=cc,countryName='Казахстан',adminName1='Северо-Казахстанская область',geonameId=int(float(lon)*100),alternateNames=[])
def transport(source,params):
    if source=='geonames':return {'geonames':[row(),row(lon='68.41623')]}
    if source=='reverse':return {'address':dict(country_code='kz',county='район Магжана Жумабаева' if params['lon']>70 else 'Есильский район',state='Северо-Казахстанская область',village='Соседняя подпись')}
    return []

class Tests(unittest.TestCase):
    def test_full_country_registry(self):
        self.assertEqual(len(set(COUNTRIES.values())),250)
        for name,cc in [('Гренландия','GL'),('шпицберген','SJ'),('japan','JP')]:self.assertEqual(COUNTRIES[name.casefold()],cc)
    def test_modern_district_selects_only_correct_place(self):
        r=Service(transport).search('Советское','Казахстан','Северо-Казахстанская область','район Магжана Жумабаева')
        self.assertEqual(r['status'],'confirmation');self.assertEqual(len(r['candidates']),1)
        self.assertEqual(r['candidates'][0]['longitude'],70.34393)
        self.assertEqual(r['candidates'][0]['changes'],[])
    def test_old_district_is_explained_and_requires_choice(self):
        r=Service(transport).search('Советское','Казахстан','Северо-Казахстанская область','Возвышенский район')
        self.assertEqual(r['status'],'ambiguous')
        self.assertEqual(len(r['candidates']),2)
        text=r['candidates'][0]['changes'][0]
        self.assertIn('Возвышенский',text);self.assertIn('Магжана Жумабаева',text)
        self.assertIn('пока не подтверждено',text)
    def test_reverse_cannot_replace_village_name(self):
        r=Service(transport).search('Советское','KZ')
        self.assertTrue(all(c['admin']['place']=='Советское' for c in r['candidates']))
    def test_provider_failure_is_not_not_found(self):
        def fail(*a):raise Unavailable()
        self.assertEqual(Service(fail).search('Hallstatt','AT')['status'],'unavailable')
    def test_empty_result_is_not_network_failure(self):
        def empty(source,params):return {'geonames':[]} if source=='geonames' else []
        self.assertEqual(Service(empty).search('Несуществующее село','RU')['status'],'not_found')
    def test_foreign_country_never_becomes_candidate(self):
        def foreign(source,params):return {'geonames':[row(cc='RU')]} if source=='geonames' else []
        self.assertEqual(Service(foreign).search('Советское','KZ')['status'],'not_found')
    def test_tampered_confirmation_rejected(self):
        s=Service(transport);r=s.search('Советское','KZ')
        self.assertEqual(s.confirm(r['token'],'forged','1961-01-30','21:00')['status'],'invalid')
        self.assertEqual(s.confirm('forged','forged','1961-01-30','21:00')['status'],'invalid')
    def test_confirmed_choice_preserves_original_and_coordinates(self):
        s=Service(transport);r=s.search('Советское','KZ','','Возвышенский район')
        d=s.confirm(r['token'],r['candidates'][0]['id'],'1961-01-30','21:00')
        self.assertEqual(d['status'],'confirmed');self.assertEqual(d['gmt'],6)
        self.assertEqual(d['original_address']['district'],'Возвышенский район')
    def test_unknown_time_remains_unknown(self):
        s=Service(transport);r=s.search('Советское','KZ')
        d=s.confirm(r['token'],r['candidates'][0]['id'],'1961-01-30','')
        self.assertFalse(d['time_known'])
    def test_bad_date_cannot_confirm(self):
        s=Service(transport);r=s.search('Советское','KZ')
        d=s.confirm(r['token'],r['candidates'][0]['id'],'1961-02-30','21:00')
        self.assertEqual(d['status'],'invalid')
    def test_temporary_failure_retries_and_then_caches_success(self):
        s=Service()
        with patch('api.location_check.world_search.urlopen',side_effect=[TimeoutError(),io.BytesIO(json.dumps({'geonames':[]}).encode())]) as network,patch('api.location_check.world_search.time.sleep'):
            first=s._network('geonames',{'name_equals':'Hallstatt','country':'AT'})
            second=s._network('geonames',{'name_equals':'Hallstatt','country':'AT'})
            self.assertEqual(first,second);self.assertEqual(network.call_count,2)
    def test_failure_is_not_cached(self):
        s=Service()
        with patch('api.location_check.world_search.urlopen',side_effect=TimeoutError()) as network,patch('api.location_check.world_search.time.sleep'):
            for _ in range(2):
                with self.assertRaises(Unavailable):s._network('geonames',{'name_equals':'Hallstatt'})
            self.assertEqual(network.call_count,4)
    def test_expired_confirmation_rejected(self):
        s=Service(transport);r=s.search('Советское','KZ')
        s.sessions[r['token']]['expires']=0
        self.assertEqual(s.confirm(r['token'],r['candidates'][0]['id'],'1961-01-30','21:00')['status'],'invalid')
    def test_invalid_provider_coordinates_never_become_candidates(self):
        for invalid in ['NaN','Infinity','91','broken']:
            def bad(source,params):
                if source=='geonames':return {'geonames':[dict(row(),lat=invalid)]}
                return []
            self.assertEqual(Service(bad).search('Советское','KZ')['status'],'unavailable')
    def test_invalid_input_and_confirmation_shapes(self):
        s=Service(transport)
        for value in [None,{},'x'*301]:self.assertEqual(s.search(value,'KZ')['status'],'invalid')
        self.assertEqual(s.confirm({},[],None,None)['status'],'invalid')
    def test_oversized_candidate_list_never_silently_chooses(self):
        def many(source,params):return {'geonames':[row()]*101,'totalResultsCount':101}
        self.assertEqual(Service(many).search('Советское','KZ')['status'],'needs_detail')
    def test_historical_place_alias_is_matched_in_backup(self):
        def historical(source,params):
            if source=='geonames':return {'geonames':[]}
            return [dict(lat='54.4',lon='70.3',name='Советское',addresstype='village',
                         namedetails={'old_name':'Старое;Советский'},address={'country_code':'kz','village':'Советское'})]
        r=Service(historical).search('Советский','KZ')
        self.assertEqual(r['status'],'confirmation')
        self.assertEqual(r['candidates'][0]['admin']['place'],'Советское')
        self.assertIn('Советский',r['candidates'][0]['changes'][0])
        self.assertIn('Советское',r['candidates'][0]['changes'][0])
    def test_backup_limit_requires_detail(self):
        def capped(source,params):
            return {'geonames':[]} if source=='geonames' else [{}]*8
        self.assertEqual(Service(capped).search('Советское','KZ')['status'],'needs_detail')
    def test_unknown_birth_time_has_explicit_reference_time(self):
        s=Service(transport);r=s.search('Советское','KZ')
        d=s.confirm(r['token'],r['candidates'][0]['id'],'1961-01-30','')
        self.assertEqual(d['gmt_reference_time'],'12:00');self.assertIsNone(d['birth_time'])
    def test_osm_request_starts_are_limited(self):
        s=Service();starts=[]
        def reply(*args,**kwargs):
            starts.append(time.monotonic());return io.BytesIO(b'[]')
        with patch('api.location_check.world_search.urlopen',side_effect=reply):
            s._network('search',{'q':'first'});s._network('search',{'q':'second'})
        self.assertGreaterEqual(starts[1]-starts[0],1.0)

if __name__=='__main__':unittest.main()
