import json
from typing import Optional, Dict, Any
from openai import OpenAI

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEFAULT_FALLBACK_MODEL
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


class DeepSeekClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, fallback_model: Optional[str] = None, main_prompt_model: Optional[str] = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.base_url = base_url or DEEPSEEK_BASE_URL
        self.fallback_model = fallback_model or DEFAULT_FALLBACK_MODEL
        self.main_prompt_model = main_prompt_model or "deepseek-chat"
        self.client = None
        
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
    
    def is_configured(self) -> bool:
        return self.client is not None
    
    def chat(self, system_prompt: str, user_prompt: str = "", temperature: float = 0.7) -> str:
        if not self.client:
            raise ValueError("DeepSeek API Key未配置，请设置环境变量 DEEPSEEK_API_KEY")
        
        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=temperature
        )
        
        return response.choices[0].message.content
    
    def chat_json(self, system_prompt: str, user_prompt: str = "", temperature: float = 0.7, schema: Dict = None, model: str = None) -> Dict[str, Any]:
        if not self.client:
            raise ValueError("DeepSeek API Key未配置，请设置环境变量 DEEPSEEK_API_KEY")
        
        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=model or self.main_prompt_model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                max_tokens=8192
            )
            return json.loads(response.choices[0].message.content)
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
        return self.chat_json(system_prompt, "", temperature, BIDDING_SCHEMA)
    
    def chat_bidding_fallback(self, system_prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        if not self.client:
            raise ValueError("DeepSeek API Key未配置，请设置环境变量 DEEPSEEK_API_KEY")
        
        messages = [{"role": "system", "content": system_prompt}]
        
        try:
            response = self.client.chat.completions.create(
                model=self.fallback_model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                max_tokens=8192
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            pass
        
        response_text = self.chat(system_prompt, "", temperature)
        
        try:
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_match = response_text.split("```")[1].split("```")[0]
            
            return json.loads(json_match.strip())
        except json.JSONDecodeError:
            return {"raw_response": response_text, "error": "JSON解析失败"}
    
    def chat_human_bid(self, system_prompt: str, temperature: float = 0) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, HUMAN_BID_SCHEMA)
