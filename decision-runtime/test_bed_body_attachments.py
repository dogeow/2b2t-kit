import unittest
from village_beds import empty_bed_body

class BedBodyAttachmentsTest(unittest.TestCase):
    foot,head,stand=[5,64,10],[4,64,10],[6,64,10]
    def row(self,name,**kwargs):
        return dict(state='Block{minecraft:'+name+'}',passable=True,fluid=False,block_entity=False,**kwargs)
    def test_wall_buttons_above_bed_and_stand_do_not_block_their_empty_halves(self):
        rows={(4,65,10):self.row('cherry_button'),(6,65,10):self.row('stone_button')}
        self.assertTrue(empty_bed_body(rows,self.foot,self.head,self.stand))
    def test_floor_lever_can_share_standing_space(self):
        self.assertTrue(empty_bed_body({(6,64,10):self.row('lever')},self.foot,self.head,self.stand))
    def test_no_attachment_may_replace_a_bed_half(self):
        for cell in (self.foot,self.head):
            self.assertFalse(empty_bed_body({tuple(cell):self.row('lever')},self.foot,self.head,self.stand))
    def test_hazards_solids_and_unknown_passable_blocks_remain_rejected(self):
        for name in ('fire','water','cobblestone','sweet_berry_bush','redstone_wire'):
            self.assertFalse(empty_bed_body({(4,65,10):self.row(name)},self.foot,self.head,self.stand))
    def test_whitelisted_name_still_requires_all_collision_and_fluid_evidence(self):
        for key,value in [('passable',False),('fluid',True),('block_entity',True),('passable',None)]:
            row=self.row('lever');row[key]=value
            self.assertFalse(empty_bed_body({(6,64,10):row},self.foot,self.head,self.stand))

if __name__=='__main__':unittest.main()
