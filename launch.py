"""启动本地服务并打开浏览器。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8765"


def ready():
    try:
        with urlopen(URL + "/api/status", timeout=1) as response:
            return json.load(response).get("app") == "cricket-sim"
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="打开本地斗蛐蛐工作台")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--restart',action='store_true',help='空闲时重启服务，加载修改后的AI')
    actions.add_argument('--stop',action='store_true',help='空闲时关闭后台服务，保留全部数据')
    args = parser.parse_args()
    if (args.restart or args.stop) and ready():
        try:
            with urlopen(Request(URL+'/api/shutdown',data=b'{}',headers={'Content-Type':'application/json'}),timeout=3): pass
        except Exception as exc:
            raise RuntimeError('无法关闭服务：请确认模拟已经结束。若为旧版服务，请先关闭旧服务再打开。') from exc
        for _ in range(50):
            if not ready(): break
            time.sleep(.1)
        else: raise RuntimeError('旧服务尚未退出，请稍后重试。')
    if args.stop:
        print('斗蛐蛐后台服务已关闭，所有已保存数据保留。',flush=True)
        return
    if not ready():
        with (ROOT / "server.log").open("a", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=ROOT,
                             stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        for _ in range(50):
            if ready(): break
            time.sleep(.1)
        else: raise RuntimeError("启动失败，请查看同目录server.log；8765端口可能已被占用")
    print(f'工作台已启动：{URL}',flush=True)
    print('关闭浏览器后可再次双击入口，已保存的对局不会丢失。',flush=True)
    if not webbrowser.open(URL): print('浏览器未自动打开，请复制上面的地址到浏览器。',flush=True)


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f'打开失败：{exc}',file=sys.stderr)
        sys.exit(1)
