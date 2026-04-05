import json
import base64
from typing import Optional, Dict, Any
from openai import OpenAI

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_VISION_ENDPOINT


VISION_PROMPT = """你的任务是从桥牌游戏图片中提取信息：

1. 四位牌手的手牌
2. 当前的叫牌序列（如果有显示）
3. 当前定约（如果有显示）

重要规则：
- **牌面10必须用T表示**，例如：♠KT85 而不是 ♠K1085
- **每手牌必须正好13张**，这是一个严格的校验规则
- 叫牌序列必须从庄家（dealer）开始，严格按照叫牌顺序列出
- 每个叫品必须准确对应其位置（南/西/北/东）
- 所有叫品都必须记录，包括开头的pass和结尾的pass
- 最终定约叫品之后通常还有三个pass结束叫牌，也可能有加倍/再加倍，必须全部记录
- 叫牌顺序是顺时针：南→西→北→东→南→...
- 仔细观察叫牌区域，确定每个叫品对应的位置，不要混淆相邻位置的叫品

**手牌验证（非常重要）**：
- 检查每手牌是否正好13张
- 检查每种花色是否有正确的牌张数（每种花色最多13张）
- 如果某手牌不足13张或总张数超过13，请明确标注
- 如果花色符号后面没有牌面（如 ♠后面为空），这是错误识别

请严格按照以下JSON格式输出：
{
  "南家手牌": "花色符号+牌面，如 ♠KT85 ♥AT863 ♦Q42 ♣63，牌面10用T表示",
  "西家手牌": "...",
  "北家手牌": "...",
  "东家手牌": "...",
  "叫牌序列": ["北:pass", "东:pass", "南:1NT", "西:pass", "北:2D", "东:pass", "南:pass", "西:pass"]，从庄家开始完整记录所有叫品，如果未显示则为null,
  "当前定约": "如 4H 由南做庄，如果未显示则为null",
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
