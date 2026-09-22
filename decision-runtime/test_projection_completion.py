import copy
import unittest
from projection_completion import block_state, classify, repair_plan, decoration_manifest, compare_decorations


def row(actual, expected='Block{minecraft:stone_bricks}', **extra):
    return {'pos':[10,60,20], 'actual':actual, 'expected':expected, 'kind':'occupied',
            'block_entity':False, 'fluid':False, **extra}


class CompletionTests(unittest.TestCase):
    def selection(self):
        return {'key':'house/NONE/NONE', 'min':[10,60,20], 'max':[14,64,24]}

    def test_log_is_transformed_only_when_axis_and_other_properties_match(self):
        self.assertEqual(classify(row('Block{minecraft:spruce_log}[axis=x]', 'Block{minecraft:stripped_spruce_log}[axis=x]')), 'strip_in_place')
        self.assertEqual(classify(row('Block{minecraft:spruce_log}[axis=x]', 'Block{minecraft:stripped_spruce_log}[axis=y]')), 'specific_block_repair')

    def test_fluid_and_container_checks_outrank_terrain_or_state_repair(self):
        self.assertEqual(classify(row('Block{minecraft:dirt}', adjacent_fluid=True)), 'fluid_review')
        self.assertEqual(classify(row('Block{minecraft:chest}[type=single]', 'Block{minecraft:chest}[type=left]', kind='state_only',block_entity=True)), 'preserve_container_or_block_entity')
        self.assertEqual(classify(row('Block{minecraft:glass_pane}[north=false]', 'Block{minecraft:glass_pane}[north=true]',kind='state_only')), 'refresh_connections_after_shell')

    def test_old_audit_cannot_claim_interiors_or_neighbor_hazards_were_checked(self):
        a={'placement_key':'house/NONE/NONE','matched':0,'total':1,'mismatches':[row('Block{minecraft:dirt}')]}
        p=repair_plan(a,self.selection())
        self.assertFalse(p['interior_air_checked'])
        self.assertTrue(p['groups']['terrain_clear_candidate'][0]['needs_neighbor_rescan'])
        self.assertFalse(p['safe_to_execute_without_revalidation'])

    def test_scope_and_count_mismatch_are_rejected(self):
        a={'placement_key':'house/NONE/NONE','matched':0,'total':1,'mismatches':[row('Block{minecraft:dirt}')]}
        bad=copy.deepcopy(a);bad['mismatches'][0]['pos']=[9,60,20]
        with self.assertRaises(ValueError):repair_plan(bad,self.selection())
        bad=copy.deepcopy(a);bad['total']=2
        with self.assertRaises(ValueError):repair_plan(bad,self.selection())
        bad=copy.deepcopy(a);bad['placement_key']='another'
        with self.assertRaises(ValueError):repair_plan(bad,self.selection())

    def manifest(self):
        special={'sha256':'example','entities':[
            {'id':'minecraft:item_frame','Pos':[1.5,2.5,1.03125],'Facing':3,'ItemRotation':4,
             'Item':{'id':'minecraft:white_banner','count':1}},
            {'id':'minecraft:armor_stand','Pos':[2.5,1,2.5],'Rotation':[360,0],'Pose':{}}],
            'tile_entities':[{'id':'minecraft:banner','x':1,'y':3,'z':1,'patterns':[{'color':'black','pattern':'minecraft:border'}]}]}
        return decoration_manifest(special,self.selection(),{'position':[0,0,0],'size':[5,5,5]})

    def test_translation_keeps_frame_offsets_and_material_accounting(self):
        m=self.manifest()
        self.assertEqual(m['entities'][0]['pos'],[11.5,62.5,21.03125])
        self.assertEqual(m['banners'][0]['pos'],[11,63,21])
        self.assertEqual(m['items_before_subtracting_verified_existing_entities']['minecraft:white_banner'],1)

    def test_transformed_placements_are_rejected_instead_of_guessed(self):
        special={'sha256':'x','entities':[],'tile_entities':[]};selection=self.selection();selection['key']='house/CLOCKWISE_90/NONE'
        with self.assertRaises(ValueError):decoration_manifest(special,selection,{'position':[0,0,0],'size':[5,5,5]})

    def test_old_or_absent_entity_observation_never_counts_as_completion(self):
        m=self.manifest();a={'placement_key':m['placement_key']}
        r=compare_decorations(m,a);self.assertFalse(r['all_observed_appearance_matches'])
        self.assertTrue(all(e['status']=='unverified' for e in r['entity_checks']))
        a.update(audit_schema=2,decorations=[],banners=[])
        r=compare_decorations(m,a);self.assertTrue(all(e['status']=='not_observed' for e in r['entity_checks']))
        self.assertFalse(r['automatic_removal_authorized'])

    def test_item_rotation_banner_pattern_and_yaw_are_separately_checked(self):
        m=self.manifest();actual=[{k:v for k,v in e.items() if k!='index'} for e in m['entities']];actual[1]['yaw']=0
        a={'placement_key':m['placement_key'],'audit_schema':2,'decorations':actual,'banners':copy.deepcopy(m['banners'])}
        self.assertTrue(compare_decorations(m,a)['all_observed_appearance_matches'])
        a['decorations'][0]['item_rotation']=0
        a['banners'][0]['patterns']=[]
        r=compare_decorations(m,a)
        self.assertEqual(r['entity_checks'][0]['different_fields'],['item_rotation'])
        self.assertEqual(r['banner_checks'][0]['status'],'different')

    def test_duplicate_entities_are_not_silently_accepted(self):
        m=self.manifest();entity={k:v for k,v in m['entities'][0].items() if k!='index'}
        a={'placement_key':m['placement_key'],'audit_schema':2,'decorations':[entity,entity]}
        self.assertEqual(compare_decorations(m,a)['entity_checks'][0]['status'],'ambiguous')

    def test_malformed_block_states_cannot_become_action_candidates(self):
        for state in ('stone','Block{minecraft:stone};clear','Block{minecraft:log}[axis=x,axis=y]'):
            with self.assertRaises(ValueError):block_state(state)


if __name__=='__main__':unittest.main()
