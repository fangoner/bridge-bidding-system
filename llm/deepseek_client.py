import json
import logging
from typing import Optional, Dict, Any
import httpx
from openai import OpenAI

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from llm.prompts import BIDDING_SYSTEM_PROMPT, BIDDING_FALLBACK_PROMPT, HUMAN_BID_PROMPT

LOG_FILE = Path(__file__).parent.parent / "deepseek_debug.log"
_logger = logging.getLogger("deepseek")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(_fh)


BIDDING_SCHEMA = {
    "type": "object",
    "properties": {
        "叫牌位置": {"type": "string"},
        "手牌分析": {"type": "string"},
        "叫牌历史": {"type": "string"},
        "叫品筛选过程": {"type": "string"},
        "选定叫品": {"type": "string"},
        "叫品含义": {"type": "string"}
    },
    "required": [
        "叫牌位置",
        "手牌分析",
        "叫牌历史",
        "叫品筛选过程",
        "选定叫品",
        "叫品含义"
    ]
}

BIDDING_FALLBACK_SCHEMA = {
    "type": "object",
    "properties": {
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
        "叫品含义": {"type": "string"}
    },
    "required": [
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
        "叫品含义"
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
                timeout=httpx.Timeout(30.0, connect=10.0)
            )
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=self._http_client
            )
    
    def is_configured(self) -> bool:
        return self.client is not None
    
    def _get_timeout(self, thinking: bool) -> float:
        is_pro = "pro" in (self.model or "").lower()
        if thinking:
            return 120.0 if is_pro else 90.0
        return 30.0

    def chat(self, system_prompt: str, user_prompt: str = "", temperature: float = 0.7, model: str = None, thinking: bool = False) -> str:
        if not self.client:
            raise ValueError("DeepSeek API Key未配置，请设置环境变量 DEEPSEEK_API_KEY")
        
        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        
        timeout = self._get_timeout(thinking)
        extra_kwargs = {}
        if thinking:
            extra_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            extra_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = self.client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            timeout=timeout,
            **extra_kwargs
        )
        
        return response.choices[0].message.content
    
    def _is_timeout_error(self, e: Exception) -> bool:
        err_str = str(e).lower()
        return any(kw in err_str for kw in ["timeout", "timed out", "read timed out", "deadline"])

    def _is_retryable_error(self, e: Exception) -> bool:
        """是否值得重试：仅超时/连接/限流等瞬时错误；业务错误（400/鉴权/上下文超长）重试无效。"""
        err_str = str(e).lower()
        return any(kw in err_str for kw in [
            "timeout", "timed out", "read timed out", "deadline",
            "rate limit", "too many requests", "connection", "http 429", "http 500", "http 502", "http 503",
        ])

    def chat_json(self, system_prompt: str, user_prompt: str = "", temperature: float = 0.7, schema: Dict = None, model: str = None, max_tokens: int = None, thinking: bool = False, max_attempts: int = 2) -> Dict[str, Any]:
        if not self.client:
            raise ValueError("DeepSeek API Key未配置，请设置环境变量 DEEPSEEK_API_KEY")
        
        if max_tokens is None:
            max_tokens = 8192 if thinking else 2048

        messages = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        
        import time as time_module
        extra_kwargs = {}
        if thinking:
            extra_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            extra_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        timeout = self._get_timeout(thinking)
        start = time_module.time()
        actual_model = model or self.model
        log_msg = f"[DeepSeek] chat_json model={actual_model} thinking={thinking} max_tokens={max_tokens} timeout={timeout}s max_attempts={max_attempts} prompt_chars={len(system_prompt)}"
        print(log_msg)
        _logger.info(log_msg)

        content = ""
        # P0-5 修复：去掉 chat() 回落链（不再 JSON 失败后再补一发非 JSON 调用）；
        # 超时/限流指数退避重试，业务错误不重试；失败直接返回 error dict（由上层决定报错或兜底）
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=actual_model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    max_tokens=max_tokens,
                    timeout=timeout,
                    **extra_kwargs
                )
                elapsed = time_module.time() - start
                content = response.choices[0].message.content
                usage_data = response.usage
                if usage_data:
                    ok_msg = f"[DeepSeek] OK in {elapsed:.1f}s response_chars={len(content)} finish_reason={response.choices[0].finish_reason} reasoning_tokens={getattr(usage_data, 'completion_tokens_details', None) and getattr(usage_data.completion_tokens_details, 'reasoning_tokens', 0) or 0} total_tokens={usage_data.total_tokens}"
                else:
                    ok_msg = f"[DeepSeek] OK in {elapsed:.1f}s response_chars={len(content)} finish_reason={response.choices[0].finish_reason} (no usage)"
                print(ok_msg)
                _logger.info(ok_msg)
                return json.loads(content)
            except json.JSONDecodeError:
                # LLM 输出不合规 JSON：重试大概率同样失败，直接返回错误（含原文便于诊断）
                fail_msg = f"[DeepSeek] JSON 解析失败 response_chars={len(content)}"
                print(fail_msg)
                _logger.error(fail_msg)
                return {"raw_response": content, "error": "JSON解析失败"}
            except KeyError:
                fail_msg = "[DeepSeek] 响应结构异常（缺 choices/message/content）"
                print(fail_msg)
                _logger.error(fail_msg)
                return {"raw_response": "", "error": "响应结构异常"}
            except Exception as e:
                is_last = (attempt == max_attempts - 1)
                if is_last or not self._is_retryable_error(e):
                    fail_msg = f"[DeepSeek] JSON mode failed: {e}"
                    print(fail_msg)
                    _logger.error(fail_msg)
                    return {"raw_response": "", "error": f"JSON mode failed: {e}"}
                # 瞬时错误：指数退避（1s, 2s, 4s...）后重试
                wait = 2 ** attempt
                retry_msg = f"[DeepSeek] JSON mode retry after {wait}s (attempt {attempt + 1}/{max_attempts}): {e}"
                print(retry_msg)
                _logger.warning(retry_msg)
                time_module.sleep(wait)

        return {"raw_response": "", "error": "JSON mode failed"}
    
    def chat_bidding(self, system_prompt: str, temperature: float = 0.7, model: str = None, thinking: bool = False) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, BIDDING_SCHEMA, model, thinking=thinking)
    
    def chat_bidding_fallback(self, system_prompt: str, temperature: float = 0.7, model: str = None, thinking: bool = False) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, BIDDING_FALLBACK_SCHEMA, model, thinking=thinking)
    
    def chat_human_bid(self, system_prompt: str, temperature: float = 0, model: str = None, thinking: bool = False) -> Dict[str, Any]:
        return self.chat_json(system_prompt, "", temperature, HUMAN_BID_SCHEMA, model, thinking=thinking)
    
    def chat_play(self, system_prompt: str, temperature: float = 0.7, model: str = None, thinking: bool = False) -> Dict[str, Any]:
        max_tokens = 8192 if thinking else 1024
        # P1-1 修复：打牌决策单次尝试（不重试），失败由 play_service 快速回落规则选牌，
        # 避免超时后重试再等一个完整 timeout（chat 30s → 最坏 60s+）
        return self.chat_json(system_prompt, "", temperature, PLAY_SCHEMA, model, max_tokens=max_tokens, thinking=thinking, max_attempts=1)
