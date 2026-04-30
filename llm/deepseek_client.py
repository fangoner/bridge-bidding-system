import json
from typing import Optional, Dict, Any
import httpx
from openai import OpenAI

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from llm.prompts import BIDDING_SYSTEM_PROMPT, BIDDING_FALLBACK_PROMPT, HUMAN_BID_PROMPT


BIDDING_SCHEMA = {
    "type": "object",
    "properties": {
        "自己pass次数": {"type": "string"},
        "当前叫牌序列": {"type": "string"},
        "JF约定": {"type": "string"},
        "叫牌位置": {"type": "string"},
        "手牌分析": {"type": "string"},
        "叫牌历史": {"type": "string"},
        "叫品筛选过程": {"type": "string"},
        "选定叫品": {"type": "string"},
        "叫品含义": {"type": "string"},
        "完整叫牌序列": {"type": "string"}
    },
    "required": [
        "自己pass次数",
        "当前叫牌序列",
        "JF约定",
        "叫牌位置",
        "手牌分析",
        "叫牌历史",
        "叫品筛选过程",
        "选定叫品",
        "叫品含义",
        "完整叫牌序列"
    ]
}

BIDDING_FALLBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "自己pass次数": {"type": "string"},
        "当前叫牌序列": {"type": "string"},
        "JF约定": {"type": "string"},
        "叫牌位置": {"type": "string"},
        "手牌分析": {"type": "string"},
        "叫牌历史": {"type": "string"},
        "自己和队友配合花色张数合计": {"type": "string"},
        "牌型点": {"type": "string"},
        "自己和队友点力合计": {"type": "string"},
        "是否进局或试探满贯": {"type": "string"},
        "止张分析": {"type": "string"},
        "扣叫控制": {"type": "string"},
        "自己和队友关键张合计": {"type": "string"},
        "叫品筛选过程": {"type": "string"},
        "选定叫品": {"type": "string"},
        "叫品含义": {"type": "string"},
        "完整叫牌序列": {"type": "string"}
    },
    "required": [
        "自己pass次数",
        "当前叫牌序列",
        "JF约定",
        "叫牌位置",
        "手牌分析",
        "叫牌历史",
        "自己和队友配合花色张数合计",
        "牌型点",
        "自己和队友点力合计",
        "是否进局或试探满贯",
        "止张分析",
        "扣叫控制",
        "自己和队友关键张合计",
        "叫品筛选过程",
        "选定叫品",
        "叫品含义",
        "完整叫牌序列"
    ]
}

HUMAN_BID_SCHEMA = {
    "type": "object",
    "properties": {
        "当前叫牌序列": {"type": "string"},
        "叫品筛选过程": {"type": "string"},
        "选定叫品": {"type": "string"},
        "叫品含义": {"type": "string"},
        "完整叫牌序列": {"type": "string"}
    },
    "required": [
        "当前叫牌序列",
        "叫品筛选过程",
        "选定叫品",
        "叫品含义",
        "完整叫牌序列"
    ]
}

PLAY_SCHEMA = {
    "type": "object",
    "properties": {
        "局面评估": {"type": "string"},
        "候选对比": {"type": "string"},
        "核心逻辑": {"type": "string"},
        "推荐出牌": {"type": "string"}
    },
    "required": ["局面评估", "候选对比", "核心逻辑", "推荐出牌"]
}


class DeepSeekClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.base_url = base_url or DEEPSEEK_BASE_URL
        self.model = model or "deepseek-v4-flash"
        self.client = None

        if self.api_key:
            self._http_client = httpx.Client(
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                timeout=httpx.Timeout(90.0, connect=15.0)
            )
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=self._http_client
            )
    
    def is_configured(self) -> bool:
        return self.client is not None
    
    def chat(self, system_prompt: str, user_prompt: str = "", temperature: float = 0.7, model: str = None) -> str:
        if not self.client:
            raise ValueError("DeepSeek API Key未配置，请设置环境变量 DEEPSEEK_API_KEY")
        
        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        
        response = self.client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            timeout=httpx.Timeout(90.0, connect=15.0)
        )
        
        return response.choices[0].message.content
    
    def chat_json(self, system_prompt: str, user_prompt: str = "", temperature: float = 0.7, schema: Dict = None, model: str = None) -> Dict[str, Any]:
        if not self.client:
            raise ValueError("DeepSeek API Key未配置，请设置环境变量 DEEPSEEK_API_KEY")
        
        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        
        import time
        max_retries = 2
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=model or self.model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    max_tokens=8192
                )
                return json.loads(response.choices[0].message.content)
            except (json.JSONDecodeError, KeyError):
                # JSON 解析失败，降级到普通模式（仅尝试一次）
                break
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait = (attempt + 1) * 3
                    print(f"[DeepSeek] JSON mode retry {attempt+1}/{max_retries} after {wait}s: {e}")
                    time.sleep(wait)
                else:
                    print(f"[DeepSeek] JSON mode failed after {max_retries} retries: {e}")
        
        # JSON 模式失败，降级到普通文本模式（仅一次，不重试）
        try:
            response_text = self.chat(system_prompt, user_prompt, temperature, model)
        except Exception as e:
            error_msg = f"json解析失败: {last_error}, 普通模式也失败: {e}"
            print(f"[DeepSeek] {error_msg}")
            return {"raw_response": "", "error": error_msg}
        
        try:
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_match = response_text.split("```")[1].split("```")[0]
            
            return json.loads(json_match.strip())
        except json.JSONDecodeError:
            return {"raw_response": response_text, "error": "JSON解析失败"}
    
    def chat_bidding(self, system_prompt: str, temperature: float = 0.7, model: str = None) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, BIDDING_SCHEMA, model)
    
    def chat_bidding_fallback(self, system_prompt: str, temperature: float = 0.7, model: str = None) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, BIDDING_FALLBACK_SCHEMA, model)
    
    def chat_human_bid(self, system_prompt: str, temperature: float = 0, model: str = None) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, HUMAN_BID_SCHEMA, model)
    
    def chat_play(self, system_prompt: str, temperature: float = 0.7, model: str = None) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, PLAY_SCHEMA, model)
