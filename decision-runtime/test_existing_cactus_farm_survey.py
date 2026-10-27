import copy
import unittest
from material_jobs.renewable_cactus import owned_farm_top


class ExistingCactusFarmSurveyTest(unittest.TestCase):
    def fixture(self):
        state={'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'w',
               'projection_selection':{'key':'original','min':[100,64,100],'max':[110,64,110]}}
        farm={'authorized':True,'source':'current_existing_farm_survey','survey_receipt':'actual-survey.json',
              'bases_verified':True,'supports_verified':True,'server':'simpcraft.com','dimension':'minecraft:overworld',
              'world_session':'w','goal_key':'original','positions':[[10,65,20]]}
        profile={'survey_registered_cactus_farms':[farm],'protected_regions':[
            {'min':[0,40,0],'max':[40,150,40],'note':'base_courtyard_villa_projection_no_survey'}]}
        return profile,state

    def test_current_survey_allows_only_two_grown_cells_and_never_the_root(self):
        p,s=self.fixture()
        self.assertTrue(owned_farm_top(p,s,[10,66,20]));self.assertTrue(owned_farm_top(p,s,[10,67,20]))
        self.assertFalse(owned_farm_top(p,s,[10,65,20]));self.assertFalse(owned_farm_top(p,s,[10,68,20]))
        self.assertFalse(owned_farm_top(p,s,[11,66,20]))

    def test_other_world_goal_or_protected_structure_cannot_reuse_the_survey(self):
        p,s=self.fixture()
        for field,value in [('world_session','old'),('goal_key','different'),('server','other'),
                            ('bases_verified',False),('supports_verified',False),('survey_receipt','')]:
            bad=copy.deepcopy(p);bad['survey_registered_cactus_farms'][0][field]=value
            self.assertFalse(owned_farm_top(bad,s,[10,66,20]))
        p['protected_regions'].append({'min':[9,0,19],'max':[11,100,21],'note':'user_protected_build'})
        self.assertFalse(owned_farm_top(p,s,[10,66,20]))

if __name__=='__main__':unittest.main()
