import unittest
from material_jobs.renewable_tree_site import choose


def volume():
    return {'complete':True,'min':[-12,59,-12],'max':[12,104,12],
            'blocks':[{'pos':[x,63,z],'state':'Block{minecraft:grass_block}[snowy=false]',
                       'solid':True,'fluid':False,'block_entity':False}
                      for x in range(-12,13)for z in range(-12,13)]}


class TreeSiteTests(unittest.TestCase):
    def test_planting_uses_existing_dry_soil_and_keeps_the_whole_harvest_halo_observed(self):
        v=volume();site=choose(v,[.5,65,.5]);self.assertEqual([0,64,0],site['root'])
        self.assertFalse(site['clearing_required']);self.assertTrue(site['stances'])
        self.assertTrue(all(v['min'][i]<=site['harvest_bounds']['min'][i]<=site['harvest_bounds']['max'][i]<=v['max'][i]for i in range(3)))
    def test_structures_crops_containers_and_crown_obstructions_prevent_planting(self):
        for state,entity in [('Block{minecraft:stone_bricks}',False),('Block{minecraft:wheat}[age=7]',False),
                             ('Block{minecraft:barrel}[facing=up,open=false]',True),('Block{minecraft:stone}',False)]:
            v=volume();v['blocks'].append({'pos':[0,65,0],'state':state,'fluid':False,'block_entity':entity})
            site=choose(v,[.5,65,.5])
            if state=='Block{minecraft:stone}':
                self.assertIsNotNone(site);self.assertNotEqual([0,64,0],site['root'])
            else:self.assertIsNone(site)
    def test_reserved_project_and_partial_scan_never_authorize_a_new_tree(self):
        v=volume();self.assertIsNone(choose(v,[.5,65,.5],[{'min':[0,60,0],'max':[2,90,2]}]))
        with self.assertRaises(ValueError):choose({**v,'complete':False},[.5,65,.5])
    def test_a_narrow_scout_can_only_return_a_hint_for_a_new_full_harvest_scan(self):
        v=volume();v.update(min=[-3,59,-3],max=[3,104,3])
        v['blocks']=[r for r in v['blocks']if abs(r['pos'][0])<=3 and abs(r['pos'][2])<=3]
        self.assertIsNone(choose(v,[.5,65,.5]))
        hint=choose(v,[.5,65,.5],require_harvest_halo=False)
        self.assertEqual([0,64,0],hint['root']);self.assertFalse(hint['harvest_halo_observed'])
    def test_crops_beyond_the_crown_remain_untouched_observation_space(self):
        v=volume();v['blocks'].append({'pos':[9,64,0],'state':'Block{minecraft:sugar_cane}[age=0]',
                                     'fluid':False,'block_entity':False})
        site=choose(v,[.5,65,.5]);self.assertEqual([0,64,0],site['root']);self.assertFalse(site['clearing_required'])
    def test_normal_sapling_placement_can_replace_observed_short_grass_without_calling_it_air(self):
        v=volume();plant={'pos':[0,64,0],'state':'Block{minecraft:short_grass}',
                         'replaceable':True,'fluid':False,'block_entity':False}
        v['blocks'].append(plant);site=choose(v,[.5,65,.5])
        self.assertEqual([0,64,0],site['root']);self.assertEqual(plant,site['root_before'])
    def test_natural_leaves_can_be_replaced_but_decorative_leaves_cannot(self):
        v=volume();v['blocks'].append({'pos':[0,66,0],'state':'Block{minecraft:oak_leaves}[persistent=false]',
                                     'fluid':False,'block_entity':False})
        self.assertIsNotNone(choose(v,[.5,65,.5]))
        v['blocks'][-1]['state']='Block{minecraft:oak_leaves}[persistent=true]'
        self.assertIsNone(choose(v,[.5,65,.5]))
