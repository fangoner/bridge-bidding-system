import json
import subprocess
import time
import os
import sys
import base64
import re

import requests
import websocket


def find_browser():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise RuntimeError("no browser found")


class CDP:
    def __init__(self, port, url):
        self.port = port
        self.url = url
        self.proc = None
        self.ws = None
        self.msg_id = 0

    def start(self):
        user_data = os.path.join(os.environ["TEMP"], "trae",
                                 "cdp-batch-%d-%d" % (self.port, int(time.time() * 1000)))
        chrome = find_browser()
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
               f"--remote-debugging-port={self.port}", f"--user-data-dir={user_data}",
               "--remote-allow-origins=*", "--hide-scrollbars",
               "--window-size=1920,1080", self.url]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                r = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=2)
                for p in r.json():
                    if p.get("type") == "page":
                        self.ws = websocket.create_connection(p["webSocketDebuggerUrl"], timeout=180)
                        self.send("Page.enable")
                        self.send("Runtime.enable")
                        self.send("Emulation.setDeviceMetricsOverride",
                                  {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False})
                        return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def send(self, method, params=None):
        self.msg_id += 1
        req_id = self.msg_id
        self.ws.send(json.dumps({"id": req_id, "method": method, "params": params or {}}))
        while True:
            data = json.loads(self.ws.recv())
            if data.get("id") == req_id:
                return data

    def shot_id(self):
        self.msg_id += 1
        req_id = self.msg_id
        self.ws.send(json.dumps({"id": req_id, "method": "Page.captureScreenshot",
                                 "params": {"format": "png", "captureBeyondViewport": True, "fromSurface": True}}))
        while True:
            data = json.loads(self.ws.recv())
            if data.get("id") == req_id:
                return data

    def eval(self, js):
        r = self.send("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
        return r.get("result", {}).get("result", {}).get("value")

    def rect(self, selector, text):
        js = ("JSON.stringify((function(){"
              "var els=Array.from(document.querySelectorAll('" + selector + "'));"
              "var exact=els.filter(function(e){return (e.textContent||'').trim()===" + json.dumps(text) + ";});"
              "var e=exact.length?exact[0]:null;"
              "if(!e)return null;"
              "var r=e.getBoundingClientRect();"
              "return {x:r.x+r.width/2,y:r.y+r.height/2};"
              "})())")
        v = self.eval(js)
        if v:
            try:
                return json.loads(v)
            except Exception:
                return None
        return None

    def click_real(self, x, y):
        self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

    def shot(self, out_path):
        try:
            data = self.shot_id()
            if "result" in data and "data" in data["result"]:
                png = base64.b64decode(data["result"]["data"])
                with open(out_path, "wb") as f:
                    f.write(png)
                return f"saved {out_path} {len(png)} bytes"
            return f"shot error: {data}"
        except Exception as e:
            return f"shot failed: {e}"

    def close(self):
        # 关闭 websocket：websocket-client 的 close() 会等待对端关闭帧，可能阻塞
        # 导致脚本收尾挂住，故全部用短超时 try 包裹，绝不阻塞。
        try:
            if self.ws:
                self.ws.sock.settimeout(1)
                self.ws.close()
        except Exception:
            pass
        try:
            if self.proc:
                self.proc.terminate()
                try:
                    self.proc.wait(3)
                except Exception:
                    try:
                        self.proc.kill()
                        self.proc.wait(3)
                    except Exception:
                        pass
        except Exception:
            pass


# ── 通用 DOM 操作：在页面 JS 内执行，返回字符串结果 ──
# 注意：不能包 JSON.stringify —— CDP returnByValue 会把字符串正确序列化为 JS string，
# 包了反而让返回值带上引号（'"CLICKED"'），导致 click_when 的 startswith 判断永远失败，
# 点击实际成功但被误判为未找到（修复于 2026-08-14）。

def _js_click_by_text(text, contains, nth, selector):
    return ("(function(){"
            "var els=Array.from(document.querySelectorAll('" + selector + "'));"
            "var exact=els.filter(function(e){return (e.textContent||'').trim()===" + json.dumps(text) + ";});"
            "var hit=exact.length?exact:(els.filter(function(e){return (e.textContent||'').trim().includes(" + json.dumps(text) + ");}));"
            "if(!hit.length){return 'NOT_FOUND&n='+els.length;}"
            "hit[" + str(nth) + "].dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));"
            "hit[" + str(nth) + "].dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0}));"
            "hit[" + str(nth) + "].dispatchEvent(new MouseEvent('click',{bubbles:true,button:0}));"
            "return 'CLICKED';"
            "})()")


def click_when(cdp, text, timeout, contains=True, nth=0, selector="button"):
    """等待元素出现并点击，返回结果字符串"""
    start = time.time()
    last = "TIMEOUT"
    while time.time() - start < timeout:
        js = _js_click_by_text(text, contains, nth, selector)
        last = cdp.eval(js)
        if isinstance(last, str) and last.startswith("CLICKED"):
            return last
        time.sleep(1)
    return last


def click_combobox(cdp, display_text, timeout=15):
    """点击显示文本为 display_text 的 MUI Select (combobox)"""
    start = time.time()
    last = "TIMEOUT"
    while time.time() - start < timeout:
        js = ("(function(){"
              "var els=Array.from(document.querySelectorAll('[role=combobox]'));"
              "var hit=els.filter(function(e){return (e.textContent||'').trim()===" + json.dumps(display_text) + ";});"
              "if(!hit.length){return 'NOT_FOUND&n='+els.length;}"
              "var el=hit[0];"
              "el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));"
              "el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0}));"
              "el.dispatchEvent(new MouseEvent('click',{bubbles:true,button:0}));"
              "el.focus();return 'CLICKED';"
              "})()")
        last = cdp.eval(js)
        if isinstance(last, str) and last.startswith("CLICKED"):
            return last
        time.sleep(1)
    return last


def click_option(cdp, text, timeout=10):
    """点击 MUI 菜单项 (role=option)"""
    start = time.time()
    last = "TIMEOUT"
    while time.time() - start < timeout:
        js = ("(function(){"
              "var els=Array.from(document.querySelectorAll('[role=option]'));"
              "var exact=els.filter(function(e){return (e.textContent||'').trim()===" + json.dumps(text) + ";});"
              "var hit=exact.length?exact:els.filter(function(e){return (e.textContent||'').trim().includes(" + json.dumps(text) + ");});"
              "if(!hit.length){return 'NOT_FOUND&n='+els.length;}"
              "var el=hit[0];"
              "el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));"
              "el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0}));"
              "el.dispatchEvent(new MouseEvent('click',{bubbles:true,button:0}));"
              "return 'CLICKED';"
              "})()")
        last = cdp.eval(js)
        if isinstance(last, str) and last.startswith("CLICKED"):
            return last
        time.sleep(1)
    return last


def click_real_when(cdp, selector, text, timeout=15):
    """用真实鼠标事件点击元素（对 MUI Select/MenuItem 可靠触发 React onChange）"""
    start = time.time()
    while time.time() - start < timeout:
        r = cdp.rect(selector, text)
        if r:
            cdp.click_real(r["x"], r["y"])
            return "CLICKED:" + text + " " + str(r)
        time.sleep(1)
    return "TIMEOUT:" + text


def set_select(cdp, combobox_text, option_text, timeout=15):
    """点开当前显示为 combobox_text 的 MUI Select，再选 option_text。
    用真实鼠标事件（可靠触发 React onChange）。comboBox 按当前值文本定位，
    因 MUI InputLabel 的 id 为空，标签关联不可靠。"""
    start = time.time()
    while time.time() - start < timeout:
        res = click_real_when(cdp, "[role=combobox]", combobox_text, timeout=timeout)
        if res.startswith("CLICKED"):
            time.sleep(0.8)
            opt = click_real_when(cdp, "[role=option]", option_text, timeout=timeout)
            return opt.startswith("CLICKED")
        time.sleep(1)
    return False


def set_toggle(cdp, button_text, timeout=10):
    """点击 ToggleButtonGroup 中指定按钮（真实鼠标）"""
    return click_real_when(cdp, "button", button_text, timeout=timeout).startswith("CLICKED")


def switch_tab(cdp, tab_text, timeout=10):
    """切换设置面板 Tab"""
    return click_real_when(cdp, "[role=tab]", tab_text, timeout=timeout).startswith("CLICKED")


def read_comboboxes(cdp):
    return cdp.eval("JSON.stringify(Array.from(document.querySelectorAll('[role=combobox]')).map(function(e){return e.textContent.trim();}))")


def body_text(cdp):
    return cdp.eval("document.body.innerText")


def wait_for_body(cdp, keyword, timeout, interval=3):
    start = time.time()
    while time.time() - start < timeout:
        t = body_text(cdp) or ""
        if keyword in t:
            return True, t
        time.sleep(interval)
    return False, body_text(cdp) or ""


def extract_contract(t):
    # "Contract: 3NT-North     643 ..." → 只取 "3NT-North"（\S+ 不含尾部手牌余料）
    m = re.search(r'Contract:\s*(\S+)', t)
    if m:
        return m.group(1).strip()
    return None


def extract_bidding_seq(t):
    m = re.search(r'叫牌过程[：:]\s*([^\n]*)', t)
    if m:
        return m.group(1).strip()
    return None


def extract_result(t):
    # 优先匹配结果区"超 N/宕 N"（含空格），其次 完成/Result，最后完整分数（如 +150，避免误取 +1）
    m = re.search(r'(超\s*\d+|宕\s*\d+|完成|Result|[+-]\d+)', t)
    if m:
        return m.group(0).strip()
    return None


def configure_settings(cdp, deal_mode="进局"):
    """流利操作设置面板：配置发牌模式、打牌引擎与LLM审查开关。
    全部用真实鼠标事件触发 React onChange，逐项验证，全程仅一次执行。
    deal_mode: 自由/进局/满贯"""
    s = "button,[role=tab],[role=combobox],[role=option]"
    print("  [设置] 打开设置面板:", click_real_when(cdp, s, "设置", timeout=20))
    time.sleep(1.2)

    # 发牌设置 tab：发牌(当前"自由") -> deal_mode
    print("  [设置] 切到发牌设置:", switch_tab(cdp, "发牌设置"))
    time.sleep(1.2)
    print(f"  [设置] 发牌 -> {deal_mode}:", set_select(cdp, "自由", deal_mode))
    time.sleep(1.5)

    # 打牌设置 tab：引擎(当前"DD-αμ-LLM") -> DD-αμ-LLM，审查 -> 纯引擎（不开审查）
    print("  [设置] 切到打牌设置:", switch_tab(cdp, "打牌设置"))
    time.sleep(1.2)
    print("  [设置] 打牌引擎 -> DD-αμ-LLM:", set_select(cdp, "DD-αμ-LLM", "DD-αμ-LLM"))
    time.sleep(1.5)
    print("  [设置] 审查 -> 纯引擎:", set_toggle(cdp, "纯引擎"))
    time.sleep(0.5)

    print("  [设置] 当前下拉值:", read_comboboxes(cdp))
    print("  [设置] 关闭设置面板:", click_real_when(cdp, s, "隐藏设置", timeout=15))
    time.sleep(1.2)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9250
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    outdir = "c:/Users/Fanyi/AppData/Local/Temp/trae/batch20_game"
    os.makedirs(outdir, exist_ok=True)
    cdp = CDP(port, "http://localhost:5173")
    if not cdp.start():
        print("FAILED to start cdp browser")
        return
    time.sleep(3)

    # 一步到位配置设置面板：发牌=满贯，打牌引擎=DD-αμ-LLM，审查=纯引擎（不开）
    # 全程只执行一次，之后不刷新页面，配置保持
    configure_settings(cdp, deal_mode="满贯")

    results = []
    for board in range(1, n + 1):
        rec = {"board": board, "start": time.strftime("%H:%M:%S")}
        print(f"=== BOARD {board} ===")
        ok = False
        for attempt in range(1, 6):
            print(f"  attempt {attempt}")
            print("  发牌:", click_when(cdp, "发牌", timeout=30, contains=False, selector="button"))
            time.sleep(4)
            print("  开始叫牌:", click_when(cdp, "开始叫牌", timeout=30, selector="button"))
            time.sleep(2)
            b_ok, t = wait_for_body(cdp, "Contract:", timeout=180)
            rec["bidding_text"] = t
            if not b_ok:
                print("  bidding not done -> re-deal")
                click_when(cdp, "重新叫牌", timeout=15, selector="button")
                time.sleep(2)
                continue
            rec["contract"] = extract_contract(t)
            rec["bidding_seq"] = extract_bidding_seq(t)
            print("  contract:", rec["contract"])
            # 流程：叫牌结束后点"切换到打牌"激活"确认定约与首攻"对话框；
            # 对话框"开始打牌"→ doPlayInit（初始化面板，playInitiated=false）；
            # 随后面板顶部还会出现"开始打牌"按钮 → handleBeginPlay（真正开始出牌）。
            # 两步必须分别点击，否则打牌停留在初始化状态（等待 13/13 将超时）。
            print("  切换到打牌:", click_when(cdp, "切换到打牌", timeout=15, selector="button"))
            time.sleep(2)
            dlg_ok, t1 = wait_for_body(cdp, "确认定约与首攻", timeout=15, interval=1)
            if not dlg_ok:
                print("  确认对话框未出现 -> re-deal")
                click_when(cdp, "取消", timeout=5, selector="button")
                time.sleep(2)
                continue
            if "未检测到定约" in t1:
                print("  NO CONTRACT -> re-deal")
                click_when(cdp, "取消", timeout=15, selector="button")
                time.sleep(2)
                continue
            print("  确认定约(对话框):", click_when(cdp, "开始打牌", timeout=15, selector="button"))
            time.sleep(2)
            # 第二步：等打牌面板出现后点顶部"开始打牌"（此时对话框已关闭，不会误点）
            print("  开始出牌(面板):", click_when(cdp, "开始打牌", timeout=15, selector="button"))
            time.sleep(2)
            p_ok, t2 = wait_for_body(cdp, "13/13", timeout=1200)
            if not p_ok:
                # 兜底：完成态面板显示"打牌总耗时"（旧文案"打牌已结束"已随 PlayPanel 弃用失效）
                p_ok, t2 = wait_for_body(cdp, "打牌总耗时", timeout=60)
            rec["play_text"] = t2
            rec["result"] = extract_result(t2)
            rec["end"] = time.strftime("%H:%M:%S")
            ok = True
            break
        rec["ok"] = ok
        results.append(rec)
        with open(os.path.join(outdir, "board_%02d.json" % board), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        time.sleep(2)

    # 收尾：先在 finally 中兜底写入 results.json，再做可能阻塞的浏览器关闭，
    # 保证即使 close() 卡住，统计数据也已落盘。
    try:
        with open(os.path.join(outdir, "results.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("DONE ALL BOARDS", flush=True)
    finally:
        try:
            cdp.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()