import json
import base64
import time
import io
import re
from typing import Optional, Dict, Any

# ── JSON 清理：豆包模型可能返回含未转义控制字符的 JSON ──
def _sanitize_json(text):
    """转义 JSON 字符串值内的控制字符（\\n \\r \\t 等）。

    豆包 Seed 模型的 response_format 实现有时不转义字符串值内的换行符，
    导致 Python 的 json.loads() 报 "Invalid control character" 错误。
    此函数用状态机追踪引号内/外，安全替换控制字符。
    """
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\':
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            elif ord(ch) < 0x20:
                result.append(f'\\u{ord(ch):04x}')
            else:
                result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)
from openai import OpenAI

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_VISION_ENDPOINT

# 视觉识别最大图片尺寸（长边像素），超过会等比缩放
VISION_MAX_IMAGE_SIZE = 1920
# 视觉识别 JPEG 压缩质量（1-100）
VISION_JPEG_QUALITY = 85


VISION_PROMPT = """你的任务是从桥牌游戏图片中提取四项关键信息。四项同等重要，必须尽力完整提取。

═══════════════════════════════════════
一、手牌（最高优先级）
═══════════════════════════════════════
- **牌面10必须用T表示**，例如：♠KT85 而不是 ♠K1085
- **每手牌必须正好13张**，这是一个严格的校验规则
- 花色符号用 ♠ ♥ ♦ ♣，牌面从大到小排列（A K Q J T 9 8 7 6 5 4 3 2）
- **缺门花色必须用"-"占位**，例如：♠KT85 ♥AT863 ♦- ♣63（方块缺门）
- 四个花色必须按♠♥♦♣顺序全部列出，即使缺门也不能省略
- 检查每种花色是否有正确的牌张数（每种花色最多13张）
- 如果某手牌不足13张或总张数超过13，仔细复查图片
- 注意区分相似字符：♠和♣、8和B、T和7

**严禁脑补——这是最高纪律！**
- **只输出图片中实际可见的手牌**，图片中没有显示的玩家手牌一律输出为 null
- **绝不**根据叫牌过程、定约、HCP推断或编造任何手牌
- **绝不**为了让四家凑齐52张而虚构未显示位置的手牌
- **绝不**参考"标准自然/JF叫牌体系的合理持牌"等先验知识来填充缺失手牌
- 例如：图片只显示南北两家手牌，东西家未显示 → 东家手牌和西家手牌都必须输出 null
- 例如：图片只显示南家手牌，其他三家未显示 → 西家手牌/北家手牌/东家手牌都输出 null
- 即使图片只显示一家手牌，也要如实输出，其他三家为 null，由后续流程处理

═══════════════════════════════════════
二、叫牌序列
═══════════════════════════════════════
- **叫牌表中空着的位置不等于pass！** 第一轮中，发牌人之前的空位只是还没轮到叫牌，不要记录为pass
- **pass 的多种表示形式**：pass 可能显示为"不叫"、"-"、"/"、"Pass"、"P"、"pass"等，这些都是pass，必须记录为"pass"。与之区别的是**完全空白的格子**（无任何字符），那才是未叫牌，不能记录
- **叫品标准化**：无论图片中显示的是"不叫"、"-"、"/"、"P"，输出JSON时统一写成"pass"
- **"=" 是叫牌结束标记**：最后一个pass后面有时会带"="符号（如"pass="、"P="、"-"=），表示叫牌到此结束。遇到带"="的叫品，仍然按pass处理，但**输出JSON时去掉"="符号**，只写"pass"。不要单独输出"="作为一条叫品
- **发牌人（dealer）的判断方法——极其重要！**：
  - 叫牌表第一行中，**第一个有内容（pass/不叫/-//具体叫品）的位置就是发牌人**
  - **绝不能跳过发牌人！** 即使发牌人pass，也必须从发牌人开始记录序列
  - 即使第一行的"-"/"P"/"不叫"看起来像"空"，那也是发牌人发出的pass，必须记录
  * 例如第一行南为空白、西为空白、北为"-"、东为"1H" → 发牌人是北（北pass），序列从北的pass开始：["北:pass", "东:1H", ...]
  * 例如第一行南为空白、西为空白、北为空白、东为"-" → 发牌人是东（东pass），序列从东的pass开始：["东:pass", ...]
  * 例如第一行南为"-"、西为"1S"、北为空白、东为空白 → 发牌人是南（南pass），序列从南的pass开始：["南:pass", "西:1S", ...]
  * 例如第一行东为"-"、南为"1NT"、西为"pass"、北为"3NT" → 发牌人是东（东pass），序列：["东:pass", "南:1NT", "西:pass", "北:3NT", ...]
- **从发牌人开始**，按顺时针方向（南→西→北→东→南→...）依次记录每个位置的叫品
- **只记录叫牌表中有内容的格子**（pass/不叫/-//具体叫品），完全空白的格子一律跳过
- 如果整个叫牌表第一行全空，则查看图片中是否有"发牌"或dealer标注来确定起始位置
- 所有实际存在的叫品都必须记录，包括pass
- 最终定约叫品之后通常还有三个pass结束叫牌，也可能有加倍/再加倍
- 仔细观察叫牌区域，每个叫品框通常有位置标签，不要混淆相邻位置的叫品
- 如果图片中没有叫牌区域或叫牌序列完全不显示，则为null

**BBO/桥友圈等平台的叫牌表识别要点**：
- 叫牌表通常是**纵向排列**的，每一行代表一轮叫牌，列代表方位（北/东/南/西 或 N/E/S/W）
- **必须按行从上到下识别**，每一行从左到右依次读取4个位置的叫品
- **同一轮叫牌中，每个位置只能出现一次**！如果识别到同一位置在同一轮中出现两次，说明识别错误
- **每个位置（南/西/北/东）的叫品总数应基本相等**（相差不超过1），如果某位置叫品数远多于其他位置，说明识别错误
- **后续轮次的叫品必须比前一轮叫品阶数更高**（同类花色），如果识别到叫品阶数倒退，说明识别错误
- **同一玩家不可能连续叫两次**（中间必须隔其他玩家），如果出现连续两次同位置叫品，说明识别错误
- 识别时请仔细核对每个格子的位置标签（N/E/S/W 或 北/东/南/西），不要把列看错
- 如果叫牌表区域较小或模糊，优先识别能看清的部分，不要猜测不清晰的叫品

═══════════════════════════════════════
三、当前定约（重要！）
═══════════════════════════════════════
定约通常显示在以下位置之一：
  - 牌桌中央上方或偏右的醒目位置
  - 叫牌区域旁边的定约框/栏
  - 牌局信息面板中
  - 通常用较大字体或加粗显示

格式要求：
  - 定约格式为"级别花色 由庄家位置做庄"
  - 级别1-7，花色为C/D/H/S/NT（S=黑桃 H=红心 D=方块 C=草花 NT=无将）
  - 加倍用X表示，再加倍用XX表示
  - 示例："4H 由南做庄"、"3NT 由北做庄"、"2SX 由西做庄"、"2HXX 由东做庄"

提取技巧：
  - 即使图片中显示的是花色符号（♠♥♦♣），也请转换为字母（S/H/D/C）
  - 如果看到"NS"或"南北"可能是庄家阵营标注
  - 如果定约区域显示为空白或不存在，才返回null
  - 不要因为不确定而轻易返回null；只要有显示就尝试提取

═══════════════════════════════════════
四、首攻牌张
═══════════════════════════════════════
首攻是庄家左手边防守方打出的第一张牌，是打牌阶段的第一张出牌。

识别要点：
  - 首攻牌张通常位于牌桌中央，可能单独显示或带有标记
  - 注意区分首攻（单独一张）和后续打出的牌（多张已打出）
  - 如果多张牌已经打出（牌桌上已有4张牌），说明打牌已经开始多轮，此时首攻可能在打出牌的历史中
  - 如果只有一张牌在桌面中央，且其他位置还没有出牌，这张牌就是首攻

格式要求：
  - 格式为"位置:花色+牌面"，花色用S/H/D/C表示
  - 示例："西:S5"表示西家首攻黑桃5，"北:DK"表示北家首攻方块K
  - 只有一张牌的缩写：A=ACE K=KING Q=QUEEN J=JACK T=10，其余用数字

什么时候返回null：
  - 图片中尚未开始打牌（没有首攻显示）
  - 打牌已经开始但无法确定哪张是首攻
  - 牌桌中央没有任何出牌

═══════════════════════════════════════
五、局况（Vulnerability）
═══════════════════════════════════════
局况是桥牌的基础元素，影响叫牌决策。桥牌有四种局况：

识别要点：
  - 通常在牌桌上方/角落以缩写或颜色显示
  - BBO/新睿：以"NS"/"EW"/"Both"/"None"或红绿配色标识
  - 桥友圈：以中文"双无"/"南北有局"/"东西有局"/"双有"标识
  - 桥牌书籍：可能在牌局标题旁标注"None vul"/"NS vul"/"EW vul"/"Both vul"
  - 红色 = 有局，绿色 = 无局

格式要求（必须输出以下四个值之一）：
  - "NV" = 双无局（None Vulnerable）
  - "NS" = 南北有局（North-South Vulnerable）
  - "EW" = 东西有局（East-West Vulnerable）
  - "All" = 双有局（Both Vulnerable）
  - 无法识别时返回 null

═══════════════════════════════════════
输出格式（严格JSON）
═══════════════════════════════════════
请严格按照以下JSON格式输出，不要添加任何额外说明文字：
{
  "南家手牌": "如 ♠KT85 ♥AT863 ♦- ♣63（♦缺门用-占位）" 或 null（图片中未显示该家）,
  "西家手牌": "..." 或 null,
  "北家手牌": "..." 或 null,
  "东家手牌": "..." 或 null,
  "叫牌序列": ["北:pass", "东:pass", "南:1NT", ...] 或 null,
  "当前定约": "如 4H 由南做庄" 或 null,
  "首攻": "如 西:S5" 或 null,
  "局况": "NV/NS/EW/All 之一" 或 null,
  "页面类型": "BBO/桥友圈/桥牌教程书籍/新睿桥牌/其他"
}

**再次强调**：未在图片中显示的手牌，对应字段必须输出 null，绝不能虚构。"""


SINGLE_HAND_VISION_PROMPT = """你的任务是从桥牌游戏截图中识别**单独一家手牌**。

═══════════════════════════════════════
识别规则
═══════════════════════════════════════
- 图片中只包含一家玩家手牌，不要脑补其他玩家手牌
- **牌面10必须用T表示**，例如：♠KT85 而不是 ♠K1085
- 花色符号用 ♠ ♥ ♦ ♣，牌面从大到小排列（A K Q J T 9 8 7 6 5 4 3 2）
- **缺门花色必须用"-"占位**，例如：♠KT85 ♥AT863 ♦- ♣63（方块缺门）
- 四个花色必须按♠♥♦♣顺序全部列出，即使缺门也不能省略
- 截图可能裁剪不全，张数可能不足13张，按实际识别到的牌张返回
- 注意区分相似字符：♠和♣、8和B、T和7

═══════════════════════════════════════
输出格式（严格JSON，不要markdown代码块）
═══════════════════════════════════════
{
  "手牌": "如 ♠KT85 ♥AT863 ♦- ♣63（♦缺门用-占位）"
}"""


class DoubaoVisionClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key or DOUBAO_API_KEY
        self.base_url = base_url or DOUBAO_BASE_URL
        self.endpoint = endpoint or DOUBAO_VISION_ENDPOINT
        self.client = None

        if self.api_key:
            import httpx
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0)
            )
    
    def is_configured(self) -> bool:
        return self.client is not None and self.endpoint and self.endpoint != "YOUR_VISION_ENDPOINT_ID"
    
    def read_cards_from_image(self, image_path: str) -> Dict[str, Any]:
        if not self.client:
            return {"error": "Doubao API Key未配置，请设置环境变量 DOUBAO_API_KEY"}

        if not self.endpoint or self.endpoint == "YOUR_VISION_ENDPOINT_ID":
            return {"error": "Doubao Vision Endpoint未配置，请在火山引擎控制台创建视觉模型推理接入点，并设置环境变量 DOUBAO_VISION_ENDPOINT"}

        try:
            t0 = time.time()

            # 1. 读取原始图片
            with open(image_path, "rb") as f:
                raw_bytes = f.read()
            raw_size_kb = len(raw_bytes) / 1024
            print(f"[DoubaoVision] 原始图片大小: {raw_size_kb:.1f} KB")

            # 2. 压缩图片（缩小分辨率 + JPEG 压缩）
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(raw_bytes))
                orig_w, orig_h = img.size
                # 等比缩放
                if max(orig_w, orig_h) > VISION_MAX_IMAGE_SIZE:
                    ratio = VISION_MAX_IMAGE_SIZE / max(orig_w, orig_h)
                    new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                    print(f"[DoubaoVision] 图片缩放: {orig_w}x{orig_h} → {new_w}x{new_h}")
                # 转 JPEG 压缩到内存
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=VISION_JPEG_QUALITY)
                compressed_bytes = buf.getvalue()
                compressed_kb = len(compressed_bytes) / 1024
                print(f"[DoubaoVision] 压缩后大小: {compressed_kb:.1f} KB (节省 {(1 - compressed_kb/raw_size_kb)*100:.0f}%)")
                mime_type = "image/jpeg"
            except Exception as e:
                print(f"[DoubaoVision] 图片压缩失败({e})，使用原始图片")
                compressed_bytes = raw_bytes
                ext = image_path.lower().split(".")[-1]
                mime_type = {
                    "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "gif": "image/gif", "webp": "image/webp"
                }.get(ext, "image/jpeg")

            # 3. Base64 编码
            t1 = time.time()
            image_b64 = base64.b64encode(compressed_bytes).decode("utf-8")
            print(f"[DoubaoVision] Base64编码耗时: {time.time() - t1:.1f}s, 长度: {len(image_b64)}")

            # 4. 调用视觉模型 API
            t2 = time.time()
            print(f"[DoubaoVision] 开始调用API (max_tokens=4096)...")
            response = self.client.chat.completions.create(
                model=self.endpoint,
                messages=[
                    {"role": "system", "content": VISION_PROMPT},
                    {
                        "role": "user",
                        "content": [{
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}"
                            }
                        }]
                    }
                ],
                temperature=0,
                max_tokens=4096,
                extra_body={"thinking": {"type": "disabled"}}
            )
            api_elapsed = time.time() - t2
            print(f"[DoubaoVision] API调用耗时: {api_elapsed:.1f}s")

            result_text = response.choices[0].message.content

            # 5. 解析 JSON
            try:
                if "```json" in result_text:
                    json_match = result_text.split("```json")[1].split("```")[0]
                elif "```" in result_text:
                    json_match = result_text.split("```")[1].split("```")[0]
                else:
                    json_match = result_text

                parsed = json.loads(json_match.strip())
                total_elapsed = time.time() - t0
                print(f"[DoubaoVision] 总耗时: {total_elapsed:.1f}s (压缩: {t2-t1:.1f}s, API: {api_elapsed:.1f}s)")
                return parsed
            except json.JSONDecodeError:
                total_elapsed = time.time() - t0
                print(f"[DoubaoVision] JSON解析失败，总耗时: {total_elapsed:.1f}s")
                return {"raw_response": result_text, "error": "JSON解析失败"}
                
        except FileNotFoundError:
            return {"error": f"图片文件不存在: {image_path}"}
        except Exception as e:
            return {"error": str(e)}

    def read_single_hand_from_image(self, image_path: str, position: str = "") -> Dict[str, Any]:
        if not self.client:
            return {"error": "Doubao API Key未配置，请设置环境变量 DOUBAO_API_KEY"}

        if not self.endpoint or self.endpoint == "YOUR_VISION_ENDPOINT_ID":
            return {"error": "Doubao Vision Endpoint未配置"}

        try:
            t0 = time.time()

            with open(image_path, "rb") as f:
                raw_bytes = f.read()
            print(f"[DoubaoVision-单家] 位置={position}, 原始图片: {len(raw_bytes)/1024:.1f} KB")

            try:
                from PIL import Image
                img = Image.open(io.BytesIO(raw_bytes))
                orig_w, orig_h = img.size
                if max(orig_w, orig_h) > VISION_MAX_IMAGE_SIZE:
                    ratio = VISION_MAX_IMAGE_SIZE / max(orig_w, orig_h)
                    new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=VISION_JPEG_QUALITY)
                compressed_bytes = buf.getvalue()
                mime_type = "image/jpeg"
            except Exception as e:
                print(f"[DoubaoVision-单家] 图片压缩失败({e})，使用原始图片")
                compressed_bytes = raw_bytes
                ext = image_path.lower().split(".")[-1]
                mime_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")

            image_b64 = base64.b64encode(compressed_bytes).decode("utf-8")

            t2 = time.time()
            print(f"[DoubaoVision-单家] 开始调用API...")
            response = self.client.chat.completions.create(
                model=self.endpoint,
                messages=[
                    {"role": "system", "content": SINGLE_HAND_VISION_PROMPT},
                    {
                        "role": "user",
                        "content": [{
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}
                        }]
                    }
                ],
                temperature=0,
                max_tokens=1024,
                extra_body={"thinking": {"type": "disabled"}}
            )
            print(f"[DoubaoVision-单家] API耗时: {time.time()-t2:.1f}s")

            result_text = response.choices[0].message.content

            try:
                if "```json" in result_text:
                    json_match = result_text.split("```json")[1].split("```")[0]
                elif "```" in result_text:
                    json_match = result_text.split("```")[1].split("```")[0]
                else:
                    json_match = result_text
                parsed = json.loads(json_match.strip())
                print(f"[DoubaoVision-单家] 总耗时: {time.time()-t0:.1f}s")
                return parsed
            except json.JSONDecodeError:
                return {"raw_response": result_text, "error": "JSON解析失败"}

        except FileNotFoundError:
            return {"error": f"图片文件不存在: {image_path}"}
        except Exception as e:
            return {"error": str(e)}

    def parse_hands_to_format(self, vision_result: Dict) -> Dict[str, str]:
        if "error" in vision_result:
            return vision_result
        
        hands = {}
        position_map = {
            "南家手牌": "SOUTH",
            "西家手牌": "WEST", 
            "北家手牌": "NORTH",
            "东家手牌": "EAST"
        }
        
        for cn_key, en_key in position_map.items():
            if cn_key in vision_result:
                hands[en_key] = vision_result[cn_key]
        
        return hands


# ── 豆包模型名 → endpoint 映射 ──
# 通过 .env 中的 DOUBAO_SEED_2_1_PRO_CHAT_ENDPOINT
# / DOUBAO_SEED_2_1_PRO_REASONING_ENDPOINT 配置各模型的推理接入点 ID
def _build_doubao_endpoint_map():
    from config import (
        DOUBAO_SEED_2_1_PRO_CHAT_ENDPOINT,
        DOUBAO_SEED_2_1_PRO_REASONING_ENDPOINT,
        DOUBAO_SEED_2_1_TURBO_CHAT_ENDPOINT,
        DOUBAO_SEED_2_1_TURBO_REASONING_ENDPOINT,
        DOUBAO_MODEL_2_1_PRO,
        DOUBAO_MODEL_2_1_TURBO,
    )
    m = {}
    if DOUBAO_SEED_2_1_PRO_CHAT_ENDPOINT:
        m[DOUBAO_MODEL_2_1_PRO] = DOUBAO_SEED_2_1_PRO_CHAT_ENDPOINT
    if DOUBAO_SEED_2_1_PRO_REASONING_ENDPOINT:
        m[f"{DOUBAO_MODEL_2_1_PRO}::reasoning"] = DOUBAO_SEED_2_1_PRO_REASONING_ENDPOINT
    if DOUBAO_SEED_2_1_TURBO_CHAT_ENDPOINT:
        m[DOUBAO_MODEL_2_1_TURBO] = DOUBAO_SEED_2_1_TURBO_CHAT_ENDPOINT
    if DOUBAO_SEED_2_1_TURBO_REASONING_ENDPOINT:
        m[f"{DOUBAO_MODEL_2_1_TURBO}::reasoning"] = DOUBAO_SEED_2_1_TURBO_REASONING_ENDPOINT
    return m


class DoubaoSeedClient:
    """豆包 Seed 系列 API 客户端。

    支持多个模型（通过 endpoint 映射），兼容 DeepSeekClient 的 self.model 接口。
    模型名称如 ``doubao-seed-2.1-pro``、``doubao-seed-2.1-pro::reasoning``。
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 endpoint: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or DOUBAO_API_KEY
        self.base_url = base_url or DOUBAO_BASE_URL
        self._endpoint_map = _build_doubao_endpoint_map()
        self.client = None

        # 模型名 → endpoint 解析
        if model:
            self.model = model
        elif endpoint:
            # 向后兼容：根据 endpoint 反查模型名
            self.model = None
            for m, ep in self._endpoint_map.items():
                if ep == endpoint:
                    self.model = m
                    break
            if self.model is None:
                self.model = ""
        else:
            self.model = ""

        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

    # ── endpoint 解析 ──
    @property
    def endpoint(self) -> str:
        """当前模型对应的推理接入点 ID"""
        base = self.model.replace("::reasoning", "")
        # 先按精确模型名匹配，再按 base 匹配
        if self.model in self._endpoint_map:
            return self._endpoint_map[self.model]
        if base in self._endpoint_map:
            return self._endpoint_map[base]
        return ""

    # ── 思考模式 ──
    @property
    def is_reasoning(self) -> bool:
        return "::reasoning" in (self.model or "")

    def _thinking_body(self, thinking: Optional[bool] = None) -> dict:
        """构建 thinking extra_body；None 表示根据模型名自动判断"""
        if thinking is None:
            thinking = self.is_reasoning
        return {"thinking": {"type": "enabled" if thinking else "disabled"}}

    def _get_timeout(self, thinking: bool) -> float:
        """根据模型返回合理超时（豆包推理版需要更长）"""
        return 120.0 if thinking else 30.0

    def is_configured(self) -> bool:
        return self.client is not None and bool(self.endpoint)

    def set_model(self, model_name: str):
        """切换模型（同时更新 endpoint）"""
        self.model = model_name

    def chat(self, system_prompt: str, user_prompt: str = "",
             temperature: float = 0.7, model: str = None,
             thinking: bool = None) -> str:
        if not self.client:
            raise ValueError("Doubao API Key未配置，请设置环境变量 DOUBAO_API_KEY")
        if not self.endpoint:
            raise ValueError(f"Doubao Seed Endpoint未配置（模型: {self.model}），"
                             "请在 .env 中设置对应的推理接入点 ID")

        use_model = model or self.model
        ep = self._endpoint_map.get(
            use_model,
            self._endpoint_map.get(use_model.replace("::reasoning", ""), self.endpoint)
        )

        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})

        _thinking = thinking if thinking is not None else self.is_reasoning
        extra_kwargs = {"extra_body": self._thinking_body(_thinking)}

        response = self.client.chat.completions.create(
            model=ep,
            messages=messages,
            temperature=temperature,
            timeout=self._get_timeout(_thinking),
            **extra_kwargs
        )
        return response.choices[0].message.content

    def chat_json(self, system_prompt: str, user_prompt: str = "",
                  temperature: float = 0.7, schema: Dict = None,
                  model: str = None, max_tokens: int = None,
                  thinking: bool = None) -> Dict[str, Any]:
        if not self.client:
            raise ValueError("Doubao API Key未配置，请设置环境变量 DOUBAO_API_KEY")
        if not self.endpoint:
            raise ValueError(f"Doubao Seed Endpoint未配置（模型: {self.model}），"
                             "请在 .env 中设置对应的推理接入点 ID")

        _thinking = thinking if thinking is not None else self.is_reasoning
        if max_tokens is None:
            max_tokens = 8192 if _thinking else 4096  # 非思考也提到 4096，避免豆包啰嗦输出截断

        use_model = model or self.model
        ep = self._endpoint_map.get(
            use_model,
            self._endpoint_map.get(use_model.replace("::reasoning", ""), self.endpoint)
        )

        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})

        extra_kwargs = {"extra_body": self._thinking_body(_thinking)}

        last_error = None
        for attempt in range(2):
            try:
                t0 = time.time()
                response = self.client.chat.completions.create(
                    model=ep,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self._get_timeout(_thinking),
                    response_format={"type": "json_object"},
                    **extra_kwargs
                )
                content = response.choices[0].message.content
                print(f"[Doubao] chat_json OK in {time.time()-t0:.1f}s, chars={len(content)}, finish={response.choices[0].finish_reason}")
                return json.loads(_sanitize_json(content))
            except json.JSONDecodeError as e:
                last_error = f"JSONDecodeError: {e}"
                print(f"[Doubao] chat_json attempt {attempt+1} JSON decode failed: {e}")
                if attempt == 0:
                    time.sleep(1)
            except KeyError as e:
                last_error = f"KeyError: {e}"
                print(f"[Doubao] chat_json attempt {attempt+1} KeyError: {e}")
                if attempt == 0:
                    time.sleep(1)
            except Exception as e:
                last_error = f"API Error: {e}"
                print(f"[Doubao] chat_json attempt {attempt+1} API error: {e}")
                if attempt == 0:
                    time.sleep(1)

        # JSON 模式失败，回退到普通 chat 再提取 JSON
        print(f"[Doubao] chat_json falling back to chat() — last_error={last_error}")
        response_text = self.chat(system_prompt, user_prompt, temperature,
                                  model=use_model, thinking=_thinking)
        # 尝试提取 JSON：移除 BOM、找 { } 边界
        text = response_text.strip().lstrip('﻿')
        # 先清理控制字符
        text = _sanitize_json(text)
        try:
            # 尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试从 markdown 代码块提取
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        # 尝试找第一个 { 到最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass
        print(f"[Doubao] chat_json fallback also failed, returning raw. text[:200]={response_text[:200]}")
        return {"raw_response": response_text, "error": "JSON解析失败"}

    def chat_bidding(self, system_prompt: str, temperature: float = 0.7,
                     model: str = None, thinking: bool = False) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, model=model, thinking=thinking)

    def chat_bidding_fallback(self, system_prompt: str, temperature: float = 0.7,
                              model: str = None, thinking: bool = False) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, model=model, thinking=thinking)

    def chat_human_bid(self, system_prompt: str, temperature: float = 0,
                       model: str = None, thinking: bool = False) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, model=model, thinking=thinking)

    def chat_play(self, system_prompt: str, temperature: float = 0.7,
                  model: str = None, thinking: bool = False) -> Dict[str, Any]:
        max_tokens = 8192 if (thinking or self.is_reasoning) else 1024
        return self.chat_json(system_prompt, "", temperature, model=model,
                              max_tokens=max_tokens, thinking=thinking)
