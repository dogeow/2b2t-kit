import unittest
from storage_stack_identity import visible_key

class StorageIdentityTest(unittest.TestCase):
    def test_only_witnessed_empty_container_normalizes(self):
        nested={'item':'minecraft:dropper','count':20,'max_stack':64}
        full={**nested,'contains':[]}
        self.assertNotEqual(visible_key(nested),visible_key(full))
        self.assertEqual(visible_key(nested,witnessed_empty_items=['minecraft:dropper']),visible_key(full,witnessed_empty_items=['minecraft:dropper']))
    def test_nonempty_or_other_components_never_disappear(self):
        base={'item':'minecraft:dropper','count':1,'max_stack':64}
        for extra in ({'contains':[{'item':'minecraft:diamond','count':1}]},{'contains':[],'custom_name':'keep'}):
            self.assertNotEqual(visible_key(base,witnessed_empty_items=['minecraft:dropper']),visible_key({**base,**extra},witnessed_empty_items=['minecraft:dropper']))
    def test_unrelated_container_empty_content_still_distinct(self):
        base={'item':'minecraft:chest','count':1}
        self.assertNotEqual(visible_key(base,witnessed_empty_items=['minecraft:dropper']),visible_key({**base,'contains':[]},witnessed_empty_items=['minecraft:dropper']))
if __name__=='__main__':unittest.main()
