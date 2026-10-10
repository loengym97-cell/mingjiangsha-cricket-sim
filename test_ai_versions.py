import tempfile
from pathlib import Path
import unittest
import importlib.util
from unittest.mock import patch
from engine import Game, Card
from batch import run_batch, connect, get_detail, get_run

class StrategyTests(unittest.TestCase):
    def test_folder_layout_preserves_historical_strategy_decisions(self):
        old=Path(__file__).parent/'versions'/'538dd1b8aba900f0'/'ai.py'
        if not old.exists(): self.skipTest('本机旧版本快照不存在')
        spec=importlib.util.spec_from_file_location('historical_ai',old)
        legacy=importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
        for left_ai,right_ai in [('v1','v1'),('v3','v7'),('v6','v5'),('v3','v3'),('v1','v2'),('v1','v4')]:
            for i in range(12):
                current=Game(7654+i//2,first=i%2,trace=True,left_ai=left_ai,right_ai=right_ai)
                previous=Game(7654+i//2,first=i%2,trace=True,left_ai=left_ai,right_ai=right_ai)
                for p,v in zip(previous.players,(left_ai,right_ai)): p.character.ai=legacy.create_ai(v,p.character)
                self.assertEqual(current.run(check=True),previous.run(check=True))
                self.assertEqual(current.events,previous.events)

    def card(self, g, p, name, zone='hand', suit='♣', rank=2):
        c = g.deck.pop(); c.name=name; c.suit=suit; c.rank=rank
        getattr(p,zone).append(c)
        return c

    def test_gan_equips_safely_and_accepts_emergency_growth(self):
        g=Game(right_ai='v2'); w,n=g.players
        c=self.card(g,n,'八卦盾')
        self.assertIsNone(n.character.choose_equipment(g,n))
        self.card(g,w,'云锦袍','equipment')
        self.assertIs(n.character.choose_equipment(g,n),c)
        g.drop(w,w.equipment[0]); n.hp=1
        self.assertIs(n.character.choose_equipment(g,n),c)

    def test_baseline_gan_still_does_not_equip(self):
        g=Game(); n=g.players[1]
        self.card(g,n,'银狮盔'); n.hp=1
        self.assertIsNone(n.character.choose_equipment(g,n))

    def test_distance_ai_removes_cloud_to_force_random_overflow(self):
        g=Game(right_ai='v7'); w,n=g.players
        cloud=self.card(g,w,'云锦袍','equipment')
        for _ in range(3): self.card(g,w,'诸葛连弩','equipment')
        self.assertIs(n.character.choose_removal(g,w),cloud)

    def test_distance_ai_removes_mount_blocking_attack(self):
        g=Game(right_ai='v7'); w,n=g.players
        mount=self.card(g,w,'绝影','equipment')
        self.card(g,w,'诸葛连弩','equipment')
        self.assertIs(n.character.choose_removal(g,w),mount)

    def test_tactical_wang_preserves_only_attack(self):
        g=Game(left_ai='v3'); w=g.players[0]
        kill=self.card(g,w,'杀'); dodge=self.card(g,w,'闪避')
        self.assertIs(w.character.ai.transform_card(g,w,[kill,dodge]),dodge)

    def test_tactical_gan_attacks_before_washing(self):
        g=Game(right_ai='v3'); n=g.players[1]
        self.card(g,n,'杀')
        n.character.phase_start()
        self.assertTrue(n.character.ai.defer_wash(g,n))
        g.used=1
        self.assertFalse(n.character.ai.defer_wash(g,n))

    def test_range_mounts_and_weapon_maximum(self):
        g=Game(); w,n=g.players
        self.card(g,n,'绝影','equipment'); self.card(g,n,'的卢','equipment')
        self.assertEqual(g.distance(w,n),3)
        self.assertFalse(g.can_attack(w,n))
        self.card(g,w,'鸣鸿刀','equipment'); self.card(g,w,'亮银枪','equipment')
        self.assertEqual(g.attack_range(w),3)
        self.assertTrue(g.can_attack(w,n))
        self.assertFalse(g.can_use_tactic(w,'夺粮劫营'))
        self.card(g,w,'乌骓','equipment'); self.card(g,w,'盗骊','equipment')
        self.assertEqual(g.distance(w,n),1)

    def test_rage_random_cost_can_discard_equipment(self):
        g=Game(); w=g.players[0]
        rage=self.card(g,w,'怒气'); gear=self.card(g,w,'凤羽盔','equipment')
        g.rage_uses=1
        with patch.object(g.rng,'choice',return_value=gear): g.play_rage(w,rage)
        self.assertNotIn(gear,w.equipment)
        self.assertIn(gear,g.discard)

    def test_duplicate_bagua_only_divines_once(self):
        g=Game(); w=g.players[0]
        self.card(g,w,'八卦盾','equipment'); self.card(g,w,'八卦盾','equipment')
        with patch.object(g,'divine',return_value=Card(999,'♦',1,'杀')) as divine:
            self.assertFalse(g.respond(w,'闪避'))
            self.assertEqual(divine.call_count,1)

    def test_duplicate_minghong_still_requires_only_two_dodges(self):
        g=Game(); w,n=g.players
        for _ in range(2): self.card(g,w,'鸣鸿刀','equipment')
        attack=self.card(g,w,'杀')
        for _ in range(2): self.card(g,n,'闪避')
        g.attack(w,attack)
        self.assertEqual(n.hp,n.max_hp)
        self.assertFalse(n.hand)

    def test_borrowed_attack_can_target_caster_without_spending_budget(self):
        g=Game(); w,n=g.players
        tactic=self.card(g,w,'调兵遣将'); self.card(g,n,'杀')
        used=g.used
        g.tactic(w,tactic)
        self.assertEqual(w.hp,w.max_hp-1)
        self.assertEqual(g.used,used)

    def test_borrowed_attack_without_kill_transfers_card(self):
        g=Game(); w,n=g.players
        tactic=self.card(g,w,'调兵遣将'); card=self.card(g,n,'闪避',suit='♥')
        g.tactic(w,tactic)
        self.assertIn(card,w.hand)
        self.assertNotIn(card,n.hand)

    def test_bright_spear_counterattack_triggers_other_spear(self):
        g=Game(trace=True); w,n=g.players
        self.card(g,w,'亮银枪','equipment'); self.card(g,n,'亮银枪','equipment')
        original=self.card(g,w,'杀'); self.card(g,w,'杀'); self.card(g,n,'杀')
        g.attack(w,original)
        attacks=[e for e in g.events if '向' in e['text'] and '打出' in e['text']]
        self.assertEqual(len(attacks),3)
        self.assertEqual(g.depth,0)
        g.check()

    def test_corrected_long_game_never_raises_action_loop(self):
        g=Game(20262297,first=0,right_ai='v2')
        r=g.run(check=True)
        self.assertIn(r['winner_side'],(0,1,-2))

    def test_delayed_removed_by_reactive_gain_is_not_resolved_again(self):
        for seed, left_ai, right_ai in [(20262211,'v1','v5'),(20262107,'v3','v3')]:
            g=Game(seed,first=0,left_ai=left_ai,right_ai=right_ai)
            r=g.run(check=True)
            self.assertIn(r['winner_side'],(0,1,-2))

    def test_versioned_batch_replays_with_saved_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'results.sqlite3'
            result=run_batch(4,seed=9,db=db,left_ai='v3',right_ai='v2')
            conn=connect(db)
            try:
                saved=get_run(conn,result['run_id'])
                self.assertEqual(saved['params']['right_ai'],'v2')
                for i in range(4):
                    g=Game(9+i//2,first=i%2,left_ai='v3',right_ai='v2',trace=True)
                    r=g.run(check=True)
                    d=get_detail(conn,result['run_id'],i+1)
                    self.assertEqual(d['result'],r)
                    self.assertEqual(d['events'],g.events)
            finally: conn.close()

if __name__=='__main__': unittest.main()
