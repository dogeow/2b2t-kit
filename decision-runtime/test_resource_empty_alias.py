import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from material_jobs.acquisition import _resource_ledger_scope_path,Unavailable


class EmptyResourceAliasTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.item='minecraft:oak_log'
        self.canonical=self.path('simpcraft.com');self.raw=self.path('simpcraft.com:25565')
    def path(self,server):
        key=hashlib.sha256((server+'|minecraft:overworld|'+self.item).encode()).hexdigest()[:20]
        return self.root/(key+'.json')
    def empty(self):
        return {'schema':1,'item':self.item,'tiles':{},'algorithm_version':2,
                'search_progress':{'new_tiles':0,'scanned_total':0,'has_more':True,
                                   'ledger':str(self.raw),'algorithm_version':2}}
    def populated(self):
        return {'schema':1,'item':self.item,'tiles':{'old-tile':{'state':'candidate','world_session':'old-world'}},
                'history':{'old-tile':[{'state':'empty_or_unsafe'}]},
                'route_failures':{'region':{'code':'guard_displaced','reason':'keep current hold',
                                          'observed_at':42,'world_session':'current-world'}}}
    def write(self,path,data):
        path.write_text(json.dumps(data));return path.read_bytes()
    def resolve(self):
        return _resource_ledger_scope_path(self.root,'simpcraft.com:25565','minecraft:overworld',self.item)
    def test_empty_port_alias_never_hides_populated_history_or_current_route_hold(self):
        actual=self.populated();old=self.write(self.canonical,actual);blank=self.write(self.raw,self.empty())
        self.assertEqual(self.canonical,self.resolve());self.assertEqual(actual,json.loads(self.canonical.read_text()))
        self.assertFalse(self.raw.exists());archive=next((self.root/'alias-reconciliations').iterdir())
        self.assertEqual(old,(archive/self.canonical.name).read_bytes());self.assertEqual(blank,(archive/self.raw.name).read_bytes())
        self.assertFalse(json.loads((archive/'reconciliation.json').read_text())['resource_observations_or_route_holds_removed'])
    def test_populated_port_alias_can_replace_empty_canonical_after_both_originals_saved(self):
        actual=self.populated();blank=self.write(self.canonical,self.empty());old=self.write(self.raw,actual)
        self.resolve();self.assertEqual(actual,json.loads(self.canonical.read_text()))
        archive=next((self.root/'alias-reconciliations').iterdir())
        self.assertEqual(blank,(archive/self.canonical.name).read_bytes());self.assertEqual(old,(archive/self.raw.name).read_bytes())
    def test_different_nonempty_records_are_preserved_and_rejected(self):
        a=self.populated();b=self.populated();b['tiles']={'another':{'state':'candidate'}}
        original=[self.write(self.canonical,a),self.write(self.raw,b)]
        with self.assertRaises(Unavailable):self.resolve()
        self.assertEqual(original,[self.canonical.read_bytes(),self.raw.read_bytes()])
    def test_zero_tiles_with_hold_unknown_metadata_or_nonzero_progress_is_not_empty(self):
        for patch in ({'guard_hold':{'world_session':'current-world'}},{'active_route':{'state':'uncertain'}},
                      {'surprise':True},{'search_progress':{'new_tiles':1,'scanned_total':0}}):
            with self.subTest(patch=patch):
                a=self.populated();b={**self.empty(),**patch}
                original=[self.write(self.canonical,a),self.write(self.raw,b)]
                with self.assertRaises(Unavailable):self.resolve()
                self.assertEqual(original,[self.canonical.read_bytes(),self.raw.read_bytes()])


if __name__=='__main__':unittest.main()
