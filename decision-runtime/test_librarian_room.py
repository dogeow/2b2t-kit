import unittest
from librarian_room import LibrarianRoom

class Tests(unittest.TestCase):
    def room(self,name,x):
        return LibrarianRoom.from_slot({'id':name,'occupant_uuid':name,'work_block':[x,65,797813 if name[1]=='S'else 797809]})
    def test_public_pose_keeps_body_outside_cap_and_eye_in_trade_window(self):
        for name in ('ES06','EN02'):
            room=self.room(name,761028);p=room.public_pose();x,y,z=room.work
            self.assertTrue(y+1.5 < p[1]+1.62 < y+2)
            if room.inward==1:self.assertLess(p[2]+.3,z)
            else:self.assertGreater(p[2]-.3,z+1)
            self.assertEqual('north'if room.inward==1 else'south',room.public_mining_face())
    def test_closed_top_trapdoor_keeps_adult_barrier(self):
        room=self.room('ES06',761028);x,y,z=room.work
        state='Block{minecraft:oak_trapdoor}[facing=north,half=top,open=false,powered=true,waterlogged=false]'
        rows={(x,y+1,z):{'state':state},(x,y+2,z):{'solid':True}}
        room.require_caps(rows)
        for old,new in [('open=false','open=true'),('half=top','half=bottom'),('waterlogged=false','waterlogged=true')]:
            rows[(x,y+1,z)]['state']=state.replace(old,new)
            with self.assertRaises(ValueError):room.require_caps(rows)
    def test_trade_pose_keeps_full_body_outside_both_counter_faces(self):
        for name in ('WS03','WN03','ES06','EN02'):
            room=self.room(name,761004);p=room.public_trade_pose();x,y,z=room.work
            self.assertEqual(x+.5,p[0])
            self.assertTrue(y+1.5 < p[1]+1.62 < y+2)
            clearance=z-(p[2]+.3) if room.inward==1 else p[2]-.3-(z+1)
            self.assertAlmostEqual(.005,clearance,places=7)
    def test_print_pose_uses_verified_public_height_and_distance(self):
        self.assertEqual([761004.5,65.3,797811.5],self.room('WN02',761004).public_print_pose())
        self.assertEqual([761004.5,65.3,797811.5],self.room('ES06',761004).public_print_pose())
    def test_raised_workpoint_does_not_raise_floor_roof_or_player_into_ceiling(self):
        room=LibrarianRoom.from_slot({'id':'WN02','occupant_uuid':'v','work_block':[761002,64,797809],
            'actual_work_block':[761002,65,797809],'interior_floor_y':64,'bed_head':[761002,64,797808]})
        self.assertEqual(64,room.floor_y)
        self.assertEqual([761002,67,797808],room.private_roof())
        self.assertEqual([761002.5,65.1,797811.5],room.public_print_pose())
        self.assertLess(room.public_print_pose()[1]+1.8,67)
        self.assertEqual([761002.5,65.1,797808.69],room.operator_pose())
        self.assertEqual(([761001,63,797805],[761003,67,797809]),room.bounds())
    def test_inconsistent_floor_metadata_is_rejected_before_planning(self):
        for floor in (63,66,True):
            with self.subTest(floor=floor),self.assertRaises(ValueError):
                LibrarianRoom.from_slot({'id':'WN02','occupant_uuid':'v','work_block':[0,65,1],'interior_floor_y':floor})
    def test_open_north_south_panel_requires_present_workstation(self):
        room=self.room('ES06',761028);x,y,z=room.work
        panel='Block{minecraft:oak_trapdoor}[facing=north,half=top,open=true,powered=false,waterlogged=false]'
        rows={(x,y+1,z):{'state':panel},(x,y+2,z):{'solid':True},(x,y,z):{'state':room.lectern_state()}}
        room.require_caps(rows)
        rows[(x,y+1,z)]['state']=panel.replace('facing=north','facing=east')
        with self.assertRaises(ValueError):room.require_caps(rows)
        rows[(x,y+1,z)]['state']=panel;del rows[(x,y,z)]
        with self.assertRaises(ValueError):room.require_caps(rows)
    def test_farther_stalls_do_not_reuse_the_old_stalls_scan_bounds(self):
        self.assertEqual(([761025,64,797813],[761027,68,797817]),self.room('ES05',761026).bounds())
        self.assertEqual(([761027,64,797813],[761029,68,797817]),self.room('ES06',761028).bounds())
        self.assertEqual(([761021,64,797813],[761023,68,797817]),self.room('ES03',761022).bounds())
    def test_north_room_is_scanned_toward_its_private_bed(self):
        self.assertEqual(([761019,64,797805],[761021,68,797809]),self.room('EN02',761020).bounds())
        north=self.room('EN02',761020);south=self.room('ES06',761028)
        self.assertEqual([761020,68,797808],north.private_roof())
        self.assertEqual([761028,66,797815],south.barrier())
        self.assertAlmostEqual(797808.69,north.operator_pose()[2])
        self.assertAlmostEqual(797814.31,south.operator_pose()[2])
        self.assertEqual(67.7,south.private_center(2.7)[1])
    def test_neighbour_or_injured_resident_is_never_accepted(self):
        room=self.room('ES05',761026);v={'uuid':'ES05','type':'minecraft:villager','health':20,'is_baby':False}
        self.assertEqual(v,room.actor({'scan_entities':[v]}))
        for mutation in ({'uuid':'ES03'},{'health':19},{'is_baby':True}):
            with self.assertRaises(ValueError):room.actor({'scan_entities':[dict(v,**mutation)]})
    def test_cap_check_uses_the_actual_work_block(self):
        room=self.room('ES05',761026);rows={(761026,66,797813):{'state':'Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'},(761026,67,797813):{'solid':True}}
        room.require_caps(rows)
        with self.assertRaises(ValueError):self.room('ES03',761022).require_caps(rows)

    def test_private_workstation_does_not_move_public_access_inside_the_cell(self):
        room=LibrarianRoom.from_slot({'id':'WS01','occupant_uuid':'v',
            'work_block':[761000,64,797813],'actual_work_block':[761000,64,797816]})
        self.assertEqual([761000.5,64.1,797812.695],room.public_trade_pose())
        self.assertEqual([761000.5,64.3,797811.5],room.public_print_pose())
        self.assertEqual((761000,64,797816),room.work)
        self.assertLessEqual(room.bounds()[0][2],797813)
        with self.assertRaises(ValueError):
            room.require_caps({(761000,65,797813):{'state':'Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'},
                               (761000,66,797813):{'solid':True}})

    def test_invalid_public_counter_axis_is_rejected(self):
        for actual in ([2,64,3],[1,64,1],[1,64,8]):
            with self.subTest(actual=actual),self.assertRaises(ValueError):
                LibrarianRoom.from_slot({'id':'WS01','occupant_uuid':'v',
                    'work_block':[1,64,2],'actual_work_block':actual})

if __name__=='__main__':unittest.main()

class InsetPublicAccessTests(unittest.TestCase):
 def test_scan_bounds_include_both_columns_and_their_outer_walls(self):
  for offsets,lo,hi in [([-1,0],98,101),([0,1],99,102)]:
   r=LibrarianRoom.from_slot({'id':'WN11','occupant_uuid':'v','work_block':[100,65,100],'interior_x_offsets':offsets})
   self.assertEqual((lo,hi),(r.bounds()[0][0],r.bounds()[1][0]))
 def test_invalid_columns_are_rejected_in_direct_and_slot_construction(self):
  for offsets in [(),(1,),(-1,1),(0,0),(0,True),(-1,0,1)]:
   with self.subTest(offsets=offsets),self.assertRaises(ValueError):
    LibrarianRoom('v',(100,65,100),-1,interior_x_offsets=offsets)
   with self.subTest(offsets=offsets),self.assertRaises(ValueError):
    LibrarianRoom.from_slot({'id':'WN11','occupant_uuid':'v','work_block':[100,65,100],'interior_x_offsets':list(offsets)})
 def test_public_route_hook_can_handle_or_decline_a_room(self):
  from types import SimpleNamespace
  from librarian_room import walk_public
  r=LibrarianRoom('v',(761004,64,797809),-1)
  calls=[];c=SimpleNamespace(walk_librarian_public=lambda room:True)
  walk_public(c,r)
  c.walk_librarian_public=lambda room:False
  c.check=lambda:{'pos':[761004.5,64.,797811.5]}
  c.n=lambda op,**params:calls.append((op,params))
  walk_public(c,r)
  self.assertEqual('walk',calls[-1][0]);self.assertEqual([r.public_pose()[0],64.,r.public_pose()[2]],calls[-1][1]['target'])
 def test_inset_quote_position_stays_low_beneath_old_cap_and_clear_of_new_workpoint(self):
  for name,actual in [('ES03',[10,65,14]),('EN03',[10,65,12])]:
   r=LibrarianRoom.from_slot({'id':name,'occupant_uuid':'v','work_block':[10,65,13],'actual_work_block':actual,'interior_depth':2})
   p=r.public_pose();t=r.public_trade_pose();self.assertEqual(p[1],65.);self.assertLess(p[1]+1.8,66.8125)
   self.assertAlmostEqual(abs(t[2]-(actual[2]+.5)),.805);self.assertGreater(abs(t[2]-(actual[2]+.5))-.3,.5)
   self.assertAlmostEqual(abs(r.public_print_pose()[2]-(actual[2]+.5)),2.)
 def test_original_three_cell_private_offset_keeps_its_existing_external_access(self):
  r=LibrarianRoom.from_slot({'id':'WS01','occupant_uuid':'v','work_block':[10,64,13],'actual_work_block':[10,64,16]})
  self.assertEqual(r.public_pose(),[10.5,64.1,12.5])

class SingleCellRoomTests(unittest.TestCase):
 def test_explicit_single_cell_has_only_one_private_cell_and_original_public_face(self):
  r=LibrarianRoom.from_slot({'id':'WN10','occupant_uuid':'v','work_block':[100,64,100],'interior_depth':1})
  self.assertEqual(([99,63,98],[101,67,100]),r.bounds());self.assertEqual([100.5,64.1,101.5],r.public_pose())
 def test_invalid_depths_cannot_shrink_the_enclosure_to_nothing(self):
  for depth in [0,True,-1,4]:
   with self.assertRaises(ValueError):LibrarianRoom.from_slot({'id':'WN10','occupant_uuid':'v','work_block':[100,64,100],'interior_depth':depth})
