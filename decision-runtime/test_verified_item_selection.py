import copy,unittest
from verified_item_selection import correction_slot

class VerifiedItemSelectionTest(unittest.TestCase):
    def frames(self):
        r=dict(id='selected',phase='done',world_session='w',control_revision=4,
               supervision_lease=dict(kind='materials',job_session='t'),health=20,
               manual_movement=False,screen='',pos=[1,64,1],inventory=[dict(slot=5,item='minecraft:dark_oak_planks',count=3)],
               menu=dict(id=0,cursor=dict(item='minecraft:air')))
        return r,dict(copy.deepcopy(r),last_request='selected')
    def test_only_existing_hotbar_slot_is_corrected(self):
        r,s=self.frames();self.assertEqual(correction_slot(r,s,'minecraft:dark_oak_planks'),5)
        for frame in (r,s):frame['inventory'][0]['slot']=12
        self.assertIsNone(correction_slot(r,s,'minecraft:dark_oak_planks'))
    def test_unknown_scope_or_physical_changes_do_not_repeat_selection(self):
        for key,value in [('phase','waiting'),('world_session','other'),('control_revision',5),('pos',[2,64,1])]:
            r,s=self.frames();r[key]=value
            with self.subTest(key=key):self.assertIsNone(correction_slot(r,s,'minecraft:dark_oak_planks'))
        for change in [dict(manual_movement=True),dict(health=19),dict(screen='InventoryScreen'),dict(navigating=True),dict(supervision_lease={})]:
            r,s=self.frames();s.update(change)
            self.assertIsNone(correction_slot(r,s,'minecraft:dark_oak_planks'))
    def test_inventory_or_cursor_changes_are_not_hidden(self):
        r,s=self.frames();s['inventory'][0]['count']=2;self.assertIsNone(correction_slot(r,s,'minecraft:dark_oak_planks'))
        r,s=self.frames();s['menu']['cursor']['item']='minecraft:diamond';self.assertIsNone(correction_slot(r,s,'minecraft:dark_oak_planks'))

if __name__=='__main__':unittest.main()
