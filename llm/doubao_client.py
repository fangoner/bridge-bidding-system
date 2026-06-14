import json
import base64
from typing import Optional, Dict, Any
from openai import OpenAI

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_VISION_ENDPOINT, DOUBAO_SEED_ENDPOINT


VISION_PROMPT = """你的任务是从桥牌游戏图片中提取四项关键信息。四项同等重要，必须尽力完整提取。

═══════════════════════════════════════
一、手牌（最高优先级）
═══════════════════════════════════════
- **牌面10必须用T表示**，例如：♠KT85 而不是 ♠K1085
- **每手牌必须正好13张**，这是一个严格的校验规则
- 花色符号用 ♠ ♥ ♦ ♣，牌面从大到小排列（A K Q J T 9 8 7 6 5 4 3 2）
- 检查每种花色是否有正确的牌张数（每种花色最多13张）
- 如果某手牌不足13张或总张数超过13，仔细复查图片
- 注意区分相似字符：♠和♣、8和B、T和7

═══════════════════════════════════════
二、叫牌序列
═══════════════════════════════════════
- 从庄家（dealer，通常标注为"发牌"或"庄"）开始，严格按照叫牌顺序列出
- 每个叫品必须准确对应其位置（南/西/北/东）
- 叫牌顺序是顺时针：南→西→北→东→南→...
- 所有叫品都必须记录，包括开头的pass和结尾的pass
- 最终定约叫品之后通常还有三个pass结束叫牌，也可能有加倍/再加倍
- 仔细观察叫牌区域，每个叫品框通常有位置标签，不要混淆相邻位置的叫品
- 如果图片中没有叫牌区域或叫牌序列完全不显示，则为null

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
输出格式（严格JSON）
═══════════════════════════════════════
请严格按照以下JSON格式输出，不要添加任何额外说明文字：
{
  "南家手牌": "如 ♠KT85 ♥AT863 ♦Q42 ♣63",
  "西家手牌": "...",
  "北家手牌": "...",
  "东家手牌": "...",
  "叫牌序列": ["北:pass", "东:pass", "南:1NT", ...] 或 null,
  "当前定约": "如 4H 由南做庄" 或 null,
  "首攻": "如 西:S5" 或 null,
  "页面类型": "BBO/桥友圈/桥牌教程书籍/新睿桥牌/其他"
}"""


class DoubaoVisionClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key or DOUBAO_API_KEY
        self.base_url = base_url or DOUBAO_BASE_URL
        self.endpoint = endpoint or DOUBAO_VISION_ENDPOINT
        self.client = None
        
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
    
    def is_configured(self) -> bool:
        return self.client is not None and self.endpoint and self.endpoint != "YOUR_VISION_ENDPOINT_ID"
    
    def read_cards_from_image(self, image_path: str) -> Dict[str, Any]:
        if not self.client:
            return {"error": "Doubao API Key未配置，请设置环境变量 DOUBAO_API_KEY"}
        
        if not self.endpoint or self.endpoint == "YOUR_VISION_ENDPOINT_ID":
            return {"error": "Doubao Vision Endpoint未配置，请在火山引擎控制台创建视觉模型推理接入点，并设置环境变量 DOUBAO_VISION_ENDPOINT"}
        
        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            ext = image_path.lower().split(".")[-1]
            mime_type = {
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
                "gif": "image/gif",
                "webp": "image/webp"
            }.get(ext, "image/jpeg")
            
            response = self.client.chat.completions.create(
                model=self.endpoint,
                messages=[
                    {
                        "role": "system",
                        "content": VISION_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0
            )
            
            result_text = response.choices[0].message.content
            
            try:
                if "```json" in result_text:
                    json_match = result_text.split("```json")[1].split("```")[0]
                elif "```" in result_text:
                    json_match = result_text.split("```")[1].split("```")[0]
                else:
                    json_match = result_text
                
                return json.loads(json_match.strip())
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


class DoubaoSeedClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key or DOUBAO_API_KEY
        self.base_url = base_url or DOUBAO_BASE_URL
        self.endpoint = endpoint or DOUBAO_SEED_ENDPOINT
        self.client = None
        
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
    
    def is_configured(self) -> bool:
        return self.client is not None and self.endpoint and self.endpoint != ""
    
    def chat(self, system_prompt: str, user_prompt: str = "", temperature: float = 0.7) -> str:
        if not self.client:
            raise ValueError("Doubao API Key未配置，请设置环境变量 DOUBAO_API_KEY")
        
        if not self.endpoint:
            raise ValueError("Doubao Seed Endpoint未配置，请设置环境变量 DOUBAO_SEED_ENDPOINT")
        
        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        
        response = self.client.chat.completions.create(
            model=self.endpoint,
            messages=messages,
            temperature=temperature
        )
        
        return response.choices[0].message.content
    
    def chat_json(self, system_prompt: str, user_prompt: str = "", temperature: float = 0.7) -> Dict[str, Any]:
        if not self.client:
            raise ValueError("Doubao API Key未配置，请设置环境变量 DOUBAO_API_KEY")
        
        if not self.endpoint:
            raise ValueError("Doubao Seed Endpoint未配置，请设置环境变量 DOUBAO_SEED_ENDPOINT")
        
        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.endpoint,
                messages=messages,
                temperature=temperature,
                max_tokens=8192
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        except Exception as e:
            pass
        
        response_text = self.chat(system_prompt, user_prompt, temperature)
        
        try:
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_match = response_text.split("```")[1].split("```")[0]
            
            return json.loads(json_match.strip())
        except json.JSONDecodeError:
            return {"raw_response": response_text, "error": "JSON解析失败"}
    
    def chat_bidding(self, system_prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature)
    
    def chat_bidding_fallback(self, system_prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature)
    
    def chat_human_bid(self, system_prompt: str, temperature: float = 0) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature)
