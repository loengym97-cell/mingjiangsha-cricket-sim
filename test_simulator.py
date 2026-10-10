import unittest
from unittest.mock import patch
from deck import summary
from simulator import Game
from engine import GameFinished


class RulesTests(unittest.TestCase):
    def test_lethal_counterattack_ends_game_before_original_attack(self):
        g = Game(first=0)
        w, n = g.players
        def attack_turn(index):
            for p in g.players:
                for c in list(p.hand): g.drop(p, c)
                p.hp = 1
            self.card(g, "亮银枪", n, "equipment")
            self.card(g, "杀", n)
            attack = self.card(g, "杀", w)
            g.attack(w, attack)
            self.fail("致死反击后不应继续返回原杀结算")
        with patch.object(g, "turn", side_effect=attack_turn):
            result = g.run(check=True)
        self.assertEqual(result["winner_side"], 1)
        self.assertEqual(n.hp, 1)
        self.assertEqual(w.hp, 0)
        g.check()

    def test_lethal_chain_damage_stops_before_transfer(self):
        g = Game()
        w, n = g.players
        w.chained = n.chained = True
        n.hp = 1
        with self.assertRaises(GameFinished): g.damage(w, n, 1, "fire")
        self.assertEqual(w.hp, 6)
        self.assertEqual(n.hp, 0)
        g.check()

    def test_hand_limit_is_only_enforced_after_play_phase(self):
        g = Game(left="白板", right="白板")
        p = g.players[0]
        g.draw(p, 6)
        self.assertEqual(len(p.hand), 6)
        def play_phase(game, player):
            self.assertEqual(len(player.hand), 8)
        with patch.object(p.character, "play_phase", side_effect=play_phase):
            g.turn(0)
        self.assertEqual(len(p.hand), p.base_hand_limit)
        g.check()

    def test_both_players_receive_four_initial_cards_in_either_order(self):
        for first in (0, 1):
            g = Game(first=first, trace=True)
            self.assertEqual(g.hand_limit(g.players[0]), 3)
            g.run(max_rounds=1, check=True)
            gains = [event for event in g.events if event["turn"] == 0 and "获得" in event["text"]]
            self.assertEqual(len(gains), 2)
            self.assertEqual(len(gains[0]["state"]["players"][first]["hand"]), 4)
            self.assertEqual(len(gains[1]["state"]["players"][1-first]["hand"]), 4)

    def card(self, game, name, owner, zone="hand"):
        c = next(c for c in game.deck if c.name == name)
        game.deck.remove(c)
        getattr(owner, zone).append(c)
        return c

    def test_deck_counts(self):
        data = summary()
        self.assertEqual(data["total"], 162)
        self.assertEqual(data["suits"], {"♦": 40, "♣": 40, "♠": 40, "♥": 40, "八卦": 2})
        self.assertEqual(data["names"]["闪避"], 22)
        self.assertEqual(sum(data["names"][n] for n in ("杀", "雷杀", "火杀")), 45)

    def test_batch_spades_only_one_strip(self):
        g = Game()
        w, n = g.players
        self.card(g, "杀", w)
        self.card(g, "杀", w)
        spades = [c for c in g.deck if c.suit == "♠"][:3]
        for c in spades: g.deck.remove(c)
        g.gain(n, spades)
        self.assertEqual(len(w.hand), 1)
        self.assertEqual(g.stats["甘宁拆牌触发"], 1)
        g.check()

    def test_transform_stays_in_hand(self):
        g = Game()
        w = g.players[0]
        self.card(g, "杀", w)
        self.assertTrue(w.character.transform(g, w))
        self.assertEqual(len(w.equipment), 0)
        self.assertEqual(len(w.hand), 2)
        g.check()

    def test_suit_mutation_survives_reshuffle(self):
        g = Game()
        w = g.players[0]
        c = self.card(g, "火杀", w)
        c.suit = "♠"
        g.drop(w, c)
        rest, g.deck = g.deck, []
        drawn = g.take()
        self.assertIs(drawn, c)
        self.assertEqual(drawn.suit, "♠")
        g.deck = rest + [drawn]
        g.check()

    def test_burn_never_recycles(self):
        g = Game()
        w = g.players[0]
        c = self.card(g, "杀", w)
        g.drop(w, c, True)
        self.assertIn(c, g.burned)
        self.assertNotIn(c, g.discard)
        g.check()

    def test_minghong_discards_attacker(self):
        g = Game()
        g.active = 0
        w, n = g.players
        self.card(g, "鸣鸿刀", w, "equipment")
        attack = self.card(g, "杀", w)
        self.card(g, "闪避", n)
        self.card(g, "闪避", n)
        g.attack(w, attack)
        self.assertFalse(w.equipment)
        self.assertEqual(n.hp, 6)
        g.check()

    def test_lion_caps_damage_and_is_destroyed(self):
        g = Game()
        w, n = g.players
        armor = self.card(g, "银狮盔", n, "equipment")
        g.damage(w, n, 4, "thunder")
        self.assertEqual(n.hp, 5)
        self.assertIn(armor, g.burned)
        g.check()

    def test_vine_fire_then_destroy(self):
        g = Game()
        w, n = g.players
        armor = self.card(g, "藤甲", n, "equipment")
        g.damage(w, n, 1)
        self.assertEqual(n.hp, 6)
        g.damage(w, n, 1, "fire")
        self.assertEqual(n.hp, 4)
        self.assertIn(armor, g.burned)
        g.check()

    def test_generated_cards_have_unique_ids(self):
        g = Game()
        w = g.players[0]
        self.card(g, "丈八蛇矛", w)
        g.equip(w)
        self.assertEqual(g.next_id, 164)
        self.assertEqual(len(w.hand), 2)
        g.check()

    def test_gan_never_equips(self):
        g = Game()
        n = g.players[1]
        self.card(g, "诸葛连弩", n)
        self.assertFalse(g.equip(n))
        self.assertFalse(n.equipment)
        g.check()

    def test_replacing_cloud_robe_respects_reduced_capacity(self):
        g = Game()
        w = g.players[0]
        self.card(g, "云锦袍", w, "equipment")
        # 利用转化模拟多件高价值装备，使云锦袍成为最先替换的装备。
        for _ in range(4):
            c = self.card(g, "杀", w, "equipment")
            c.name = "惊羽弓"
        replacement = self.card(g, "诸葛连弩", w)
        self.assertTrue(g.equip(w))
        self.assertIn(replacement, w.equipment)
        self.assertEqual(len(w.equipment), 3)
        g.check()

    def test_random_games_conserve_every_card(self):
        for seed in range(30):
            g = Game(seed)
            g.run(max_rounds=100, check=True)

    def test_sword_ignores_armor_and_seals_character(self):
        g = Game()
        w, n = g.players
        self.card(g, "轩辕剑", w, "equipment")
        self.card(g, "藤甲", n, "equipment")
        attack = self.card(g, "杀", w)
        g.attack(w, attack)
        self.assertEqual(n.hp, 5)
        self.assertTrue(n.silenced)
        spade = next(c for c in g.deck if c.suit == "♠")
        g.deck.remove(spade)
        g.gain(n, [spade])
        self.assertTrue(w.has("轩辕剑"))
        self.assertEqual(g.stats["甘宁拆牌触发"], 0)
        g.check()

    def test_first_pick_gives_one_card_to_each_player(self):
        g = Game(left="白板", right="白板")
        w, n = g.players
        tactic = self.card(g, "先拔头筹", w)
        g.tactic(w, tactic)
        self.assertEqual(len(w.hand), 1)
        self.assertEqual(len(n.hand), 1)
        g.check()

    def test_first_pick_countered_as_whole(self):
        g = Game()
        w, n = g.players
        tactic = self.card(g, "先拔头筹", w)
        self.card(g, "识破", n)
        before = len(g.deck)
        g.tactic(w, tactic)
        self.assertEqual(len(g.deck), before)
        self.assertFalse(w.hand)
        self.assertFalse(n.hand)
        g.check()

    def test_heal_full_hp_not_counterspell_target(self):
        g = Game()
        w, n = g.players
        c = self.card(g, "休养生息", w)
        counter = self.card(g, "识破", w)
        g.tactic(w, c)
        self.assertIn(counter, w.hand)

    def test_chain_transmits_element_once(self):
        g = Game()
        w, n = g.players
        w.chained = n.chained = True
        g.damage(w, n, 1, "fire")
        self.assertEqual((w.hp, n.hp), (5, 5))
        self.assertFalse(w.chained or n.chained)
        g.check()

    def test_ground_fire_hits_other_player_once(self):
        g = Game(left="白板", right="白板")
        w, n = g.players
        self.card(g, "地火", w, "delayed")
        top = next(c for c in g.deck if c.rank == 3)
        g.deck.remove(top)
        g.deck.append(top)
        with patch.object(w.character, "play_phase"):
            g.turn(0)
        self.assertEqual((w.hp, n.hp), (1, 2))
        g.check()

    def test_character_instances_are_independent(self):
        g = Game(left="甘宁", right="甘宁")
        left, right = g.players
        self.assertIsNot(left.character, right.character)
        left.character.phase_start()
        right.character.phase_start()
        left.character.washed = True
        self.assertFalse(right.character.washed)

    def duplicate(self, g, p, name, count, zone="equipment"):
        cards = []
        for _ in range(count):
            c = self.card(g, "杀", p, zone)
            c.name = name
            cards.append(c)
        return cards

    def test_repeated_equipment_can_mix_in_three_slots(self):
        g = Game()
        w = g.players[0]
        self.duplicate(g, w, "轩辕剑", 2, "hand")
        self.card(g, "凤羽盔", w)
        for _ in range(3): self.assertTrue(g.equip(w))
        self.assertEqual(w.count("轩辕剑"), 2)
        self.assertTrue(w.has("凤羽盔"))
        g.check()

    def test_two_fans_add_two_fire_damage(self):
        g = Game()
        w, n = g.players
        self.duplicate(g, w, "羽扇", 2)
        g.damage(w, n, 1, "fire")
        self.assertEqual(n.hp, 3)
        g.check()

    def test_two_helmets_increase_character_hand_limit_by_four(self):
        g = Game(left="白板", right="白板")
        w = g.players[0]
        self.duplicate(g, w, "凤羽盔", 2)
        for _ in range(7): self.card(g, "闪避", w)
        with patch.object(w.character, "play_phase"):
            g.turn(0)
        self.assertEqual(len(w.hand), w.base_hand_limit + 4)
        g.check()

    def test_two_cloud_robes_provide_seven_slots(self):
        g = Game()
        w = g.players[0]
        self.duplicate(g, w, "云锦袍", 2)
        self.duplicate(g, w, "轩辕剑", 5)
        self.assertEqual(g.slots(w), 7)
        with patch.object(g.rng, "choice", side_effect=lambda cards: cards[-1]):
            g.drop(w, w.equipment[0])
        self.assertEqual(len(w.equipment), g.slots(w))
        self.assertEqual(len(w.equipment), 5)
        g.check()

    def test_two_horses_draw_on_one_attack(self):
        g = Game()
        w, n = g.players
        self.duplicate(g, w, "乌骓", 2)
        attack = self.card(g, "杀", w)
        g.attack(w, attack)
        self.assertEqual(len(w.hand), 2)
        g.check()

    def test_spade_transform_only_offers_cloud_robe(self):
        g = Game(trace=True)
        w = g.players[0]
        c = self.card(g, "识破", w)
        self.assertTrue(w.character.transform(g, w))
        self.assertEqual(c.name, "云锦袍")
        self.assertEqual(c.suit, "♠")
        self.assertIn("候选['云锦袍']", g.log[0])
        self.assertFalse(w.equipment)
        g.check()

    def test_sword_seals_before_defense_even_when_dodged(self):
        g = Game()
        w, n = g.players
        self.card(g, "轩辕剑", w, "equipment")
        self.card(g, "绝影", n, "equipment")
        attack = self.card(g, "杀", w)
        self.card(g, "闪避", n)
        spade = next(c for c in g.deck if c.suit == "♠")
        g.deck.remove(spade)
        g.deck.append(spade)
        g.attack(w, attack)
        self.assertEqual(n.hp, 6)
        self.assertTrue(n.silenced)
        self.assertTrue(w.has("轩辕剑"))
        self.assertEqual(g.stats["甘宁拆牌触发"], 0)
        g.check()


if __name__ == "__main__": unittest.main()
