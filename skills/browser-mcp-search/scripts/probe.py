#!/usr/bin/env python3
"""MCP stdio 探针：启动 playwright MCP 并按顺序调用浏览器工具，打印结果。
响应到达即发下一步（不等满超时）；仅搜索类导航之间可加节流间隔。

用法: python3 probe.py <tool> [json_args] [更多 tool/args 对...]
环境: PW_MCP_SERVER    MCP 启动命令（默认 ~/.local/bin/pw-mcp-edge）
      PROBE_TOOL_TIMEOUT  单步等待上限秒数（默认 90）
      PROBE_GAP           每步额外间隔秒（默认 0；一般不需要）
示例: PW_MCP_SERVER=~/.local/bin/pw-mcp-bg python3 probe.py \
        browser_navigate '{"url":"https://www.xiaohongshu.com"}'
"""
import subprocess, json, sys, time, threading, os, tempfile

SERVER = os.environ.get("PW_MCP_SERVER") or os.path.expanduser("~/.local/bin/pw-mcp-edge")
TOOL_TIMEOUT = float(os.environ.get("PROBE_TOOL_TIMEOUT", "90"))
GAP = float(os.environ.get("PROBE_GAP", "0"))

# playwright-mcp 会往自身工作目录写 .playwright-mcp/ 日志；指到临时目录，
# 避免污染调用者所在目录（如本 skill 的 scripts/）。
p = subprocess.Popen([SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True, bufsize=1,
                     cwd=tempfile.gettempdir())

done_ids = set()
last_result = [""]
CLEANUP = os.environ.get("PROBE_CLEANUP", "1") != "0"
NAME = os.environ.get("PROBE_NAME", "probe")

def send(obj):
    p.stdin.write(json.dumps(obj) + "\n"); p.stdin.flush()

def reader():
    for line in p.stdout:
        line = line.strip()
        if not line: continue
        try: msg = json.loads(line)
        except Exception: print("RAW:", line[:300], flush=True); continue
        if "id" in msg:
            done_ids.add(msg["id"])
            if "result" in msg and "content" in (msg["result"] or {}):
                texts = [c.get("text", "") for c in msg["result"]["content"]]
                print(f"== TOOL RESULT (id={msg['id']}) ==", flush=True)
                for t in texts: print(t[:4000], flush=True)
                last_result[0] = "\n".join(texts)
            else:
                print(f"== RPC (id={msg['id']}) == {json.dumps(msg, ensure_ascii=False)[:600]}", flush=True)

threading.Thread(target=reader, daemon=True).start()
def err_reader():
    for line in p.stderr:
        print("STDERR:", line.rstrip()[:300], flush=True)
threading.Thread(target=err_reader, daemon=True).start()

send({"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":NAME,"version":"1.0"}}})
t0 = time.time()
while 0 not in done_ids and time.time() - t0 < 15: time.sleep(0.1)
send({"jsonrpc":"2.0","method":"notifications/initialized"})

pairs = sys.argv[1:] or ["browser_tabs", '{"action":"list"}']
for i in range(0, len(pairs), 2):
    tool = pairs[i]
    args = json.loads(pairs[i+1]) if i+1 < len(pairs) else {}
    rid = i // 2 + 1
    print(f"--> calling {tool} {json.dumps(args, ensure_ascii=False)}", flush=True)
    send({"jsonrpc":"2.0","id":rid,"method":"tools/call","params":{"name":tool,"arguments":args}})
    t0 = time.time()
    while rid not in done_ids and time.time() - t0 < TOOL_TIMEOUT:
        time.sleep(0.1)
    if rid not in done_ids:
        print(f"!! (id={rid}) 超时 {TOOL_TIMEOUT}s，继续下一步", flush=True)
    if GAP: time.sleep(GAP)

# 退出清理：关闭本会话标签（PROBE_CLEANUP=0 可禁用）
if CLEANUP:
    import re as _re
    cleanup_id = 9000
    send({"jsonrpc":"2.0","id":cleanup_id,"method":"tools/call","params":{"name":"browser_tabs","arguments":{"action":"list"}}})
    t0 = time.time()
    while cleanup_id not in done_ids and time.time() - t0 < 15: time.sleep(0.1)
    idxs = sorted((int(m) for m in _re.findall(r"^- (\d+):", last_result[0], _re.M)), reverse=True)
    for i in idxs:
        send({"jsonrpc":"2.0","id":cleanup_id+i,"method":"tools/call","params":{"name":"browser_tabs","arguments":{"action":"close","index":i}}})
    time.sleep(min(4, 0.5 + 0.5 * len(idxs)))

time.sleep(0.3)
p.kill()
