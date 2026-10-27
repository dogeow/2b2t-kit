import unittest
from unittest.mock import patch
from villager_events import wait_for_frame
class VillagerFrameWaitTests(unittest.TestCase):
 def timer(self):
  tick=[0.]
  def pause(seconds):tick[0]+=seconds
  return lambda:tick[0],pause
 def test_transient_frame_requires_a_new_validated_read(self):
  clock,pause=self.timer();frame={'villagers':[]};states=[]
  def state():states.append(1);return {'time':len(states)}
  with patch('villager_events.read',side_effect=[None,frame])as reader:
   self.assertIs(wait_for_frame('r',state,clock=clock,pause=pause),frame);self.assertEqual(reader.call_count,2)
  self.assertEqual(len(states),2)
 def test_unavailable_evidence_is_never_treated_as_empty_and_times_out(self):
  clock,pause=self.timer()
  with patch('villager_events.read',return_value=None),self.assertRaisesRegex(RuntimeError,'no new world input'):wait_for_frame('r',lambda:{},clock=clock,pause=pause)
  self.assertLessEqual(clock(),3)
 def test_manual_takeover_or_health_error_during_wait_propagates(self):
  clock,pause=self.timer()
  def state():raise RuntimeError('owner lost')
  with self.assertRaisesRegex(RuntimeError,'owner lost'):wait_for_frame('r',state,clock=clock,pause=pause)
 def test_overlong_wait_is_rejected(self):
  with self.assertRaises(ValueError):wait_for_frame('r',lambda:{},seconds=4)
