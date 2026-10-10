import json
from pathlib import Path
import tempfile
import unittest
from batch import connect, get_detail, get_run, run_batch
from engine import Game


class BatchTests(unittest.TestCase):
    def test_every_game_is_saved_and_can_be_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "results.sqlite3"
            result = run_batch(6, seed=1729, db=db)
            conn = connect(db)
            try:
                run = get_run(conn, result["run_id"])
                self.assertEqual(run["status"], "complete")
                self.assertEqual(run["completed"], 6)
                for i in range(1, 7):
                    detail = get_detail(conn, run["id"], i)
                    game = Game(1729+(i-1)//2, first=(i-1)%2, trace=True)
                    expected = game.run(check=True)
                    self.assertEqual(detail["result"], expected)
                    self.assertEqual(detail["events"], game.events)
                    self.assertEqual(detail["final_state"], game.snapshot())
                    self.assertGreater(len(detail["events"]), 1)
                self.assertIsNone(get_detail(conn, run["id"], 7))
                self.assertTrue((Path(directory)/"reports"/"run_1.html").exists())
                frozen=Path(directory)/'versions'/result['engine_hash']
                self.assertTrue((frozen/'ai'/'王濬'/'v3.py').exists())
                self.assertTrue((frozen/'ai'/'甘宁'/'v7.py').exists())
                self.assertFalse((frozen/'ai.py').exists())
            finally:
                conn.close()

    def test_snapshot_does_not_change_with_future_actions(self):
        g = Game(trace=True)
        g.note("before")
        before = json.dumps(g.events[0], sort_keys=True)
        g.draw(g.players[0], 3)
        self.assertEqual(json.dumps(g.events[0], sort_keys=True), before)


if __name__ == "__main__": unittest.main()
