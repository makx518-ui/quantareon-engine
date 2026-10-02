import asyncio
import unittest
from api.location_check.collection import Collection
from api.location_check.world_search import Service, Unavailable

def lookup(source,params):
    if source=='geonames':return {'geonames':[
        dict(name='Советское',lat='54.42957',lng='70.34393',countryCode='KZ',countryName='Казахстан',adminName1='Северо-Казахстанская область',adminName2='район Магжана Жумабаева'),
        dict(name='Советское',lat='54.04392',lng='68.41623',countryCode='KZ',countryName='Казахстан',adminName1='Северо-Казахстанская область',adminName2='Есильский район')]}
    if source=='reverse':return {'address':{'country_code':'kz','county':'район Магжана Жумабаева' if params['lon']>70 else 'Есильский район','state':'Северо-Казахстанская область'}}
    return []

MARKER={'тип':'натал','дата':'30.01.1961','время':'20:56:00','место':'Советское / Возвышенский район / Северо-Казахстанская область / Казахстан','пол':'M'}

class CollectionTests(unittest.TestCase):
    def setUp(self):self.c=Collection(Service(lookup))
    def choose(self,r,kind='натал'):
        choice=r['location_choice'];return self.c.choose(choice['token'],choice['candidates'][0]['id'],kind)
    def test_old_district_requires_choice_then_uses_selected_coordinates(self):
        r=self.c.start(MARKER)
        self.assertNotIn('dannye',r);self.assertEqual(len(r['location_choice']['candidates']),2)
        result=self.choose(r)
        geo=result['_places'][0]
        self.assertEqual(geo['longitude'],70.34393);self.assertEqual(geo['utc_offset'],6)
        self.assertIn('Возвышенский',geo['changes'][0])
        self.assertEqual(result['_ready'],MARKER)
    def test_wrong_or_replayed_selection_does_not_advance(self):
        r=self.c.start(MARKER);token=r['location_choice']['token']
        self.assertNotIn('_ready',self.c.choose(token,'forged','натал'))
        self.assertNotIn('_ready',self.c.choose(token,r['location_choice']['candidates'][0]['id'],'соляр'))
        self.assertIn('_ready',self.choose(r))
        self.assertNotIn('_ready',self.choose(r))
    def test_expired_session(self):
        r=self.c.start(MARKER);self.c.sessions[r['location_choice']['token']]['expires']=0
        self.assertNotIn('_ready',self.choose(r))
    def test_synastry_requires_both_confirmations(self):
        r=self.c.start({'тип':'синастрия','первый':MARKER,'второй':dict(MARKER,время=None)})
        r2=self.choose(r,'синастрия');self.assertIn('location_choice',r2)
        self.assertFalse(r2['location_choice']['time_known'])
        self.assertIn('_ready',self.choose(r2,'синастрия'))
    def test_solar_requires_current_place_confirmation(self):
        r=self.c.start(dict(MARKER,тип='соляр',текущее_место=MARKER['место']))
        r2=self.choose(r,'соляр');self.assertIn('location_choice',r2)
        self.assertIn('_ready',self.choose(r2,'соляр'))
    def test_identical_names_can_keep_different_selected_villages(self):
        r=self.c.start({'тип':'синастрия','первый':MARKER,'второй':MARKER})
        r2=self.choose(r,'синастрия');choice=r2['location_choice']
        result=self.c.choose(choice['token'],choice['candidates'][1]['id'],'синастрия')
        self.assertEqual([g['longitude'] for g in result['_places']],[70.34393,68.41623])
        from api.klassika_api import _собрать_dannye
        data=asyncio.run(_собрать_dannye(result['_ready'],result['_places']))
        self.assertEqual(data['первый']['_dolgota'],70.34393)
        self.assertEqual(data['второй']['_dolgota'],68.41623)
    def test_network_failure_is_explained(self):
        def fail(*a):raise Unavailable()
        r=Collection(Service(fail)).start(MARKER)
        self.assertNotIn('location_choice',r);self.assertIn('связи',r['reply'])
    def test_invalid_date_and_country_stop_before_ready(self):
        self.assertNotIn('location_choice',self.c.start(dict(MARKER,дата='30.02.1961')))
        self.assertNotIn('location_choice',self.c.start(dict(MARKER,место='Советское')))

if __name__=='__main__':unittest.main()
