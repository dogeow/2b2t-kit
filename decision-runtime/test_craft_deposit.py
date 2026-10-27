import copy
import unittest
from unittest.mock import patch
import craft_recipe


def scene(stamp,cell,cursor):
    return {'time':stamp,'menu':{'id':6,'cursor':{'item':'minecraft:dark_oak_planks','count':cursor},
            'slots':[{'item':'minecraft:air','count':0},{'item':'minecraft:dark_oak_planks','count':cell}]}}


class CraftDepositTests(unittest.TestCase):
    def test_stale_reply_is_observed_not_reclicked_and_next_count_is_current(self):
        initial=scene(1,1,50);first=scene(2,2,49);second=scene(3,2,49)
        class Client:
            def __init__(self):self.frames=iter([copy.deepcopy(initial),first,second])
            def status(self):return next(self.frames)
        with patch.object(craft_recipe,'k',Client()),patch.object(craft_recipe,'checked',return_value=initial)as click:
            result=craft_recipe.deposit_one(initial,6,1,'minecraft:dark_oak_planks')
            self.assertEqual(result,second)
            click.assert_called_once()
            self.assertEqual(click.call_args.kwargs['expected_count'],1)
            self.assertEqual(click.call_args.kwargs['expected_cursor_count'],50)

    def test_rejected_or_unknown_click_is_never_retried(self):
        with patch.object(craft_recipe,'checked',side_effect=RuntimeError('unknown native outcome'))as click:
            with self.assertRaisesRegex(RuntimeError,'unknown native'):
                craft_recipe.deposit_one(scene(1,1,50),6,1,'minecraft:dark_oak_planks')
            click.assert_called_once()

    def test_changed_cursor_prevents_any_click(self):
        with patch.object(craft_recipe,'checked')as click:
            with self.assertRaises(RuntimeError):
                craft_recipe.deposit_one(scene(1,1,0),6,1,'minecraft:dark_oak_planks')
            click.assert_not_called()
