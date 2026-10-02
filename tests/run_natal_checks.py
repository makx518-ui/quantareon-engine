"""Run release regression groups without network, payment, email or LLM calls."""
from pathlib import Path
import runpy
import sys
import unittest
import warnings
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'natal-test-deps')]
# Load its native dependencies before tests temporarily replace sys.modules.
import timezonefinder
warnings.simplefilter('ignore',ResourceWarning)
suite=unittest.TestSuite()
for name in ['test_natal_location.py','test_natal_export.py','test_natal_completion.py','test_natal_delivery.py',
             'test_natal_reading.py', 'test_machine_natal.py', 'test_natal_facts.py',
             'test_location_check.py', 'test_location_check_routes.py', 'test_location_collection.py']:
    ns=runpy.run_path(str(ROOT/'tests'/name),run_name='release_check')
    for obj in ns.values():
        if isinstance(obj,type) and issubclass(obj,unittest.TestCase):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(obj))
result=unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful(): sys.exit(1)
for filename in ['api/main.py','api/klassika_api.py','api_vhod.py','engine/natal_export.py',
                 'engine/chat_klassika.py','engine/chitatel.py','engine/storozh_faktov.py',
                 'engine/karta_html.py','engine/kosmogramma.py','engine/dispetcher.py','engine/natal_reading.py',
                 'engine/machine_natal.py', 'engine/natal_facts.py', 'api/location_check/collection.py',
                 'api/location_check/world_search.py','api/location_check/routes.py']:
    compile((ROOT/filename).read_text(encoding='utf-8-sig'),filename,'exec')
print('All changed Python modules compile')
