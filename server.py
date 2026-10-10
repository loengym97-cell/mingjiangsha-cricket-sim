"""仅绑定本机的可视化服务，运行与查询均不需要联网。"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlparse
from batch import DB, ROOT, connect, get_detail, get_run, run_batch
from characters import REGISTRY, SKILL_VERSIONS
from ai import AI_REGISTRY, AI_LABELS, AI_CHOICES

JOB = {"running": False, "completed": 0, "total": 0, "run_id": None, "error": None}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        def number(name, default=0): return int(q.get(name, [default])[0])
        try:
            if parsed.path.startswith("/api/"):
                conn = connect(self.server.db)
                try:
                    run_id = number("run")
                    if parsed.path == "/api/status":
                        with LOCK: job = dict(JOB)
                        return self.respond({"app": "cricket-sim", "job": job, "run": get_run(conn, run_id),
                                             "characters": list(REGISTRY), "ai_versions": AI_LABELS,
                                             "ai_choices": AI_CHOICES, "skill_versions": SKILL_VERSIONS})
                    if parsed.path == "/api/runs":
                        return self.respond([dict(r) for r in conn.execute(
                            "SELECT id,created,status,completed,params FROM runs ORDER BY id DESC LIMIT 30")])
                    if parsed.path == "/api/games":
                        clauses = ["run_id=?"]
                        values = [run_id]
                        for name, column in (("winner", "winner_side"), ("first", "first_side"), ("game", "id")):
                            if name in q and q[name][0] != "":
                                clauses.append(column + "=?"); values.append(number(name))
                        where = " AND ".join(clauses)
                        page = max(1, number("page", 1))
                        total = conn.execute("SELECT COUNT(*) FROM games WHERE " + where, values).fetchone()[0]
                        rows = conn.execute("SELECT id,seed,winner,winner_side,first_side,rounds,events FROM games WHERE " + where +
                                            " ORDER BY id LIMIT 50 OFFSET ?", values + [(page-1)*50]).fetchall()
                        return self.respond({"total": total, "page": page, "rows": [dict(r) for r in rows]})
                    if parsed.path == "/api/detail":
                        detail = get_detail(conn, run_id, number("game"))
                        return self.respond(detail if detail else {"error": "找不到这局记录"}, 200 if detail else 404)
                    return self.respond({"error": "接口不存在"}, 404)
                finally:
                    conn.close()
            filename = {"/": "ui.html", "/app.js": "app.js", "/style.css": "style.css"}.get(parsed.path)
            if filename:
                path = ROOT / filename
            elif parsed.path.startswith("/reports/"):
                reports = Path(self.server.db).resolve().parent / "reports"
                path = (reports / parsed.path.removeprefix("/reports/")).resolve()
                if not path.is_relative_to(reports):
                    return self.respond({"error": "路径无效"}, 400)
            else:
                return self.respond({"error": "页面不存在"}, 404)
            if not path.is_file(): return self.respond({"error": "文件不存在"}, 404)
            raw = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(str(path))[0] or "application/octet-stream") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (ValueError, TypeError):
            self.respond({"error": "参数格式无效"}, 400)
        except Exception as exc:
            self.respond({"error": str(exc)}, 500)

    def do_POST(self):
        if self.path not in {"/api/run", "/api/shutdown"}: return self.respond({"error": "接口不存在"}, 404)
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
            return self.respond({"error": "仅允许本地工作台提交"}, 403)
        if self.path == "/api/shutdown":
            with LOCK:
                if JOB['running']: return self.respond({'error':'模拟正在运行，请完成后再重启'},409)
                JOB['running'] = True  # 停机期间不再接受新任务。
            self.respond({'stopping':True})
            threading.Thread(target=self.server.shutdown,daemon=True).start()
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096: raise ValueError("请求内容无效")
            params = json.loads(self.rfile.read(length))
            games = int(params.get("games", 10000))
            seed = int(params.get("seed", 20261010))
            rounds = int(params.get("max_rounds", 300))
            left, right = params.get("left", "王濬"), params.get("right", "甘宁")
            if not 1 <= games <= 100000: raise ValueError("局数应为1到100000")
            if not 1 <= rounds <= 1000: raise ValueError("回合上限应为1到1000")
            if not 0 <= seed <= 2**53-1: raise ValueError("种子应为0到9007199254740991")
            if left not in REGISTRY or right not in REGISTRY: raise ValueError("武将不存在")
            variants = {key: params.get(key, "v1") for key in ("left_ai", "right_ai", "left_version", "right_version")}
            if variants['left_ai'] not in AI_REGISTRY.get(left, {'v1': None}) or variants['right_ai'] not in AI_REGISTRY.get(right, {'v1': None}):
                raise ValueError("所选武将没有这个AI版本")
            if any(variants[key] not in SKILL_VERSIONS for key in ("left_version", "right_version")): raise ValueError("技能版本不存在")
        except (ValueError, TypeError, AttributeError) as exc:
            return self.respond({"error": str(exc)}, 400)
        with LOCK:
            if JOB["running"]: return self.respond({"error": "已有任务正在运行"}, 409)
            JOB.update(running=True, completed=0, total=games, run_id=None, error=None)
        def progress(run_id, completed, total):
            with LOCK: JOB.update(run_id=run_id, completed=completed, total=total)
        def worker():
            try:
                result = run_batch(games, seed, rounds, left, right, db=self.server.db, progress=progress, **variants)
                with LOCK: JOB.update(run_id=result["run_id"], completed=games)
            except Exception as exc:
                with LOCK: JOB["error"] = str(exc)
            finally:
                with LOCK: JOB["running"] = False
        threading.Thread(target=worker, daemon=True).start()
        self.respond({"started": True}, 202)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(DB))
    args = parser.parse_args()
    with connect(args.db) as conn:
        conn.execute("UPDATE runs SET status='interrupted',error='服务中断，已完成的逐局记录仍保留' WHERE status='running'")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.db = args.db
    print(f"http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__": main()
