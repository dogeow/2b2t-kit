import unittest
from printer_mode_handoff import restoration_target,idle_for_mode


class PrinterModeHandoffTests(unittest.TestCase):
    def test_original_choice_is_restored_only_without_new_external_changes(self):
        self.assertTrue(restoration_target(True,3,dict(external_mode_revision=3)))
        self.assertFalse(restoration_target(False,3,dict(external_mode_revision=3)))
    def test_later_user_choices_beat_the_old_restore_target(self):
        self.assertFalse(restoration_target(True,3,dict(external_mode_revision=4,last_external_enabled=False)))
        self.assertTrue(restoration_target(False,3,dict(external_mode_revision=5,last_external_enabled=True)))
    def test_unknown_and_older_revisions_are_not_restore_authority(self):
        for p in [{},{'external_mode_revision':2},{'external_mode_revision':4},
                  {'external_mode_revision':4,'last_external_enabled':'false'}]:
            self.assertIsNone(restoration_target(True,3,p))
    def test_mode_change_cannot_preempt_an_owner_or_manual_input(self):
        state=dict(connected=True,health=20,projection_selection=dict(key='key'))
        self.assertTrue(idle_for_mode(state,'key'))
        for change in [dict(manual_movement=True),dict(screen='ContainerScreen'),dict(health=17),
                       dict(supervision_lease=dict(job_session='other')),dict(professional_printer=dict(owned=True)),
                       dict(build_job=dict(active=True)),dict(projection_batch=dict(active=True)),
                       dict(safety_hold=dict(active=True)),dict(navigating=True)]:
            self.assertFalse(idle_for_mode({**state,**change},'key'))


if __name__=='__main__':unittest.main()
