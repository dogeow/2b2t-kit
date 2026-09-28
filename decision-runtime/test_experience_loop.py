import json
import tempfile
import unittest
from pathlib import Path

from experience_loop import ExperienceStore, MAX_EXAMPLES, MAX_SOURCE_BYTES, ingest_sources, watch_sources


def lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


def mining_case(decision_id, outcome, choice='retry_once'):
    incident = {'cause': 'mine', 'phase': 'DIG', 'no_progress_seconds': 12,
                'tool_class': 'pickaxe', 'block_class': 'stone',
                'inventory_band': 'roomy', 'health_band': 'healthy',
                'server_ack': 'timeout', 'secret_position': [761004, 63, 797829]}
    return [
        {'kind': 'prompt_summary', 'decision_id': decision_id,
         'data': {'incident': incident, 'candidates': {'pause': 'pause', choice: 'test'}}},
        {'kind': 'decision', 'decision_id': decision_id,
         'data': {'choice': choice, 'source': 'jev', 'raw_reply': 'private marker'}},
        {'kind': 'outcome', 'decision_id': decision_id,
         'data': {'choice': choice, 'outcome': outcome}},
    ]


def recovery(job, action='replan', success=True, time_value=1):
    return {'kind': 'recovery_observed', 'time': time_value, 'job': job,
            'fingerprint': 'secret-server-hash', 'action': action, 'success': success,
            'before': {'matched': 10, 'active': True, 'blocked_blocks': 1,
                       'navigation': {'secret_position': [761004, 63, 797829]}},
            'after': {'matched': 11 if success else 10,
                      'server': 'private.example', 'health': 20}}


class ExperienceLoopTests(unittest.TestCase):
    def test_mining_advice_is_not_mislabeled_as_executed_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'mining.jsonl'
            rows = mining_case('case-a', 'paused_pending_explicit_restart')
            rows += mining_case('case-b', 'post_restart_observed_target_air')
            rows += mining_case('case-c', 'post_restart_no_confirmed_progress')
            rows += mining_case('case-d', 'post_restart_re_stalled')
            rows += mining_case('case-e', 'post_restart_confirmed_column_progress')[:2]
            rows += mining_case('case-b', 'paused_pending_explicit_restart')[-1:]
            rows += mining_case('case-b', 'post_restart_observed_target_air')[-1:]
            lines(log, rows)
            with ExperienceStore(root / 'memory.sqlite3') as store:
                self.assertEqual(store.ingest_mining(log), 3)
                self.assertEqual(store.ingest_mining(log), 0)
                out = root / 'examples.jsonl'
                self.assertEqual(store.export(out), 3)
                self.assertEqual(store.rankings(), [])
            samples = [json.loads(row) for row in out.read_text().splitlines()]
            self.assertEqual({s['label'] for s in samples},
                             {'observed_target_air_after_restart', 'observed_no_progress',
                              'observed_re_stall'})
            self.assertTrue(all(s['executed_action'] is None and s['advice'] == 'retry_once'
                                and s['training_use'] == 'diagnosis_only'
                                and s['advice_caused_outcome'] is False for s in samples))
            exported = out.read_text()
            self.assertNotIn('761004', exported)
            self.assertNotIn('private marker', exported)
            self.assertNotIn('case-b', exported)

    def test_paving_requires_complete_receipt_chain_and_blocks_are_guard_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / 'dry-paving-v1' / 'secret-server-hash'
            base = {'schema': 1, 'phase': 'complete', 'pos': [761004, 63, 797829],
                    'server': 'private.example', 'actual': 'Block{minecraft:grass_block}',
                    'expected': 'Block{minecraft:stone_bricks}', 'world_session': 'private-world',
                    'updated_at_ns': 900,
                    'receipts': [{'phase': 'mine_intent'},
                                 {'phase': 'mined', 'server_air': True},
                                 {'phase': 'recovered', 'inventory_after': 1},
                                 {'phase': 'place_intent'},
                                 {'phase': 'complete', 'actual': 'Block{minecraft:stone_bricks}',
                                  'material_after': 8}]}
            directory.mkdir(parents=True)
            (directory / 'complete.json').write_text(json.dumps(base))
            incomplete = {**base, 'receipts': base['receipts'][:-2], 'updated_at_ns': 901}
            (directory / 'incomplete.json').write_text(json.dumps(incomplete))
            blocker = root / 'paving-blockers.jsonl'
            lines(blocker, [{'at_ns': 1_790_000_000_000_000_000, 'cell': [761004, 63, 797829],
                             'journal_phase': 'recovered', 'kind': 'nearby_entity',
                             'nearby': ['private-player-uuid'],
                             'player_position': [761003, 64, 797830]}])
            with ExperienceStore(root / 'memory.sqlite3') as store:
                self.assertEqual(store.ingest_paving(root / 'dry-paving-v1', blocker), 2)
                self.assertEqual(store.ingest_paving(root / 'dry-paving-v1', blocker), 0)
                self.assertEqual(store.rankings(), [])
                out = root / 'examples.jsonl'
                store.export(out)
            samples = [json.loads(row) for row in out.read_text().splitlines()]
            self.assertEqual({s['label'] for s in samples}, {'verified_complete', 'guard_blocked'})
            self.assertEqual({s['training_use'] for s in samples}, {'diagnosis_only'})
            export = out.read_text()
            self.assertNotIn('761004', export)
            self.assertNotIn('private.example', export)
            self.assertNotIn('private-player-uuid', export)

    def test_paving_cursor_reaches_later_files_beyond_two_thousand_and_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / 'dry-paving-v1' / 'one-world'
            directory.mkdir(parents=True)
            for index in range(2001):
                (directory / f'old-{index:04}.json').write_text('{}')
            def valid_journal(marker):
                return {'schema': 1, 'phase': 'complete', 'pos': [marker, 63, 10],
                        'actual': 'Block{minecraft:grass_block}',
                        'expected': 'Block{minecraft:stone_bricks}',
                        'world_session': 'private-world', 'updated_at_ns': marker,
                        'receipts': [{'phase': 'mine_intent'},
                                     {'phase': 'mined', 'server_air': True},
                                     {'phase': 'recovered', 'inventory_after': 1},
                                     {'phase': 'place_intent'},
                                     {'phase': 'complete', 'actual': 'Block{minecraft:stone_bricks}',
                                      'material_after': 8}]}
            (directory / 'z-late.json').write_text(json.dumps(valid_journal(3)))
            with ExperienceStore(root / 'memory.sqlite3') as store:
                self.assertEqual(sum(store.ingest_paving(root / 'dry-paving-v1')
                                     for _ in range(3)), 1)
                self.assertEqual(store.count(), 1)
                (directory / 'z-newer.json').write_text(json.dumps(valid_journal(4)))
                self.assertEqual(sum(store.ingest_paving(root / 'dry-paving-v1')
                                     for _ in range(3)), 1)
                self.assertEqual(store.count(), 2)

    def test_ranking_needs_three_distinct_confirmed_runs_and_abstains_on_uncertainty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'events.jsonl'
            lines(log, [recovery('one', time_value=1), recovery('one', time_value=2),
                        recovery('two', time_value=3)])
            with ExperienceStore(root / 'memory.sqlite3') as store:
                self.assertEqual(store.ingest_build_events(log), 3)
                self.assertEqual(store.rankings()[0]['status'], 'abstain')
                lines(log, [recovery('one', time_value=1), recovery('two', time_value=3),
                            recovery('three', time_value=4)])
                self.assertEqual(store.ingest_build_events(log), 1)
                self.assertEqual(store.rankings()[0]['status'], 'candidate_for_human_review')
                lines(log, [recovery('four', success=False, time_value=5)])
                self.assertEqual(store.ingest_build_events(log), 1)
                self.assertEqual(store.rankings()[0]['status'], 'abstain')
                out = root / 'examples.jsonl'
                store.export(out)
            export = out.read_text()
            self.assertNotIn('private.example', export)
            self.assertNotIn('secret-server-hash', export)
            self.assertNotIn('761004', export)
            self.assertNotIn('"job"', export)

    def test_claimed_success_without_observed_gain_cannot_rank(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'events.jsonl'
            events = [recovery(str(n), time_value=n) for n in range(3)]
            events[0]['after']['matched'] = 10
            lines(log, events)
            with ExperienceStore(root / 'memory.sqlite3') as store:
                store.ingest_build_events(log)
                result = store.rankings()[0]
            self.assertEqual(result['confirmed_runs'], 2)
            self.assertEqual(result['uncertain_runs'], 1)
            self.assertEqual(result['status'], 'abstain')

    def test_evidence_rank_is_within_context_and_never_a_live_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'events.jsonl'
            rows = [recovery('replan-' + str(i), 'replan', time_value=i) for i in range(4)]
            rows += [recovery('rescan-' + str(i), 'rescan', time_value=10+i) for i in range(3)]
            lines(log, rows)
            with ExperienceStore(root / 'memory.sqlite3') as store:
                store.ingest_build_events(log)
                ranking = store.rankings()
            self.assertEqual([(r['candidate'], r['evidence_rank']) for r in ranking],
                             [('replan', 1), ('rescan', 2)])
            self.assertTrue(all(r['status'] == 'candidate_for_human_review' for r in ranking))

    def test_oversized_and_malformed_sources_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'mining.jsonl'
            log.write_bytes(b'{' + b'a' * 17000 + b'}\ninvalid\n')
            with ExperienceStore(root / 'memory.sqlite3') as store:
                self.assertEqual(store.ingest_mining(log), 0)
                self.assertEqual(store.count(), 0)
            self.assertEqual(MAX_EXAMPLES, 10000)

    def test_bounded_watch_imports_only_new_client_observation_after_log_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'mining.jsonl'
            rows = mining_case('case-a', 'paused_pending_explicit_restart')
            lines(log, rows)
            progress = []
            def append_followup(_seconds):
                with log.open('a') as stream:
                    stream.write(json.dumps(mining_case(
                        'case-a', 'post_restart_confirmed_column_progress')[-1]) + '\n')
            with ExperienceStore(root / 'memory.sqlite3') as store:
                result = watch_sources(store, {'mining_log': log}, interval_seconds=5,
                                       cycles=2, sleep=append_followup,
                                       on_progress=progress.append)
                self.assertEqual(result, {'cycles': 2, 'new': 1, 'stored': 1,
                                          'tail_only_sources': []})
                self.assertEqual(progress, [{'new': 1, 'stored': 1,
                                             'tail_only_sources': []}])
                with self.assertRaises(ValueError):
                    watch_sources(store, {'mining_log': log}, interval_seconds=1,
                                  cycles=2, sleep=lambda _: None)

    def test_append_only_log_past_four_megabytes_still_imports_future_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'build-events.jsonl'
            log.write_bytes(b'X' * (MAX_SOURCE_BYTES + 100) + b'\n')
            with log.open('a') as stream:
                stream.write(json.dumps(recovery('new-job', time_value=1)) + '\n')
            with ExperienceStore(root / 'memory.sqlite3') as store:
                result = ingest_sources(store, build_events=log)
                self.assertEqual(result['projection_recoveries'], 1)
                self.assertEqual(result['tail_only_sources'], ['build_events'])
                with log.open('a') as stream:
                    stream.write(json.dumps(recovery('next-job', time_value=2)) + '\n')
                result = ingest_sources(store, build_events=log)
                self.assertEqual(result['projection_recoveries'], 1)
                self.assertEqual(result['tail_only_sources'], ['build_events'])
                self.assertEqual(store.count(), 2)
                progress = []
                watched = watch_sources(store, {'build_events': log}, interval_seconds=5,
                                        cycles=1, on_progress=progress.append)
                self.assertEqual(watched['tail_only_sources'], ['build_events'])
                self.assertEqual(progress, [{'new': 0, 'stored': 2,
                                             'tail_only_sources': ['build_events']}])


if __name__ == '__main__':
    unittest.main()
