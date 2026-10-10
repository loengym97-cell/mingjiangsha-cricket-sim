"""批量任务与逐局记录存储；每局完整事件压缩保存到SQLite。"""
from collections import Counter
from datetime import datetime, timezone, timedelta
import csv
import hashlib
import html
import json
from pathlib import Path
import sqlite3
from statistics import mean
import zlib
from engine import Game, ROOT

DB = ROOT / "results.sqlite3"
REPORTS = ROOT / "reports"


def connect(db=DB):
    conn = sqlite3.connect(db, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY, created TEXT, status TEXT, params TEXT,
        rules TEXT, engine_hash TEXT, completed INTEGER DEFAULT 0, summary TEXT, error TEXT);
      CREATE TABLE IF NOT EXISTS games (
        run_id INTEGER, id INTEGER, seed INTEGER, winner TEXT, winner_side INTEGER,
        first_side INTEGER, rounds INTEGER, events INTEGER, detail BLOB,
        PRIMARY KEY (run_id,id));
      CREATE INDEX IF NOT EXISTS games_filter ON games(run_id,winner_side,first_side,id);
    """)
    return conn


def source_files():
    return [ROOT / name for name in ("engine.py", "characters.py", "deck.py", "rules.json")] + sorted((ROOT / "ai").rglob("*.py"))


def engine_hash():
    digest = hashlib.sha256()
    for path in source_files():
        digest.update(path.relative_to(ROOT).as_posix().encode('utf-8') + b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def run_batch(games=10000, seed=20261010, max_rounds=300, left="王濬", right="甘宁",
              db=DB, progress=None, left_ai="v1", right_ai="v1", left_version="v1", right_version="v1"):
    params = dict(games=games, seed=seed, max_rounds=max_rounds, left=left, right=right,
                  left_ai=left_ai, right_ai=right_ai, left_version=left_version, right_version=right_version)
    rules = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))
    created = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    version = engine_hash()
    # 连同批次保留实际源代码，未来修改当前文件也能复现此版本。
    frozen = Path(db).resolve().parent / "versions" / version
    frozen.mkdir(parents=True, exist_ok=True)
    for path in source_files():
        target = frozen / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        if target.exists() and target.read_bytes() != raw:
            raise RuntimeError("版本快照与现有文件不一致")
        target.write_bytes(raw)
    conn = connect(db)
    cursor = conn.execute("INSERT INTO runs(created,status,params,rules,engine_hash) VALUES(?,?,?,?,?)",
                          (created, "running", json.dumps(params, ensure_ascii=False),
                           json.dumps(rules, ensure_ascii=False), version))
    run_id = cursor.lastrowid
    conn.commit()
    outcomes = []
    try:
        for i in range(games):
            game_seed = seed + i // 2
            game = Game(game_seed, first=i % 2, trace=True, left=left, right=right,
                        left_ai=left_ai, right_ai=right_ai, left_version=left_version, right_version=right_version)
            result = game.run(max_rounds, check=True)
            detail = {"id": i+1, "seed": game_seed, "result": result, "events": game.events,
                      "final_state": game.snapshot()}
            packed = zlib.compress(json.dumps(detail, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 1)
            conn.execute("INSERT INTO games VALUES(?,?,?,?,?,?,?,?,?)",
                         (run_id, i+1, game_seed, result["winner"], result["winner_side"],
                          result["first_side"], result["rounds"], len(game.events), packed))
            outcomes.append(result)
            if (i+1) % 100 == 0 or i+1 == games:
                conn.execute("UPDATE runs SET completed=? WHERE id=?", (i+1, run_id))
                conn.commit()
                if progress: progress(run_id, i+1, games)
        counts = Counter(r["winner_side"] for r in outcomes)
        summary = {"run_id": run_id, "created": created, "status": "当前规则与AI下的模型结果，非实战胜率",
                   "params": params, "engine_hash": version, "counts": dict(counts),
                   "mean_rounds": mean(r["rounds"] for r in outcomes),
                   "by_first": {str(side): dict(Counter(r["winner_side"] for r in outcomes if r["first_side"] == side)) for side in (0,1)},
                   "stats": dict(sum((Counter(r["stats"]) for r in outcomes), Counter())),
                   "rules": rules}
        conn.execute("UPDATE runs SET status='complete',summary=? WHERE id=?",
                     (json.dumps(summary, ensure_ascii=False), run_id))
        conn.commit()
        export_reports(conn, summary, report_dir=Path(db).resolve().parent / "reports")
        return summary
    except Exception as exc:
        conn.execute("UPDATE runs SET status='failed', completed=?, error=? WHERE id=?",
                     (len(outcomes), str(exc), run_id))
        conn.commit()
        raise
    finally:
        conn.close()


def export_reports(conn, summary, report_dir=REPORTS):
    report_dir.mkdir(exist_ok=True)
    run_id = summary["run_id"]
    base = report_dir / f"run_{run_id}"
    base.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with base.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["局号", "种子", "胜者", "胜者座位", "先手座位", "轮数", "事件数"])
        writer.writerows(tuple(row) for row in conn.execute(
            "SELECT id,seed,winner,winner_side,first_side,rounds,events FROM games WHERE run_id=? ORDER BY id", (run_id,)))
    p = summary["params"]
    names = [p["left"], p["right"]]
    counts = summary["counts"]
    legacy = summary["rules"].get("revision", 0) < 4
    legacy_notice = "<p><strong>旧规则批次，距离等规则尚未修正，请以最新修正批次为准。</strong></p>" if legacy else ""
    legacy_deaths = counts.get(-1, counts.get('-1',0))
    deaths_text = f"；旧模型继续结算产生的双方死亡 {legacy_deaths} 局" if legacy_deaths else ""
    rows = []
    for side, name in enumerate(names):
        wins = counts.get(side, counts.get(str(side), 0))
        rows.append(f"<tr><td>{html.escape(name)}</td><td>{wins:,}</td><td>{wins/p['games']:.2%}</td></tr>")
    groups = []
    for side in (0,1):
        group = summary["by_first"][str(side)]
        total = sum(group.values())
        groups.append(f"<tr><td>{html.escape(names[side])}先手</td><td>{total:,}</td>" +
                      "".join(f"<td>{group.get(i, group.get(str(i), 0)):,}</td>" for i in (0,1)) + "</tr>")
    document = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>斗蛐蛐 · 第{run_id}批报告</title>
    <style>body{{font:16px/1.7 system-ui,'Microsoft YaHei',sans-serif;color:#20212a;background:#fff;max-width:900px;margin:48px auto;padding:0 24px}}h1{{font-size:28px}}table{{width:100%;border-collapse:collapse;margin:20px 0}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}details{{margin:24px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 system-ui}}a{{color:#4637a4}}</style>
    <h1>{html.escape(names[0])} vs {html.escape(names[1])}</h1><p>第{run_id}批 · {p['games']:,}局 · {html.escape(summary['created'])}</p>
    {legacy_notice}<p><strong>当前规则与AI下的模型结果，非实战胜率。</strong>平均 {summary['mean_rounds']:.2f} 轮结束。</p>
    <table><tr><th>武将</th><th>获胜局数</th><th>占全部对局</th></tr>{''.join(rows)}</table>
    <p>未结束 {counts.get(-2, counts.get('-2',0))} 局{deaths_text}。</p>
    <table><tr><th>先手</th><th>总局数</th><th>{html.escape(names[0])}获胜</th><th>{html.escape(names[1])}获胜</th></tr>{''.join(groups)}</table>
    <p>策略：左侧 {html.escape(p.get('left_ai','v1'))} / 技能 {html.escape(p.get('left_version','v1'))}；右侧 {html.escape(p.get('right_ai','v1'))} / 技能 {html.escape(p.get('right_version','v1'))}。</p>
    <p>随机种子 {p['seed']}；回合上限 {p['max_rounds']}；引擎版本指纹 {summary['engine_hash']}。</p>
    <p><a href="http://127.0.0.1:8765/?run={run_id}">打开逐局可视化界面</a>（先运行同目录上级的“打开斗蛐蛐.bat”）。</p>
    <p>全部逐局状态与事件保存在 results.sqlite3。<a href="run_{run_id}.csv">下载逐局结果表</a> · <a href="run_{run_id}.json">查看汇总数据</a></p>
    <details><summary>本次规则与假设快照</summary><pre>{html.escape(json.dumps(summary['rules'],ensure_ascii=False,indent=2))}</pre></details>
    </html>"""
    base.with_suffix(".html").write_text(document, encoding="utf-8")


def get_run(conn, run_id=None):
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone() if run_id else conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if not row: return None
    result = dict(row)
    for key in ("params", "rules", "summary"):
        result[key] = json.loads(result[key]) if result[key] else None
    return result


def get_detail(conn, run_id, game_id):
    row = conn.execute("SELECT detail FROM games WHERE run_id=? AND id=?", (run_id, game_id)).fetchone()
    return json.loads(zlib.decompress(row[0])) if row else None
