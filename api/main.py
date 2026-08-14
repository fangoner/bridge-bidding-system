#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
桥牌叫牌练习系统 - Web API服务
"""

import sys
import subprocess
import os
import io
import re
import json
import time
import copy
import threading
import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
import traceback
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bridge.dealer import BridgeDealer, Hand, Position, POSITION_ORDER, DealMode, parse_deal_input, parse_hand_string
from bridge.bidding import (
    extract_retrieval_keyword,
    get_partner_position,
    get_position_name,
    get_next_position,
)
from bridge.output_format import generate_all_outputs, generate_compact_output, generate_deep_finesse_output
from bridge.deep_finesse import analyze_with_deep_finesse, parse_df_deal, df_format_to_hand
from bridge.bidding_service import BiddingService
from knowledge.loader import JFLoader, JFRetriever
from llm.prompts import BIDDING_SYSTEM_PROMPT, BIDDING_FALLBACK_PROMPT, HUMAN_BID_PROMPT
from llm.deepseek_client import DeepSeekClient
from llm.doubao_client import DoubaoVisionClient, DoubaoSeedClient
from utils.screenshot import trigger_screenshot_shortcut, read_clipboard_image
from config import (
    JF_CONVENTION_FILE, DEFAULT_DEAL_SYSTEM,
    AI_PROVIDER_DEEPSEEK, AI_PROVIDER_DOUBAO, DEFAULT_AI_PROVIDER,
    DEFAULT_PLAY_ENGINE,
    ALL_MODELS, ALL_BASE_MODELS,
    is_doubao_model, is_reasoning_model, get_base_model,
    DOUBAO_MODEL_2_1_PRO, DOUBAO_MODEL_2_1_TURBO,
    DD_PARTICLES_MIN, DD_PARTICLES_MAX,
    MCTS_PARTICLES_MIN, MCTS_PARTICLES_MAX,
    ALPHA_MU_WORLDS_MIN, ALPHA_MU_WORLDS_MAX,
)

try:
    from dd_analysis import analyze_all_contracts, DDS_AVAILABLE
    ENDPLAY_AVAILABLE = DDS_AVAILABLE  # 向后兼容别名
except ImportError:
    ENDPLAY_AVAILABLE = False
    print("警告: dd_analysis 模块不可用，双明手分析功能不可用")

app = FastAPI(title="桥牌叫牌练习系统 API", version="1.0.0")

# 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量 - 无状态的可共享
jf_loader = JFLoader(JF_CONVENTION_FILE)
jf_segments = jf_loader.load()
jf_retriever = JFRetriever(jf_segments)
llm_client = DeepSeekClient()
doubao_client = DoubaoSeedClient()
vision_client = DoubaoVisionClient()

current_ai_provider = DEFAULT_AI_PROVIDER

def get_available_models() -> list:
    """返回当前环境实际可用的模型列表（已配置 endpoint / API Key）"""
    available = []
    # DeepSeek 模型：需 API Key
    if llm_client.is_configured():
        available.extend(["deepseek-v4-flash", "deepseek-v4-flash::reasoning",
                          "deepseek-v4-pro", "deepseek-v4-pro::reasoning"])
    return available

def get_llm_client(ai_provider: str = None):
    global current_ai_provider
    provider = ai_provider or current_ai_provider
    if provider == AI_PROVIDER_DOUBAO:
        return doubao_client
    return llm_client


class GameMode(str, Enum):
    PAIR = "双人叫牌"
    FOUR = "四人叫牌"


class DealRequest(BaseModel):
    mode: str = "free"  # free, weak_twos, strong_twos, preemptive, gambling_3nt


class DealResponse(BaseModel):
    hands: Dict[str, dict]
    dealer: str


class BidRequest(BaseModel):
    hand: dict
    bidding_sequence: List[Dict[str, str]]
    position: str
    deal_system: str = DEFAULT_DEAL_SYSTEM
    bid_history: str = ""
    use_fallback: bool = False
    fallback_model: Optional[str] = None
    ai_provider: Optional[str] = None
    use_reasoning: bool = False


class FallbackModelRequest(BaseModel):
    fallback_model: str  # deepseek-v4-flash 或 deepseek-v4-pro


class FallbackModelResponse(BaseModel):
    fallback_model: str
    message: str


class BidResponse(BaseModel):
    bid: str
    meaning: str
    selection_process: str
    use_fallback: bool = False
    full_output: Optional[dict] = None


class AnalyzeRequest(BaseModel):
    bidding_sequence: str
    deal_system: str = DEFAULT_DEAL_SYSTEM
    position: Optional[str] = None


class AnalyzeResponse(BaseModel):
    keyword: str
    content: str


class HumanBidRequest(BaseModel):
    bidding_sequence: List[Dict[str, str]]
    position: str
    user_input: str
    deal_system: str = DEFAULT_DEAL_SYSTEM
    bid_history: str = ""  # 已累积的叫牌含义文本，供 LLM 理解上下文


class HumanBidResponse(BaseModel):
    bid: str
    meaning: str
    full_output: Optional[dict] = None


class OutputFormatsRequest(BaseModel):
    hands: Dict[str, dict]
    bidding_sequence: str
    dealer: str
    game_mode: str = "四人叫牌"
    position_roles: Optional[Dict[str, str]] = None
    opening_lead: Optional[str] = None


class OutputFormatsResponse(BaseModel):
    compact: str
    deep_finesse: str


def hand_to_dict(hand: Hand) -> dict:
    """将Hand对象转换为字典"""
    return {
        "spades": hand.spades,
        "hearts": hand.hearts,
        "diamonds": hand.diamonds,
        "clubs": hand.clubs,
        "hcp": hand.hcp,
        "distribution": hand.distribution,
        "display": hand.to_display_string()
    }


@app.get("/")
async def root():
    return {"message": "桥牌叫牌练习系统 API", "version": "1.0.0"}


@app.post("/api/deal", response_model=DealResponse)
async def deal(request: DealRequest):
    """发牌接口"""
    try:
        mode_map = {
            "free": DealMode.FREE,
            "game": DealMode.GAME,
            "slam": DealMode.SLAM,
        }
        deal_mode = mode_map.get(request.mode, DealMode.FREE)
        
        dealer = BridgeDealer(deal_mode)
        hands = dealer.deal()
        
        hands_dict = {}
        for pos, hand in hands.items():
            hands_dict[get_position_name(pos)] = hand_to_dict(hand)
        
        return DealResponse(
            hands=hands_dict,
            dealer="南"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """分析叫牌序列，提取关键字"""
    try:
        keyword = extract_retrieval_keyword(
            request.bidding_sequence,
            request.deal_system,
            request.position
        )
        
        partner_name = get_partner_position(request.position) if request.position else "北"
        result = jf_retriever.retrieve_with_preprocess(keyword, request.bidding_sequence, partner_name)
        
        return AnalyzeResponse(
            keyword=keyword,
            content=result.get("original_content", "")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/human-bid", response_model=HumanBidResponse)
async def human_bid(request: HumanBidRequest):
    """人类叫牌接口 - 获取叫品含义"""
    try:
        # 将数组转换为正确格式的字符串
        bidding_str = ""
        if request.bidding_sequence and len(request.bidding_sequence) > 0:
            bidding_str = "-".join([f"({b['position']}){b['bid']}" for b in request.bidding_sequence]) + "-"
        
        bidding_service = BiddingService(llm_client, jf_retriever)
        bidding_service.set_bid_meanings(request.bid_history if request.bid_history else "")
        # LLM 调用（可能 14-90s）卸载到线程，避免阻塞事件循环（P0-1 修复）
        result = await asyncio.to_thread(
            bidding_service.human_bid,
            user_input=request.user_input,
            position=request.position,
            bidding_sequence=bidding_str,
            deal_system=request.deal_system,
            verbose=True,
        )
        
        # 人类叫牌时，直接使用用户输入的叫品，而不是LLM返回的"选定叫品"
        # 避免LLM解析错误导致显示的叫品与实际不符
        bid = request.user_input.strip()
        if bid.upper() == "P":
            bid = "pass"
        meaning = result.get("叫品含义", "")
        if isinstance(meaning, dict):
            meaning = json.dumps(meaning, ensure_ascii=False)
        result["_prompt"] = bidding_service._last_prompt
        return HumanBidResponse(
            bid=bid,
            meaning=meaning,
            full_output=result
        )
    except Exception as e:
        print(f"[ERROR] 人类叫牌失败: {str(e)}")
        bid = request.user_input.strip().upper()
        if bid == "P":
            bid = "pass"
        return HumanBidResponse(
            bid=bid,
            meaning=f"获取叫品含义失败: {str(e)}"
        )


@app.get("/api/fallback-model")
async def get_fallback_model():
    """获取当前模型配置（仅返回已配置 endopoint 的可用模型）"""
    return {
        "fallback_model": llm_client.model,
        "available_models": get_available_models()
    }


@app.post("/api/fallback-model", response_model=FallbackModelResponse)
async def set_fallback_model(request: FallbackModelRequest):
    """设置模型"""
    available = get_available_models()
    if request.fallback_model not in available:
        raise HTTPException(
            status_code=400,
            detail=f"模型不可用（未配置 endpoint）。当前可用: {', '.join(available) if available else '(无)'}"
        )

    # 如果是豆包模型，切换到 DoubaoSeedClient
    if is_doubao_model(request.fallback_model):
        doubao_client.set_model(request.fallback_model)
    else:
        llm_client.model = request.fallback_model

    return FallbackModelResponse(
        fallback_model=request.fallback_model,
        message=f"模型已设置为: {request.fallback_model}"
    )


class AIProviderRequest(BaseModel):
    ai_provider: str


class AIProviderResponse(BaseModel):
    ai_provider: str
    message: str


@app.get("/api/ai-provider")
async def get_ai_provider():
    """获取当前AI提供商配置"""
    return {
        "ai_provider": current_ai_provider,
        "available_providers": [
            {"id": AI_PROVIDER_DEEPSEEK, "name": "DeepSeek",
             "models": ["deepseek-v4-flash", "deepseek-v4-pro"]},
            {"id": AI_PROVIDER_DOUBAO, "name": "Doubao (豆包)",
             "models": [DOUBAO_MODEL_2_1_PRO, DOUBAO_MODEL_2_1_TURBO]}
        ]
    }


@app.post("/api/ai-provider", response_model=AIProviderResponse)
async def set_ai_provider(request: AIProviderRequest):
    """设置AI提供商"""
    global current_ai_provider
    valid_providers = [AI_PROVIDER_DEEPSEEK, AI_PROVIDER_DOUBAO]
    if request.ai_provider not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"无效的AI提供商。有效选项: {', '.join(valid_providers)}"
        )
    
    current_ai_provider = request.ai_provider
    provider_name = "DeepSeek" if request.ai_provider == AI_PROVIDER_DEEPSEEK else "Doubao (豆包)"
    
    return AIProviderResponse(
        ai_provider=request.ai_provider,
        message=f"AI提供商已设置为: {provider_name}"
    )


@app.post("/api/bid", response_model=BidResponse)
async def bid(request: BidRequest):
    """AI叫牌接口"""
    # except 分支所需的默认值：异常可能发生在这些变量赋值之前（P1-11 修复，避免 except 内二次 NameError）
    current_llm_client = None
    use_doubao = False
    target_model = ""
    try:
        # 将数组转换为正确格式的字符串
        bidding_str = ""
        if request.bidding_sequence and len(request.bidding_sequence) > 0:
            bidding_str = "-".join([f"({b['position']}){b['bid']}" for b in request.bidding_sequence]) + "-"
        
        hand_info = request.hand
        
        # 支持两种手牌格式：
        # 1. 旧格式：display, hcp, distribution
        # 2. 新格式：spades, hearts, diamonds, clubs, hcp
        hand_display = hand_info.get('display', '')
        hcp = hand_info.get('hcp', 0)
        distribution = hand_info.get('distribution', '')
        
        # 如果没有display字段，从spades/hearts/diamonds/clubs构建
        if not hand_display:
            spades = hand_info.get('spades', '')
            hearts = hand_info.get('hearts', '')
            diamonds = hand_info.get('diamonds', '')
            clubs = hand_info.get('clubs', '')
            
            # 构建display字符串
            suit_parts = []
            if spades:
                suit_parts.append(f"♠{spades}")
            if hearts:
                suit_parts.append(f"♥{hearts}")
            if diamonds:
                suit_parts.append(f"♦{diamonds}")
            if clubs:
                suit_parts.append(f"♣{clubs}")
            hand_display = ' '.join(suit_parts) if suit_parts else ''
            
            # 构建distribution字符串
            distribution = f"S{len(spades)}-H{len(hearts)}-D{len(diamonds)}-C{len(clubs)}"
        
        class SimpleHand:
            def __init__(self, display, hcp, dist):
                self._display = display
                self.hcp = hcp
                self.distribution = dist
            
            def to_display_string(self):
                return self._display
        
        hand = SimpleHand(hand_display, hcp, distribution)
        
        # 确定使用的模型和客户端
        target_model = request.fallback_model or ""
        use_doubao = is_doubao_model(target_model)
        use_reasoning = request.use_reasoning or is_reasoning_model(target_model)
        # 豆包需将 ::reasoning 追加到模型名以匹配正确的 endpoint
        if use_doubao and use_reasoning:
            target_model = f"{get_base_model(target_model)}::reasoning"

        if use_doubao:
            current_llm_client = doubao_client
            current_llm_client.set_model(target_model)
            if not current_llm_client.is_configured():
                available = get_available_models()
                # P0-4 修复：配置错误走 502，前端提示而非静默 pass
                raise HTTPException(
                    status_code=502,
                    detail=f"豆包模型 {target_model} 的推理接入点未配置。请在 .env 中设置对应的 endpoint。当前可用模型: {', '.join(available)}"
                )
        else:
            current_llm_client = get_llm_client(request.ai_provider)
            if target_model:
                # 请求级浅拷贝：并发请求各自持有独立的 model 属性，
                # 避免共享 llm_client.model 被并发修改导致模型串用（F4 修复）
                current_llm_client = copy.copy(current_llm_client)
                current_llm_client.model = target_model

        bidding_service = BiddingService(current_llm_client, jf_retriever)
        bidding_service.use_fallback = request.use_fallback
        bidding_service.set_bid_meanings(request.bid_history if request.bid_history else "")

        # LLM 调用（14-90s，思考模式最坏 360s）卸载到线程，避免阻塞事件循环（P0-1 修复）
        result = await asyncio.to_thread(
            bidding_service.ai_bid,
            hand=hand,
            position=request.position,
            bidding_sequence=bidding_str,
            deal_system=request.deal_system,
            verbose=True,
            use_reasoning=use_reasoning,
        )

        # 附带发给 LLM 的完整提示词
        result["_prompt"] = bidding_service._last_prompt

        bid = result.get("选定叫品") or "pass"
        meaning = result.get("叫品含义") or result.get("叫品含义及后续建议") or ""
        if isinstance(meaning, dict):
            meaning = json.dumps(meaning, ensure_ascii=False)
        selection_process = result.get("叫品筛选过程") or ""
        if isinstance(selection_process, dict):
            selection_process = json.dumps(selection_process, ensure_ascii=False)

        # 合规性重试耗尽：保持 200，前端识别"暂停叫牌"标记后停止自动叫牌等待用户处理
        if result.get("暂停叫牌"):
            return BidResponse(
                bid=bid,
                meaning=meaning,
                selection_process=selection_process,
                use_fallback=bidding_service.use_fallback,
                full_output=result,
            )

        # 硬错误（LLM 超时/网络/API Key 未配置等）：返回非 200，
        # 前端提示并允许重试，不再把错误伪装成合法 pass（P0-4 修复）
        if result.get("error"):
            raise HTTPException(status_code=502, detail=result["error"])

        return BidResponse(
            bid=bid,
            meaning=meaning,
            selection_process=selection_process,
            use_fallback=bidding_service.use_fallback,
            full_output=result
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] 叫牌失败: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"叫牌失败: {str(e)}")


@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "jf_segments_loaded": len(jf_segments)}


@app.post("/api/reload-jf")
async def reload_jf_segments():
    """重新加载约定片段"""
    global jf_segments, jf_retriever
    try:
        jf_segments = jf_loader.load()
        jf_retriever = JFRetriever(jf_segments)
        return {"status": "success", "jf_segments_loaded": len(jf_segments)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/output-formats", response_model=OutputFormatsResponse)
async def get_output_formats(request: OutputFormatsRequest):
    """获取其他输出格式（紧凑格式和Deep Finesse格式）"""
    try:
        # 将字典转换回Hand对象
        position_map = {
            "南": Position.SOUTH,
            "西": Position.WEST,
            "北": Position.NORTH,
            "东": Position.EAST
        }
        
        hands = {}
        for pos_name, hand_data in request.hands.items():
            pos = position_map.get(pos_name)
            if pos:
                hand = Hand(
                    spades=hand_data.get("spades", ""),
                    hearts=hand_data.get("hearts", ""),
                    diamonds=hand_data.get("diamonds", ""),
                    clubs=hand_data.get("clubs", "")
                )
                hands[pos] = hand
        
        # 获取庄家位置
        dealer_pos = position_map.get(request.dealer, Position.SOUTH)
        
        # 获取人类位置（从position_roles中提取）
        human_pos = None
        if request.position_roles:
            for pos_name, role in request.position_roles.items():
                if role == 'human':
                    human_pos = position_map.get(pos_name)
                    break  # 取第一个人类位置
        
        # 叫牌序列格式已经是 (南)1S-(西)pass 格式，无需转换
        bidding_str = request.bidding_sequence

        # 解析首攻字符串（格式 "西:S5" 或 "西:♠5"），提取纯卡牌部分给 DF 格式
        lead_card = None
        if request.opening_lead:
            parsed = _parse_opening_lead(request.opening_lead)
            if parsed:
                lead_card = parsed["card"]  # 如 "S5"

        # 只生成需要的格式，跳过 graphic output
        compact = generate_compact_output(hands)
        deep_finesse = generate_deep_finesse_output(hands, bidding_str, dealer_pos, lead_card)
        
        return OutputFormatsResponse(
            compact=compact,
            deep_finesse=deep_finesse
        )
    except Exception as e:
        print(f"[ERROR] 获取输出格式失败: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class AnalyzeContractRequest(BaseModel):
    deep_finesse_format: str


class AnalyzeContractResponse(BaseModel):
    success: bool
    contract: Optional[str] = None
    declarer: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    deal_file: Optional[str] = None


@app.post("/api/analyze-contract", response_model=AnalyzeContractResponse)
async def analyze_contract(request: AnalyzeContractRequest):
    """检验定约接口 - 调用Deep Finesse分析"""
    try:
        df_deal = parse_df_deal(request.deep_finesse_format)
        
        if not df_deal["north"] or not df_deal["south"]:
            return AnalyzeContractResponse(
                success=False,
                error="解析Deep Finesse格式失败"
            )
        
        hands_dict = {
            "北": df_format_to_hand(df_deal['north']),
            "西": df_format_to_hand(df_deal['west']) if df_deal['west'] else "",
            "南": df_format_to_hand(df_deal['south']),
            "东": df_format_to_hand(df_deal['east']) if df_deal['east'] else ""
        }
        
        import asyncio
        result = await asyncio.to_thread(
            analyze_with_deep_finesse,
            hands=hands_dict,
            contract=df_deal['contract'],
            declarer=df_deal['declarer'],
            onlead=df_deal['onlead'],
            lead=df_deal['lead']
        )
        
        return AnalyzeContractResponse(
            success=result.get("success", False),
            contract=result.get("contract"),
            declarer=result.get("declarer"),
            message=result.get("message"),
            error=result.get("error"),
            deal_file=result.get("deal_file")
        )
    except Exception as e:
        print(f"[ERROR] 检验定约失败: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class CustomDealRequest(BaseModel):
    input_text: str


class CustomDealResponse(BaseModel):
    hands: Dict[str, dict]
    dealer: str
    success: bool
    message: Optional[str] = None
    opening_lead: Optional[str] = None


def convert_10_to_T(hand_str: str) -> str:
    result = re.sub(r'([♠♥♦♣])10', r'\1T', hand_str)
    result = re.sub(r'([♠♥♦♣SsHhDdCc])10', r'\1T', result)
    result = result.replace('10', 'T')
    return result


def _extract_dealer_from_bidding(bidding):
    """从叫牌序列中提取发牌人位置（第一个叫牌的位置）"""
    if not bidding or bidding == "null":
        return "南"
    if isinstance(bidding, list) and len(bidding) > 0:
        first = bidding[0]
        if ":" in first:
            pos = first.split(":", 1)[0].strip()
            if pos in ["南", "西", "北", "东"]:
                return pos
    return "南"


def _format_bidding_sequence(bidding):
    """将AI识别返回的叫牌序列格式化为标准字符串"""
    if not bidding or bidding == "null":
        return None
    if isinstance(bidding, list):
        formatted_bids = []
        ended_by_marker = False
        for item in bidding:
            if ended_by_marker:
                # "=" 之后的所有叫品一律丢弃（叫牌已结束）
                continue
            if ":" in item:
                pos, bid = item.split(":", 1)
                pos = pos.strip()
                # 检测并去除 "=" 叫牌结束标记
                has_end_marker = "=" in bid
                # 去除 "=" 后再去除首尾的 "-"、"/" 等符号（处理 "pass-"、"pass--"、"-p" 等情况）
                cleaned = bid.replace("=", "").strip().strip("-/").strip()
                # 标准化 pass 的多种表示形式
                if cleaned.lower() in ["pass", "p", "不叫"] or cleaned in ["-", "/", ""]:
                    bid = "pass"
                else:
                    bid = cleaned
                # 若原叫品只是"="或符号（无实质内容），按pass处理
                if has_end_marker and bid == "":
                    bid = "pass"
                formatted_bids.append(f"({pos}){bid}")
                if has_end_marker:
                    ended_by_marker = True
            else:
                formatted_bids.append(item)
        return "-".join(formatted_bids) + "-"
    return bidding


def _normalize_vulnerability(vul):
    """将AI识别返回的局况标准化为 'NV'/'NS'/'EW'/'All' 之一"""
    if not vul or vul == "null":
        return None
    if isinstance(vul, str):
        v = vul.strip().lower()
        if v in ("nv", "none", "none vul", "none vulnerable", "双无", "双无局"):
            return "NV"
        if v in ("ns", "ns vul", "n-s", "n/s", "南北", "南北有局", "南北方有局"):
            return "NS"
        if v in ("ew", "ew vul", "e-w", "e/w", "东西", "东西有局", "东西方有局"):
            return "EW"
        if v in ("all", "both", "both vul", "both vulnerable", "双有", "双有局"):
            return "All"
        if "双无" in v or "none" in v:
            return "NV"
        if "双有" in v or "both" in v:
            return "All"
        if "南北" in v or "ns" in v:
            return "NS"
        if "东西" in v or "ew" in v:
            return "EW"
    return None


def _parse_contract_string(contract_str):
    """从视觉识别返回的定约字符串解析为结构化信息
    支持格式: "4H 由南做庄", "3NT 由北做庄", "4SX 由东做庄" 等
    """
    if not contract_str or contract_str == "null":
        return {}
    
    import re
    result = {}
    
    print(f"[DEBUG] _parse_contract_string input: '{contract_str}'")
    
    # 解析加倍/再加倍
    doubled = False
    redoubled = False
    contract_part = contract_str
    if "XX" in contract_part:
        redoubled = True
        doubled = True
        contract_part = contract_part.replace("XX", "")
    elif "X" in contract_part:
        doubled = True
        contract_part = contract_part.replace("X", "")
    
    result["doubled"] = doubled
    result["redoubled"] = redoubled
    
    print(f"[DEBUG] contract_part after removing X: '{contract_part}'")
    
    # 解析级别和花色 - 支持多种格式
    # 优先匹配 "级别+花色" 如 3NT, 4H, 2S
    level_match = re.search(r'(\d)([SHDC]|NT)', contract_part, re.IGNORECASE)
    if level_match:
        result["level"] = int(level_match.group(1))
        result["suit"] = level_match.group(2).upper()
    else:
        # 尝试匹配中文格式如 "3无将" 或 "3NT"
        level_match2 = re.search(r'(\d)', contract_part)
        suit_match = re.search(r'(NT|无将|[SHDC])', contract_part, re.IGNORECASE)
        if level_match2 and suit_match:
            result["level"] = int(level_match2.group(1))
            suit_str = suit_match.group(1).upper()
            result["suit"] = "NT" if suit_str in ("NT", "无将") else suit_str
    
    print(f"[DEBUG] parsed result: {result}")
    
    # 解析庄家
    declarer_match = re.search(r'由([东西南北])做庄', contract_str)
    if not declarer_match:
        # 尝试其他格式如 "庄家:南" 或直接 "南"
        declarer_match = re.search(r'[庄做]家?[:：]?\s*([东西南北])', contract_str)
    if declarer_match:
        result["declarer"] = declarer_match.group(1)
    
    return result


def _parse_opening_lead(lead_str):
    """从视觉识别返回的首攻字符串解析为首攻信息
    支持格式: "西:S5", "东:HQ" 等
    """
    if not lead_str or lead_str == "null":
        return None
    
    print(f"[DEBUG] _parse_opening_lead input: '{lead_str}'")
    
    import re
    match = re.match(r'([东西南北]):([SHDC])(\w+)', lead_str, re.IGNORECASE)
    if match:
        result = {
            "position": match.group(1),
            "card": f"{match.group(2).upper()}{match.group(3)}"
        }
        print(f"[DEBUG] _parse_opening_lead result: {result}")
        return result
    
    # 尝试更宽松的匹配：位置可能用中文冒号，花色可能用♠♥♦♣
    suit_map = {'♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C'}
    match2 = re.match(r'([东西南北])[:：]\s*([♠♥♦♣SHDCshdc])(\w+)', lead_str)
    if match2:
        suit = suit_map.get(match2.group(2), match2.group(2).upper())
        result = {
            "position": match2.group(1),
            "card": f"{suit}{match2.group(3)}"
        }
        print(f"[DEBUG] _parse_opening_lead result (loose match): {result}")
        return result
    
    print(f"[DEBUG] _parse_opening_lead: no match found")
    return None


def _parse_vision_hands(result):
    """从视觉识别结果中解析手牌，返回 (hands_dict, validation_errors)"""
    import re
    
    def parse_hand_with_suits(hand_str: str) -> Hand:
        """按花色符号解析手牌，正确处理缺门花色。
        例如 "♠KT85 ♥AT863 ♣63" → 黑桃KT85, 红心AT863, 方块空, 草花63
        """
        hand_str = convert_10_to_T(hand_str)
        # 用花色符号分割，保留花色标记
        suit_map = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}
        suits = {"spades": "", "hearts": "", "diamonds": "", "clubs": ""}
        
        # 找到所有花色符号的位置
        suit_positions = []
        for m in re.finditer(r'[♠♥♦♣]', hand_str):
            suit_positions.append((m.start(), m.group()))
        
        # 按花色符号提取每个花色的牌
        for i, (pos, symbol) in enumerate(suit_positions):
            # 牌面从花色符号后开始，到下一个花色符号前结束
            start = pos + 1
            end = suit_positions[i + 1][0] if i + 1 < len(suit_positions) else len(hand_str)
            card_str = hand_str[start:end].strip()
            # 统一各种破折号为标准"-"，再清理：只保留有效的牌面字符
            card_str = re.sub(r'[-—–－―‐]', '-', card_str)
            card_str = re.sub(r'[^AKQJT98765432]', '', card_str)
            suits[suit_map[symbol]] = card_str
        
        return Hand(
            spades=suits["spades"],
            hearts=suits["hearts"],
            diamonds=suits["diamonds"],
            clubs=suits["clubs"]
        )
    
    hands = {}
    position_map = {
        "南家手牌": Position.SOUTH,
        "西家手牌": Position.WEST,
        "北家手牌": Position.NORTH,
        "东家手牌": Position.EAST
    }
    
    for key, pos in position_map.items():
        hand_str = result.get(key)
        if hand_str and hand_str != "null":
            hands[pos] = parse_hand_with_suits(hand_str)
    
    validation_errors = []
    for pos, hand in hands.items():
        total_cards = len(hand.spades) + len(hand.hearts) + len(hand.diamonds) + len(hand.clubs)
        if total_cards != 13:
            validation_errors.append(f"{get_position_name(pos)}手牌有{total_cards}张，不是13张")

    # 重复牌张校验：同一张牌不能出现在多手
    all_cards = {}  # "♠A" → [positions]
    for pos, hand in hands.items():
        for suit_symbol, suit_attr in [("♠", "spades"), ("♥", "hearts"), ("♦", "diamonds"), ("♣", "clubs")]:
            for rank in getattr(hand, suit_attr):
                card_key = f"{suit_symbol}{rank}"
                if card_key not in all_cards:
                    all_cards[card_key] = []
                all_cards[card_key].append(get_position_name(pos))
    duplicates = [(card, positions) for card, positions in all_cards.items() if len(positions) > 1]
    if duplicates:
        dup_desc = "; ".join(f"{card}出现在{','.join(ps)}" for card, ps in duplicates[:5])
        if len(duplicates) > 5:
            dup_desc += f"等{len(duplicates)}处重复"
        validation_errors.append(f"牌张重复: {dup_desc}")

    # 跨手校验：每种花色四手合计必须为13（仅四手齐全时做精确校验）
    if len(hands) == 4:
        suit_totals = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
        for hand in hands.values():
            suit_totals["♠"] += len(hand.spades)
            suit_totals["♥"] += len(hand.hearts)
            suit_totals["♦"] += len(hand.diamonds)
            suit_totals["♣"] += len(hand.clubs)
        for suit, total in suit_totals.items():
            if total != 13:
                validation_errors.append(f"花色{suit}四手合计{total}张，应为13张（可能花色错位）")
    elif len(hands) == 3:
        # 三手时可检测明显超标
        suit_totals = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
        for hand in hands.values():
            suit_totals["♠"] += len(hand.spades)
            suit_totals["♥"] += len(hand.hearts)
            suit_totals["♦"] += len(hand.diamonds)
            suit_totals["♣"] += len(hand.clubs)
        for suit, total in suit_totals.items():
            if total > 13:
                validation_errors.append(f"花色{suit}三手已有{total}张，超过13张（可能花色错位）")

    return hands, validation_errors


def _hands_to_response_dict(hands):
    """将 hands dict (Position -> Hand) 转为 API 响应格式"""
    return {get_position_name(pos): hand_to_dict(hand) for pos, hand in hands.items()}





@app.post("/api/custom-deal", response_model=CustomDealResponse)
async def custom_deal(request: CustomDealRequest):
    """自定义牌局接口

    支持部分输入：用户可只修改1-3行，空缺位置返回空手牌（由前端保留原数据或清空）
    空行表示未编辑，非空行（即使0张牌）表示主动修改/清空
    """
    try:
        # 不过滤空行，保留位置信息
        raw_lines = request.input_text.split("\n")
        lines = [l.strip() for l in raw_lines]
        non_empty_lines = [l for l in lines if l]

        if any(line.startswith("Deal:") for line in non_empty_lines):
            df_result = parse_df_deal(request.input_text)
            hands = {}

            if df_result.get("north"):
                hands[Position.NORTH] = parse_hand_string(df_format_to_hand(df_result["north"]))
            if df_result.get("west"):
                hands[Position.WEST] = parse_hand_string(df_format_to_hand(df_result["west"]))
            if df_result.get("east"):
                hands[Position.EAST] = parse_hand_string(df_format_to_hand(df_result["east"]))
            if df_result.get("south"):
                hands[Position.SOUTH] = parse_hand_string(df_format_to_hand(df_result["south"]))

            if len(hands) == 4:
                hands_dict = _hands_to_response_dict(hands)
                # 提取首攻信息：DF格式中 OnLead + Lead 组合为 "位置:牌张"
                opening_lead = None
                onlead_en_to_cn = {"NORTH": "北", "SOUTH": "南", "EAST": "东", "WEST": "西"}
                if df_result.get("lead") and df_result.get("onlead"):
                    lead_pos = onlead_en_to_cn.get(df_result["onlead"].upper(), df_result["onlead"])
                    opening_lead = f"{lead_pos}:{df_result['lead']}"
                return CustomDealResponse(
                    hands=hands_dict,
                    dealer="南",
                    success=True,
                    message="牌局已加载（Deep Finesse格式）",
                    opening_lead=opening_lead,
                )
            else:
                return CustomDealResponse(
                    hands={},
                    dealer="南",
                    success=False,
                    message=f"牌局解析不完整，缺少 {4 - len(hands)} 家手牌"
                )
        elif 1 <= len(non_empty_lines) <= 4:
            input_text = convert_10_to_T(request.input_text)
            hands = parse_deal_input(input_text)
            if hands:
                hands_dict = _hands_to_response_dict(hands)
                # 补齐缺失位置为空手牌（前端根据原始文本决定保留原数据或清空）
                for pos_name in ["南", "西", "北", "东"]:
                    if pos_name not in hands_dict:
                        hands_dict[pos_name] = {"spades": "", "hearts": "", "diamonds": "", "clubs": "", "hcp": 0}
                return CustomDealResponse(
                    hands=hands_dict,
                    dealer="南",
                    success=True,
                    message="牌局已加载"
                )
            else:
                return CustomDealResponse(
                    hands={},
                    dealer="南",
                    success=False,
                    message="牌局解析失败，请检查格式"
                )
        else:
            return CustomDealResponse(
                hands={},
                dealer="南",
                success=False,
                message=f"需要输入1-4行标准格式或Deep Finesse格式，当前输入了{len(non_empty_lines)}行"
            )
    except Exception as e:
        print(f"[ERROR] 自定义牌局失败: {str(e)}")
        traceback.print_exc()
        return CustomDealResponse(
            hands={},
            dealer="南",
            success=False,
            message=f"解析失败: {str(e)}"
        )


class ImageDealResponse(BaseModel):
    hands: Dict[str, dict]
    dealer: str
    success: bool
    message: Optional[str] = None
    bidding_sequence: Optional[str] = None
    contract: Optional[str] = None
    contract_level: Optional[int] = None
    contract_suit: Optional[str] = None
    contract_declarer: Optional[str] = None
    contract_doubled: Optional[bool] = None
    contract_redoubled: Optional[bool] = None
    opening_lead: Optional[str] = None
    page_type: Optional[str] = None
    vulnerability: Optional[str] = None


@app.post("/api/image-deal", response_model=ImageDealResponse)
async def image_deal(image: bytes = File(..., description="图片文件")):
    """从图片读取牌局接口"""
    try:
        import time
        t_start = time.time()

        print(f"[INFO] 收到图片上传请求，大小: {len(image)} bytes")
        
        # 保存上传的文件到临时目录
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
            tmp.write(image)
            image_path = tmp.name
        
        print(f"[INFO] 图片已保存到临时文件: {image_path}")
        
        try:
            print(f"[INFO] 开始调用vision_client识别图片...")
            # 视觉识别（最长 120s）卸载到线程，避免阻塞事件循环（P0-1 修复）
            result = await asyncio.to_thread(vision_client.read_cards_from_image, image_path)
            print(f"[INFO] vision_client返回结果: {result}")
        finally:
            # 清理临时文件
            if os.path.exists(image_path):
                os.unlink(image_path)
        
        if "error" in result:
            print(f"[ERROR] 图片识别失败: {result['error']}")
            if "raw_response" in result:
                print(f"[ERROR] 原始响应: {result['raw_response']}")
            return ImageDealResponse(
                hands={},
                dealer="南",
                success=False,
                message=f"识别失败: {result['error']}"
            )

        hands, validation_errors = _parse_vision_hands(result)

        # 解析叫牌、定约、首攻、局况（手牌不完整时也尽量提取）
        bidding_str = _format_bidding_sequence(result.get("叫牌序列"))
        contract_str = result.get("当前定约")
        contract_info = _parse_contract_string(contract_str)
        lead_info = _parse_opening_lead(result.get("首攻"))
        dealer = _extract_dealer_from_bidding(result.get("叫牌序列"))
        vulnerability = _normalize_vulnerability(result.get("局况"))

        # 无最低家数要求：识别到几家就是几家，缺失位置填空牌
        hands_dict = _hands_to_response_dict(hands)
        for pos_name in ["南", "西", "北", "东"]:
            if pos_name not in hands_dict:
                hands_dict[pos_name] = {"spades": "", "hearts": "", "diamonds": "", "clubs": "", "hcp": 0}
        warnings = []
        if validation_errors:
            warnings.extend(validation_errors)
        missing = [p for p in ["南", "西", "北", "东"] if p not in [get_position_name(pos) for pos in hands]]
        if missing:
            warnings.append(f"缺少{','.join(missing)}的手牌（显示为未知）")

        print(f"[INFO] 图片识别总耗时: {time.time() - t_start:.1f}s")
        return ImageDealResponse(
            hands=hands_dict,
            dealer=dealer,
            success=True,
            message=("牌局已加载" if not warnings else "识别完成（" + "; ".join(warnings) + "）"),
            bidding_sequence=bidding_str,
            contract=contract_str,
            contract_level=contract_info.get("level"),
            contract_suit=contract_info.get("suit"),
            contract_declarer=contract_info.get("declarer"),
            contract_doubled=contract_info.get("doubled", False),
            contract_redoubled=contract_info.get("redoubled", False),
            opening_lead=f"{lead_info['position']}:{lead_info['card']}" if lead_info else None,
            page_type=result.get("页面类型", "未知"),
            vulnerability=vulnerability
        )
    except Exception as e:
        print(f"[ERROR] 图片识别失败: {str(e)}")
        traceback.print_exc()
        return ImageDealResponse(
            hands={},
            dealer="南",
            success=False,
            message=f"识别失败: {str(e)}"
        )


class TriggerScreenshotResponse(BaseModel):
    success: bool
    message: str
    screenshot_path: Optional[str] = None


# 记录触发截屏前的剪贴板内容哈希，轮询时只接受不同的内容
_pre_screenshot_hash: Optional[str] = None
# 单家截屏识别的独立哈希（避免与整体识别互相干扰）
_pre_single_hand_hash: Optional[str] = None


@app.post("/api/trigger-screenshot")
async def trigger_screenshot():
    """触发系统截屏快捷键，同时记录当前剪贴板内容的哈希"""
    global _pre_screenshot_hash, _pre_single_hand_hash
    # 先读当前剪贴板内容并记录哈希，轮询时跳过旧内容（避免误识别旧图片）
    try:
        result = read_clipboard_image()
        if result is not None:
            image_data, _ = result
            old_hash = hashlib.md5(image_data).hexdigest()
            _pre_screenshot_hash = old_hash
            _pre_single_hand_hash = old_hash
            print(f"[INFO] 触发截屏，记录旧剪贴板哈希: {old_hash[:8]}...")
        else:
            _pre_screenshot_hash = None
            _pre_single_hand_hash = None
            print(f"[INFO] 触发截屏，剪贴板为空")
    except Exception as e:
        _pre_screenshot_hash = None
        _pre_single_hand_hash = None
        print(f"[INFO] 触发截屏，读取剪贴板失败: {e}")
    success = trigger_screenshot_shortcut()
    if success:
        return {"success": True, "message": "截屏已触发，请在截屏工具中选择区域后点击识别"}
    else:
        return {"success": False, "message": "触发截屏失败"}


def _recognize_single_hand_image(image_path: str, position: str) -> dict:
    """识别单张图片中的某一家手牌。剪贴板与上传两条路径共用。"""
    import time
    t_start = time.time()
    result = vision_client.read_single_hand_from_image(image_path, position)
    if "error" in result:
        return {"success": False, "message": f"识别失败: {result['error']}"}

    hand_str = result.get("手牌") or ""
    if not hand_str:
        return {"success": False, "message": "未识别到手牌"}

    hand_str = convert_10_to_T(hand_str)
    suit_map = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}
    suits = {"spades": "", "hearts": "", "diamonds": "", "clubs": ""}
    suit_positions = [(m.start(), m.group()) for m in re.finditer(r'[♠♥♦♣]', hand_str)]
    for i, (pos, symbol) in enumerate(suit_positions):
        start = pos + 1
        end = suit_positions[i + 1][0] if i + 1 < len(suit_positions) else len(hand_str)
        card_str = hand_str[start:end].strip()
        card_str = re.sub(r'[-—–－―‐]', '-', card_str)
        card_str = re.sub(r'[^AKQJT98765432]', '', card_str)
        suits[suit_map[symbol]] = card_str

    hand = Hand(spades=suits["spades"], hearts=suits["hearts"], diamonds=suits["diamonds"], clubs=suits["clubs"])
    total_cards = len(hand.spades) + len(hand.hearts) + len(hand.diamonds) + len(hand.clubs)

    warnings = []
    if total_cards != 13:
        warnings.append(f"识别到{total_cards}张牌（标准为13张）")

    hand_dict = hand_to_dict(hand)
    hand_dict["hcp"] = sum(4 if c == "A" else 3 if c == "K" else 2 if c == "Q" else 1 if c == "J" else 0
                           for c in (hand.spades + hand.hearts + hand.diamonds + hand.clubs).upper())

    print(f"[INFO] 单家识别 {position}家完成: {total_cards}张, 耗时: {time.time() - t_start:.1f}s")
    return {
        "success": True,
        "message": "识别成功" if not warnings else "识别完成（" + "; ".join(warnings) + "）",
        "position": position,
        "hand": hand_dict,
        "total_cards": total_cards
    }


@app.post("/api/single-hand-image")
async def single_hand_image(position: str = Query(...), image: bytes = File(..., description="单家手牌图片")):
    """上传单家手牌图片并识别（移动端/相册路径）。"""
    try:
        if position not in ["南", "西", "北", "东"]:
            return {"success": False, "message": f"无效的位置: {position}"}
        print(f"[INFO] 收到 {position}家手牌图片上传请求，大小: {len(image)} bytes")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(image)
            image_path = tmp.name
        try:
            # 视觉识别（最长 120s）卸载到线程，避免阻塞事件循环（P0-1 修复）
            return await asyncio.to_thread(_recognize_single_hand_image, image_path, position)
        finally:
            if os.path.exists(image_path):
                os.unlink(image_path)
    except Exception as e:
        print(f"[ERROR] 上传单家识别失败: {str(e)}")
        traceback.print_exc()
        return {"success": False, "message": f"上传单家识别失败: {str(e)}"}


@app.post("/api/read-hand-clipboard")
async def read_hand_clipboard(position: str = ""):
    """从剪贴板读取截图，识别单家手牌"""
    global _pre_single_hand_hash
    try:
        if position not in ["南", "西", "北", "东"]:
            return {"success": False, "message": f"无效的位置: {position}"}

        result = read_clipboard_image()
        if result is None:
            return {"success": False, "message": "剪贴板中没有图片，请先截屏"}

        image_data, fmt = result

        current_hash = hashlib.md5(image_data).hexdigest()
        if current_hash == _pre_single_hand_hash:
            print(f"[INFO] 单家识别剪贴板图片无变化（哈希: {current_hash[:8]}...），跳过")
            return {"success": False, "message": "剪贴板图片无变化（已处理过），请先截取新截图"}

        print(f"[INFO] 单家识别 {position}家，新剪贴板内容（哈希: {current_hash[:8]}...）")

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{fmt}") as tmp:
            tmp.write(image_data)
            image_path = tmp.name

        print(f"[INFO] 单家截图已保存到: {image_path} ({fmt})")

        try:
            # 视觉识别（最长 120s）卸载到线程，避免阻塞事件循环（P0-1 修复）
            result = await asyncio.to_thread(_recognize_single_hand_image, image_path, position)
        finally:
            os.unlink(image_path)

        _pre_single_hand_hash = current_hash
        return result

    except Exception as e:
        print(f"[ERROR] 单家识别失败: {str(e)}")
        traceback.print_exc()
        return {
            "success": False,
            "message": f"单家识别失败: {str(e)}"
        }


@app.post("/api/read-clipboard")
async def read_clipboard():
    """从剪贴板读取截图"""
    global _pre_screenshot_hash
    try:
        result = read_clipboard_image()
        if result is None:
            return {"success": False, "message": "剪贴板中没有图片，请先截屏"}

        image_data, fmt = result

        # 哈希防重：与上一轮已处理过的图片比较，避免重复识别同一截图
        current_hash = hashlib.md5(image_data).hexdigest()
        if current_hash == _pre_screenshot_hash:
            print(f"[INFO] 剪贴板图片无变化（哈希: {current_hash[:8]}...），跳过")
            return {"success": False, "message": "剪贴板图片无变化（已处理过），请先截取新截图"}

        print(f"[INFO] 检测到新剪贴板内容（当前: {current_hash[:8]}...）")

        import time
        t_clipboard = time.time()

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{fmt}") as tmp:
            tmp.write(image_data)
            image_path = tmp.name

        print(f"[INFO] 截图已保存到: {image_path} ({fmt})")

        # 视觉识别（最长 120s）卸载到线程，避免阻塞事件循环（P0-1 修复）
        result = await asyncio.to_thread(vision_client.read_cards_from_image, image_path)
        print(f"[DEBUG] vision_client返回结果: {result}")

        os.unlink(image_path)

        if "error" in result:
            return {
                "success": False,
                "message": f"识别失败: {result['error']}"
            }

        hands, validation_errors = _parse_vision_hands(result)

        # 更新哈希，避免重复处理同一张截图
        _pre_screenshot_hash = current_hash

        # 解析叫牌、定约、首攻（手牌不完整时也尽量提取）
        bidding_str = _format_bidding_sequence(result.get("叫牌序列"))
        contract_str = result.get("当前定约")
        contract_info = _parse_contract_string(contract_str)
        lead_info = _parse_opening_lead(result.get("首攻"))
        dealer = _extract_dealer_from_bidding(result.get("叫牌序列"))

        # 无最低家数要求：识别到几家就是几家，缺失位置填空牌
        hands_dict = _hands_to_response_dict(hands)
        for pos_name in ["南", "西", "北", "东"]:
            if pos_name not in hands_dict:
                hands_dict[pos_name] = {"spades": "", "hearts": "", "diamonds": "", "clubs": "", "hcp": 0}
        warnings = []
        if validation_errors:
            warnings.extend(validation_errors)
        missing = [p for p in ["南", "西", "北", "东"] if p not in [get_position_name(pos) for pos in hands]]
        if missing:
            warnings.append(f"缺少{','.join(missing)}的手牌（显示为未知）")

        print(f"[INFO] 截屏识别总耗时: {time.time() - t_clipboard:.1f}s")
        return {
            "success": True,
            "message": ("识别成功" if not warnings else "识别完成（" + "; ".join(warnings) + "）"),
            "hands": hands_dict,
            "dealer": dealer,
            "bidding_sequence": bidding_str,
            "contract": contract_str,
            "contract_level": contract_info.get("level"),
            "contract_suit": contract_info.get("suit"),
            "contract_declarer": contract_info.get("declarer"),
            "contract_doubled": contract_info.get("doubled", False),
            "contract_redoubled": contract_info.get("redoubled", False),
            "opening_lead": f"{lead_info['position']}:{lead_info['card']}" if lead_info else None,
            "vulnerability": vulnerability,
            "page_type": result.get("页面类型", "未知")
        }

    except Exception as e:
        print(f"[ERROR] 读取剪贴板失败: {str(e)}")
        traceback.print_exc()
        return {
            "success": False,
            "message": f"读取剪贴板失败: {str(e)}"
        }


@app.get("/api/diag-clipboard")
async def diag_clipboard():
    """诊断：测试剪贴板读取，返回详细耗时和结果"""
    import time as _time
    results = []

    # 测试1：启动PowerShell时间
    t0 = _time.time()
    try:
        subprocess.run(["powershell", "-Command", "Write-Output 'POWERSHELL_OK'"],
                       capture_output=True, text=True, timeout=5)
        ps_launch_time = _time.time() - t0
        results.append(f"PowerShell启动: {ps_launch_time:.2f}s")
    except Exception as e:
        results.append(f"PowerShell启动失败: {e}")
        return {"success": False, "diagnostics": results}

    # 测试2：测试剪贴板读取（含耗时）
    t0 = _time.time()
    img_result = read_clipboard_image()
    clipboard_time = _time.time() - t0

    if img_result is None:
        results.append(f"剪贴板读取: {clipboard_time:.2f}s → 无图片")
        results.append("提示：请先使用 Win+Shift+S 手动截屏，或在测试前在网页中完成截屏")
    else:
        image_data, fmt = img_result
        results.append(f"剪贴板读取: {clipboard_time:.2f}s → 有图片 ({len(image_data)}字节, {fmt})")
        results.append("图片识别管道正常！如果截屏识别仍然超时，问题在前端轮询环节。")

    return {"success": True, "diagnostics": results}


class DoubleDummyRequest(BaseModel):
    hands: Dict[str, dict]


class DoubleDummyResponse(BaseModel):
    success: bool
    table_data: Optional[Dict] = None
    error: Optional[str] = None


@app.post("/api/double-dummy", response_model=DoubleDummyResponse)
async def double_dummy_analysis(request: DoubleDummyRequest):
    """双明手分析接口"""
    if not ENDPLAY_AVAILABLE:
        return DoubleDummyResponse(
            success=False,
            error="双明手分析功能不可用，请确保 DirectDDS 模块可用"
        )
    
    try:
        position_map = {
            "南": Position.SOUTH,
            "西": Position.WEST,
            "北": Position.NORTH,
            "东": Position.EAST
        }
        
        hands_dict = {}
        
        for pos_name, hand_data in request.hands.items():
            hand = Hand(
                spades=hand_data.get("spades", ""),
                hearts=hand_data.get("hearts", ""),
                diamonds=hand_data.get("diamonds", ""),
                clubs=hand_data.get("clubs", "")
            )
            hands_dict[pos_name] = hand.to_simple_string()
        
        # 双明手批分析（秒级到数十秒）卸载到线程，避免阻塞事件循环（P0-1 修复）
        result = await asyncio.to_thread(analyze_all_contracts, hands_dict)
        
        if result.get("success"):
            return DoubleDummyResponse(
                success=True,
                table_data=result.get("results")
            )
        else:
            return DoubleDummyResponse(
                success=False,
                error=result.get("error", "分析失败")
            )
    except Exception as e:
        print(f"[ERROR] 双明手分析失败: {str(e)}")
        traceback.print_exc()
        return DoubleDummyResponse(
            success=False,
            error=f"分析失败: {str(e)}"
        )


# ==================== 打牌相关API ====================

from bridge.play_types import Card, Contract, PlayPhase
from bridge.play_service import PlayService

# ── 打牌服务会话隔离（方案A）──
# PlayService 每会话独立实例，避免多用户/多局并发互相覆盖共享 state.hands（窜牌根因）。
# LLM client 复用全局 get_llm_client()，不随会话新建，性能开销可忽略。
_play_services_lock = threading.Lock()
_play_services = {}  # session_id -> (PlayService, last_access_ts)
_PLAY_SESSION_TTL = 3600  # 会话空闲 1 小时自动回收
_session_cleanup_task = None


def get_play_service(session_id: str = "default"):
    """按会话获取 PlayService，不存在则新建；LLM client 复用全局 get_llm_client()。"""
    now = time.time()
    with _play_services_lock:
        entry = _play_services.get(session_id)
        if entry is None:
            service = PlayService(get_llm_client())
        else:
            service, _ = entry
        _play_services[session_id] = (service, now)
        return service


def _sweep_expired_sessions():
    now = time.time()
    expired = [sid for sid, (_, ts) in _play_services.items() if now - ts > _PLAY_SESSION_TTL]
    for sid in expired:
        _play_services.pop(sid, None)


async def _session_cleanup_loop():
    while True:
        await asyncio.sleep(300)
        with _play_services_lock:
            _sweep_expired_sessions()


@app.on_event("startup")
async def _start_session_cleanup():
    global _session_cleanup_task
    _session_cleanup_task = asyncio.create_task(_session_cleanup_loop())


@app.on_event("shutdown")
async def _stop_session_cleanup():
    global _session_cleanup_task
    if _session_cleanup_task:
        _session_cleanup_task.cancel()


class PlayInitRequest(BaseModel):
    hands: Dict[str, dict]
    contract: str
    declarer: str
    player_roles: Optional[Dict[str, str]] = None
    doubled: bool = False
    redoubled: bool = False
    bidding_sequence: Optional[str] = None
    bid_history: Optional[str] = None  # 叫牌序列，用于MCTS约束采样
    bid_meanings: Optional[str] = None  # 叫牌含义文本，复用LLM已分析信息
    vulnerability: Optional[str] = None  # 局况: "NV"/"NS"/"EW"/"All"
    session_id: str = "default"  # 打牌会话隔离标识


class PlayInitResponse(BaseModel):
    success: bool
    state: Optional[dict] = None
    current_player: Optional[str] = None
    dummy: Optional[str] = None
    lead_player: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/play/init", response_model=PlayInitResponse)
async def play_init(request: PlayInitRequest):
    """初始化打牌"""
    try:
        service = get_play_service(request.session_id)
        state = service.initialize(
            hands=request.hands,
            contract_str=request.contract,
            declarer=request.declarer,
            player_roles=request.player_roles,
            doubled=request.doubled,
            redoubled=request.redoubled,
            bidding_sequence=request.bidding_sequence or "未提供",
            bid_history=request.bid_history or "",
            bid_meanings=request.bid_meanings or "",
            vulnerability=_normalize_vulnerability(request.vulnerability) or "NV",
        )

        return PlayInitResponse(
            success=True,
            state=state.to_dict(),
            current_player=state.current_player,
            dummy=state.dummy,
            lead_player=state.lead_player,
            message=f"打牌初始化成功，{state.lead_player}首攻"
        )
    except Exception as e:
        print(f"[ERROR] 初始化打牌失败: {str(e)}")
        traceback.print_exc()
        return PlayInitResponse(
            success=False,
            error=f"初始化失败: {str(e)}"
        )


class PlayCardRequest(BaseModel):
    position: str
    card: dict  # {"suit": "♠", "rank": "A"}
    session_id: str = "default"


class PlayCardResponse(BaseModel):
    success: bool
    state: Optional[dict] = None
    trick_winner: Optional[str] = None
    trick_complete: bool = False
    declarer_tricks: int = 0
    defender_tricks: int = 0
    is_complete: bool = False
    result: Optional[dict] = None
    message: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/play/card", response_model=PlayCardResponse)
async def play_card(request: PlayCardRequest):
    """出牌"""
    try:
        service = get_play_service(request.session_id)

        state_before = service.get_state()
        tricks_before = len(state_before.tricks) if state_before else 0
        state_snapshot = copy.deepcopy(state_before) if state_before else None

        card = Card(suit=request.card["suit"], rank=request.card["rank"])
        _log = f"[PLAY_CARD] position={request.position} card={card} current_player={state_before.current_player if state_before else 'N/A'} hands[{request.position}]={state_before.hands.get(request.position) if state_before else 'N/A'}"
        print(_log)
        with open("dd_debug.log", "a", encoding="utf-8") as _f:
            _f.write(_log + "\n")
        success, message = service.play_card(request.position, card)
        _log2 = f"[PLAY_CARD] result: success={success} message={message}"
        print(_log2)
        with open("dd_debug.log", "a", encoding="utf-8") as _f:
            _f.write(_log2 + "\n")

        state = service.get_state()
        trick_winner = None
        trick_complete = False

        # 检查是否刚完成一墩（墩数增加了）
        tricks_after = len(state.tricks) if state else 0
        if tricks_after > tricks_before and state:
            trick_winner = state.current_player  # 新一墩的首攻者就是上一墩的赢家
            trick_complete = True

        # 记录DD提示到trick（后台异步计算，不阻塞响应）
        _submit_dd_hint(state_snapshot, state, tricks_before)

        result = None
        is_complete = service.is_complete()
        if is_complete:
            result = service.get_result()
        
        return PlayCardResponse(
            success=success,
            state=service.get_state_dict(),
            trick_winner=trick_winner,
            trick_complete=trick_complete,
            declarer_tricks=state.declarer_tricks if state else 0,
            defender_tricks=state.defender_tricks if state else 0,
            is_complete=is_complete,
            result=result,
            message=message,
            error=None if success else message
        )
    except Exception as e:
        print(f"[ERROR] 出牌失败: {str(e)}")
        traceback.print_exc()
        return PlayCardResponse(
            success=False,
            error=f"出牌失败: {str(e)}"
        )


class PlayUndoResponse(BaseModel):
    success: bool
    state: Optional[dict] = None
    declarer_tricks: Optional[int] = None
    defender_tricks: Optional[int] = None
    is_complete: Optional[bool] = None
    message: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/play/undo", response_model=PlayUndoResponse)
async def undo_play(session_id: str = Query("default")):
    """撤销最近一次出牌"""
    try:
        service = get_play_service(session_id)
        success, message = service.undo_last_card()
        
        state = service.get_state()
        
        return PlayUndoResponse(
            success=success,
            state=service.get_state_dict(),
            declarer_tricks=state.declarer_tricks if state else 0,
            defender_tricks=state.defender_tricks if state else 0,
            is_complete=service.is_complete(),
            message=message
        )
    except Exception as e:
        print(f"[ERROR] 撤销失败: {str(e)}")
        traceback.print_exc()
        return PlayUndoResponse(
            success=False,
            error=f"撤销失败: {str(e)}"
        )


class PlayAIRequest(BaseModel):
    use_reasoning: bool = False
    play_model: Optional[str] = None
    play_engine: Optional[str] = None  # "llm" | "mcts" | "dd" | "perfect" | "alphamu" | "dd_alphamu_llm"
    dd_sample_count: Optional[int] = None  # DD 蒙地卡罗采样数
    dd_alphamu_switch_cards: Optional[int] = None  # DD-αμ-LLM 引擎中盘/残局切换分界
    dd_scoring_mode: Optional[str] = None  # DD 决策计分制: "imp" | "make_rate" | "avg_tricks"
    use_llm_review: bool = False  # DD-αμ-LLM 引擎是否启用 LLM 分组审查（默认关闭）
    session_id: str = "default"


class SetHandRequest(BaseModel):
    position: str
    hand: dict
    session_id: str = "default"


class SetHandResponse(BaseModel):
    success: bool
    state: Optional[dict] = None
    message: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/play/set-hand", response_model=SetHandResponse)
async def set_play_hand(request: SetHandRequest):
    """设置一家的手牌（如首攻后输入明手整手牌）"""
    try:
        service = get_play_service(request.session_id)
        success, message = service.set_hand(request.position, request.hand)
        return SetHandResponse(
            success=success,
            state=service.get_state_dict(),
            message=message,
            error=None if success else message,
        )
    except Exception as e:
        return SetHandResponse(
            success=False,
            error=str(e),
        )


class PlayAIResponse(BaseModel):
    success: bool
    card: Optional[dict] = None
    reasoning: Optional[str] = None
    follow_up: Optional[str] = None
    full_output: Optional[dict] = None
    prompt: Optional[str] = None
    used_model: Optional[str] = None
    used_engine: Optional[str] = None
    elapsed_ms: Optional[int] = None
    state: Optional[dict] = None
    error: Optional[str] = None


@app.post("/api/play/ai-play", response_model=PlayAIResponse)
async def ai_play(request: PlayAIRequest):
    """AI出牌"""
    try:
        service = get_play_service(request.session_id)

        # 临时切换打牌模型（不影响叫牌模型）
        pm_raw = request.play_model or ""
        print(f"[ai_play] play_model={request.play_model!r}, use_reasoning={request.use_reasoning}, engine={request.play_engine}")
        use_doubao_play = is_doubao_model(pm_raw)
        use_reasoning = request.use_reasoning or is_reasoning_model(pm_raw)
        # 豆包需将 ::reasoning 追加到模型名以匹配正确的 endpoint
        if use_doubao_play and use_reasoning:
            pm_raw = f"{get_base_model(pm_raw)}::reasoning"
        original_play_client = service.llm_client  # 记录会话当前客户端，finally 恢复
        actual_model = llm_client.model

        if use_doubao_play:
            doubao_client.set_model(pm_raw)
            if not doubao_client.is_configured():
                available = get_available_models()
                return PlayAIResponse(
                    success=False,
                    used_model=pm_raw,
                    error=f"豆包模型 {pm_raw} 的推理接入点未配置。请在 .env 中设置对应的 endpoint。当前可用: {', '.join(available)}"
                )
            service.llm_client = doubao_client
            actual_model = pm_raw
        elif pm_raw and pm_raw in ALL_MODELS:
            # 请求级浅拷贝：避免并发修改全局 llm_client.model 导致模型串用（F4 修复）
            play_client = copy.copy(llm_client)
            play_client.model = pm_raw
            service.llm_client = play_client
            actual_model = f"{pm_raw}::reasoning" if use_reasoning else pm_raw
        
        try:
            if not service.is_human_turn():
                engine = request.play_engine or DEFAULT_PLAY_ENGINE
                use_mcts = engine == "mcts"
                use_dd = engine == "dd"
                use_perfect = engine == "perfect"
                use_alphamu = engine == "alphamu"
                use_dd_alphamu_llm = engine == "dd_alphamu_llm"
                enable_llm_review = request.use_llm_review
                dd_samples = (request.dd_sample_count
                              if (use_dd or use_dd_alphamu_llm) else None)
                dd_switch_cards = request.dd_alphamu_switch_cards if use_dd_alphamu_llm else None
                dd_scoring_mode = request.dd_scoring_mode if (use_dd or use_dd_alphamu_llm) else None
                t0 = time.time()
                # 记录DD提示所需的出牌前状态
                state_before = service.get_state()
                tricks_before = len(state_before.tricks) if state_before else 0
                state_snapshot = copy.deepcopy(state_before) if state_before else None
                result = await service.get_ai_play(
                    use_reasoning=use_reasoning,
                    use_mcts=use_mcts,
                    use_dd=use_dd,
                    use_perfect=use_perfect,
                    use_alphamu=use_alphamu,
                    use_dd_alphamu_llm=use_dd_alphamu_llm,
                    enable_llm_review=enable_llm_review,
                    dd_samples=dd_samples,
                    dd_alphamu_switch_cards=dd_switch_cards,
                    dd_scoring_mode=dd_scoring_mode)
                elapsed_ms = int((time.time() - t0) * 1000)

                if result.get("card"):
                    card = Card(suit=result["card"]["suit"], rank=result["card"]["rank"])
                    current_player = service.get_current_player()
                    reason = result.get("reasoning", "")
                    success, message = service.play_card(current_player, card, is_ai=True, reason=reason)
                    # 记录DD提示到trick（后台异步计算，不阻塞响应）
                    state_after = service.get_state()
                    _submit_dd_hint(state_snapshot, state_after, tricks_before)
                    state_dict = service.get_state_dict()

                    return PlayAIResponse(
                        success=success,
                        card=result["card"],
                        reasoning=result.get("reasoning"),
                        follow_up=result.get("follow_up"),
                        full_output=result.get("full_output"),
                        prompt=result.get("prompt"),
                        used_model=actual_model,
                        used_engine=engine,
                        elapsed_ms=elapsed_ms,
                        state=state_dict,
                    )
                else:
                    engine = request.play_engine or DEFAULT_PLAY_ENGINE
                    return PlayAIResponse(
                        success=False,
                        used_model=actual_model,
                        used_engine=engine,
                        elapsed_ms=elapsed_ms,
                        error=result.get("error", "AI无法选择出牌")
                    )
            else:
                return PlayAIResponse(
                    success=False,
                    used_model=actual_model,
                    error="当前是人类玩家回合"
                )
        finally:
            # 恢复会话原客户端（拷贝/豆包分支统一恢复，避免污染后续请求）
            if original_play_client is not None:
                service.llm_client = original_play_client
    except Exception as e:
        print(f"[ERROR] AI出牌失败: {str(e)}")
        traceback.print_exc()
        return PlayAIResponse(
            success=False,
            error=f"AI出牌失败: {str(e)}"
            )


class UpdatePlayerRolesRequest(BaseModel):
    player_roles: Dict[str, str]
    session_id: str = "default"


class UpdatePlayerRolesResponse(BaseModel):
    success: bool
    state: Optional[dict] = None
    is_human_turn: bool = False
    error: Optional[str] = None


@app.post("/api/play/update-roles", response_model=UpdatePlayerRolesResponse)
async def update_player_roles(request: UpdatePlayerRolesRequest):
    """更新打牌阶段的玩家角色"""
    try:
        service = get_play_service(request.session_id)
        success = service.update_player_roles(request.player_roles)
        
        if not success:
            return UpdatePlayerRolesResponse(
                success=False,
                error="打牌未初始化"
            )
        
        return UpdatePlayerRolesResponse(
            success=True,
            state=service.get_state_dict(),
            is_human_turn=service.is_human_turn()
        )
    except Exception as e:
        print(f"[ERROR] 更新玩家角色失败: {str(e)}")
        return UpdatePlayerRolesResponse(
            success=False,
            error=f"更新失败: {str(e)}"
        )


class PlayStateResponse(BaseModel):
    success: bool
    state: Optional[dict] = None
    current_player: Optional[str] = None
    is_human_turn: bool = False
    playable_cards: Optional[List[dict]] = None
    error: Optional[str] = None


@app.get("/api/play/state", response_model=PlayStateResponse)
async def get_play_state(session_id: str = Query("default")):
    """获取当前打牌状态"""
    try:
        service = get_play_service(session_id)
        state = service.get_state()
        
        if not state:
            return PlayStateResponse(
                success=False,
                error="打牌未初始化"
            )
        
        playable = service.get_playable_cards()
        state_dict = service.get_state_dict()
        
        return PlayStateResponse(
            success=True,
            state=state_dict,
            current_player=state.current_player,
            is_human_turn=service.is_human_turn(),
            playable_cards=[c.to_dict() for c in playable]
        )
    except Exception as e:
        print(f"[ERROR] 获取打牌状态失败: {str(e)}")
        return PlayStateResponse(
            success=False,
            error=f"获取状态失败: {str(e)}"
        )


def _hands_are_complete(state) -> bool:
    """校验剩余手牌与已出牌是否构成完整一副牌（52张无重复）。

    实战模拟时若人类位置未下发手牌（或编辑手牌后前后端未同步），
    手牌不完整，此时不应计算DD提示，避免给出误导性结果。
    """
    try:
        seen = set()
        total = 0
        for pos in ["北", "东", "南", "西"]:
            for card in state.hands.get(pos) or []:
                key = (card.suit, card.rank)
                if key in seen:
                    return False
                seen.add(key)
                total += 1
        for trick in state.tricks:
            for pos, card in trick.cards:
                key = (card.suit, card.rank)
                if key in seen:
                    return False
                seen.add(key)
                total += 1
        cur = getattr(state, "current_trick", None)
        if cur is not None:
            for pos, card in cur.cards:
                key = (card.suit, card.rank)
                if key in seen:
                    return False
                seen.add(key)
                total += 1
        return total == 52
    except Exception:
        return False


def _compute_dd_hints_from_state(state, playable) -> dict:
    """共享 DD 提示计算：给定状态与可出牌列表，返回每张牌的 delta。

    Args:
        state: PlayState（含 contract/hands/declarer_tricks 等）
        playable: 当前玩家可出牌列表

    Returns:
        hints dict like {"♠A": "+2", "♣K": "=", "♥5": "-1"}
        如果无法计算（DDS不可用、手牌不完整等），返回空dict
    """
    from bridge.mcts.dd_search import ENDPLAY_AVAILABLE
    if not ENDPLAY_AVAILABLE:
        return {}

    try:
        from bridge.mcts.dd_search import solve_all_boards_raw, _dds_result_to_score_map
        from bridge.mcts.state_utils import get_current_trick_state

        # 手牌不完整（实战模拟无可出牌者手牌等）则不计算提示
        if not _hands_are_complete(state):
            return {}

        declarer = state.contract.declarer
        dummy = state.dummy
        trump = state.contract.suit

        trick_state = get_current_trick_state(state)
        trick_cards = trick_state["cards"]
        trick_leader = trick_state.get("leader")

        total_played = state.declarer_tricks + state.defender_tricks
        remaining_tricks = 13 - total_played

        hands = {}
        for pos in ["北", "东", "南", "西"]:
            hands[pos] = list(state.hands.get(pos) or [])

        first_p = trick_leader if trick_cards else state.current_player
        solved_list = solve_all_boards_raw([(hands, trump, first_p, trick_cards)])
        score_map = _dds_result_to_score_map(solved_list[0]) if (solved_list and solved_list[0]) else {}

        _DD_POS = {'北': 0, '东': 1, '南': 2, '西': 3}
        cur_p = (_DD_POS.get(first_p, 0) + len(trick_cards)) % 4
        curplayer_is_declarer = cur_p in (_DD_POS.get(declarer, 2), _DD_POS.get(dummy, 0))

        contract_level = state.contract.level
        target_tricks = contract_level + 6
        hints = {}

        for card in playable:
            key = (card.suit, card.rank)
            target_tricks_for_card = score_map.get(key, 0)
            if curplayer_is_declarer:
                decl_side_tricks = target_tricks_for_card
            else:
                decl_side_tricks = remaining_tricks - target_tricks_for_card
            total = state.declarer_tricks + decl_side_tricks
            delta = total - target_tricks
            card_str = str(card)
            if delta > 0:
                hints[card_str] = f"+{delta}"
            elif delta == 0:
                hints[card_str] = "="
            else:
                hints[card_str] = str(delta)

        return hints
    except Exception as e:
        import traceback, os
        with open(os.path.join(os.path.dirname(__file__), "..", "dd_hint_error.log"), "a", encoding="utf-8") as _f:
            _f.write(f"[DD-HINT-ERROR] {e}\n")
            traceback.print_exc(file=_f)
        return {}


def _compute_dd_hints_for_state(service, state) -> dict:
    """实战模式 DD 提示：从 PlayService 取 playable，委托共享函数。"""
    playable = service.get_playable_cards()
    return _compute_dd_hints_from_state(state, playable)


def _resolve_dd_target(state_after, tricks_before):
    """确定本次出牌对应的目标 trick（请求线程同步捕获，避免竞态）。"""
    if not state_after:
        return None
    tricks_after = len(state_after.tricks)
    trick_complete = tricks_after > tricks_before
    if trick_complete and state_after.tricks:
        return state_after.tricks[-1]
    return state_after.current_trick


# ── DD 提示异步计算（7/8）──
# P1 修复：有界队列——单工作线程 + 待办只保留最新 1 个未开始的。
# 连续快速出牌时丢弃过期的提示计算，避免无界堆积（每个任务持整局深拷贝快照，堆积即内存膨胀）
_dd_hint_executor = ThreadPoolExecutor(max_workers=1)
_dd_hint_pending = []  # [(snapshot, target_trick), ...]，锁内操作，最多 1 项
_dd_hint_lock = threading.Lock()


def _submit_dd_hint(state_before_snapshot, state_after, tricks_before):
    """异步提交DD提示计算。

    在请求线程内同步捕获目标trick引用（避免后台运行时状态已前进导致定位错墩），
    并传入出牌前状态深拷贝快照，供后台线程安全读取。
    """
    try:
        if not state_before_snapshot or not state_after:
            return
        target_trick = _resolve_dd_target(state_after, tricks_before)
        if target_trick is None:
            return
        with _dd_hint_lock:
            _dd_hint_pending.append((state_before_snapshot, target_trick))
            # 只保留最新一个未开始的待办，丢弃旧的
            if len(_dd_hint_pending) > 1:
                _dd_hint_pending[:] = _dd_hint_pending[-1:]
        _dd_hint_executor.submit(_dd_hint_worker)
    except Exception:
        pass


def _dd_hint_worker():
    """后台工作线程：取最新待办计算 DD 提示。"""
    while True:
        with _dd_hint_lock:
            if not _dd_hint_pending:
                return
            snapshot, target = _dd_hint_pending.pop(0)
        _record_dd_hint_async(snapshot, target)


def _record_dd_hint_async(state_before_snapshot, target_trick):
    """后台线程：基于出牌前状态快照计算DD提示，追加到目标trick。"""
    if not state_before_snapshot or target_trick is None:
        return
    try:
        perspective = state_before_snapshot.current_player
        playable = state_before_snapshot.get_playable_cards(perspective)
        # P1 修复：DD 提示计算加硬超时（10s），避免坏局面挂起占用唯一工作线程
        with ThreadPoolExecutor(max_workers=1) as _compute_exec:
            _fut = _compute_exec.submit(_compute_dd_hints_from_state, state_before_snapshot, playable)
            hints = _fut.result(timeout=10.0)
        if not hints:
            return
        target_trick.dd_hints.append(hints)
    except TimeoutError:
        print("[DD提示] 计算超时（>10s），丢弃本次提示")
    except Exception:
        pass


@app.get("/api/play/dd-hints")
async def get_dd_hints(session_id: str = Query("default")):
    """获取当前人类玩家可选牌的完美DD结果提示（基于剩余手牌）"""
    try:
        service = get_play_service(session_id)
        state = service.get_state()
        if not state:
            return {"success": False, "error": "打牌未初始化"}

        # DDS 求解（秒级）卸载到线程，避免阻塞事件循环（P0-1 修复）
        hints = await asyncio.to_thread(_compute_dd_hints_for_state, service, state)
        return {"success": True, "hints": hints}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


class ReviewDDHintsRequest(BaseModel):
    play_state: dict
    cursor: int  # 复盘游标：0-based，表示当前查看第几张牌（已出牌的序号）


@app.post("/api/play/dd-hints-review")
async def get_dd_hints_review(request: ReviewDDHintsRequest):
    """复盘模式：根据游标位置重建牌局状态并计算DD提示。

    前端传入完整的 playState（已完成或进行中）和 cursor，
    后端重建该游标位置时的牌局状态（手牌、当前墩、当前出牌者），
    计算 DD 提示。不修改全局 play_service 状态。
    """
    from bridge.play_types import Card, Contract, PlayState, PlayPhase, Trick, POSITION_ORDER, PARTNERS

    try:
        ps = request.play_state
        cursor = request.cursor

        if not ps or not ps.get("contract"):
            return {"success": False, "error": "playState 无效"}

        # 1. 重建 Contract
        c_dict = ps["contract"]
        contract = Contract(
            level=c_dict["level"],
            suit=c_dict["suit"],
            declarer=c_dict["declarer"],
            doubled=c_dict.get("doubled", False),
            redoubled=c_dict.get("redoubled", False),
        )

        # 2. 收集所有已出牌（按出牌顺序）
        all_played = []
        for trick in ps.get("tricks", []):
            for pos, card in trick.get("cards", []):
                all_played.append((pos, Card(suit=card["suit"], rank=card["rank"])))
        for pos, card in ps.get("current_trick", {}).get("cards", []):
            all_played.append((pos, Card(suit=card["suit"], rank=card["rank"])))

        # 3. 游标语义：cursor = N 表示前 N 张牌已出，第 N 张牌（all_played[N]）回到手牌，轮到该位置出牌
        #    已出牌 = all_played[:N]，未出牌（含游标位置的加亮牌）= all_played[N:]
        played_before_cursor = all_played[:cursor]

        # 4. 重建四家完整手牌（从 playState.hands）
        full_hands = {}
        for pos in POSITION_ORDER:
            hand_list = ps.get("hands", {}).get(pos, [])
            full_hands[pos] = [Card(suit=c["suit"], rank=c["rank"]) for c in hand_list]

        # 5. 从完整手牌中移除游标之前已出的牌，得到游标位置时的手牌
        #    游标位置及之后的牌（包括 all_played[cursor]）保留在手牌中（未出）
        hands_at_cursor = {pos: list(cards) for pos, cards in full_hands.items()}
        for pos, card in played_before_cursor:
            if pos in hands_at_cursor:
                hands_at_cursor[pos] = [
                    c for c in hands_at_cursor[pos]
                    if not (c.suit == card.suit and c.rank == card.rank)
                ]

        # 6. 重建已完成墩和当前墩
        #    前 cursor 张牌分布在若干完整墩 + 一个可能未满的当前墩
        tricks_completed = []
        current_trick_cards = []
        card_count = 0
        for trick in ps.get("tricks", []):
            trick_cards = trick.get("cards", [])
            if card_count + len(trick_cards) <= cursor:
                # 整个墩都在游标之前，已完成
                t = Trick(trump=contract.suit)
                for pos, card in trick_cards:
                    t.add_card(pos, Card(suit=card["suit"], rank=card["rank"]))
                tricks_completed.append(t)
                card_count += len(trick_cards)
            else:
                # 这个墩部分在游标之前
                for pos, card in trick_cards:
                    if card_count < cursor:
                        current_trick_cards.append((pos, Card(suit=card["suit"], rank=card["rank"])))
                        card_count += 1
                    else:
                        break
                break
        # 处理 current_trick（最后一个未完成墩）
        if card_count < cursor:
            for pos, card in ps.get("current_trick", {}).get("cards", []):
                if card_count < cursor:
                    current_trick_cards.append((pos, Card(suit=card["suit"], rank=card["rank"])))
                    card_count += 1
                else:
                    break

        # 如果当前墩满4张，移入已完成
        if len(current_trick_cards) == 4:
            t = Trick(trump=contract.suit)
            for p, c in current_trick_cards:
                t.add_card(p, c)
            tricks_completed.append(t)
            current_trick_cards = []

        # 7. 确定当前出牌者 = all_played[cursor].pos（游标位置的牌的出牌者）
        if cursor < len(all_played):
            current_player = all_played[cursor][0]
        else:
            # 全部已出，无当前出牌者
            current_player = None

        if current_player is None:
            return {"success": True, "hints": {}}

        # 8. 构建 PlayState
        state = PlayState(
            contract=contract,
            hands=hands_at_cursor,
            player_roles=ps.get("player_roles", {}),
        )
        state.tricks = tricks_completed
        state.current_trick = Trick(trump=contract.suit)
        for p, c in current_trick_cards:
            state.current_trick.add_card(p, c)
        state.current_player = current_player
        state.dummy = PARTNERS.get(contract.declarer)
        # 计算墩数
        state.declarer_tricks = sum(
            1 for t in tricks_completed if t.winner() in (contract.declarer, state.dummy)
        )
        state.defender_tricks = len(tricks_completed) - state.declarer_tricks
        state.phase = PlayPhase.PLAYING

        # 9. 计算 DD 提示（DDS 求解卸载到线程，避免阻塞事件循环，P0-1 修复）
        hints = await asyncio.to_thread(_compute_dd_hints_for_state_from_state, state)
        return {"success": True, "hints": hints}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def _compute_dd_hints_for_state_from_state(state) -> dict:
    """复盘模式 DD 提示：从 PlayState 取 playable，委托共享函数。"""
    perspective = state.current_player
    if not perspective:
        return {}
    playable = state.get_playable_cards(perspective)
    return _compute_dd_hints_from_state(state, playable)


# ── 样本数 / world数设置（原"粒子数"，Phase 0a 后改为直接控制引擎参数）──
class ParticleSettingsRequest(BaseModel):
    dd_particles: Optional[int] = None       # DD 样本数
    mcts_particles: Optional[int] = None     # MCTS 迭代数
    alpha_mu_particles: Optional[int] = None # αμ world数
    session_id: str = "default"


@app.get("/api/play/particle-settings")
async def get_particle_settings(session_id: str = Query("default")):
    """获取当前采样/W数设置"""
    service = get_play_service(session_id)
    dd_val = service.dd_search.num_samples
    mcts_val = service.mcts.iterations
    amu_val = service.alpha_mu_search.num_worlds if service.alpha_mu_search else ALPHA_MU_NUM_WORLDS
    return {
        "dd_particles": dd_val,
        "dd_min": DD_PARTICLES_MIN,
        "dd_max": DD_PARTICLES_MAX,
        "mcts_particles": mcts_val,
        "mcts_min": MCTS_PARTICLES_MIN,
        "mcts_max": MCTS_PARTICLES_MAX,
        "alpha_mu_particles": amu_val,
        "alpha_mu_min": ALPHA_MU_WORLDS_MIN,
        "alpha_mu_max": ALPHA_MU_WORLDS_MAX,
    }


@app.post("/api/play/particle-settings")
async def set_particle_settings(request: ParticleSettingsRequest):
    """设置 DD样本数 / αμ world数（实时生效）"""
    service = get_play_service(request.session_id)
    updates = {}
    if request.dd_particles is not None:
        val = max(DD_PARTICLES_MIN, min(DD_PARTICLES_MAX, request.dd_particles))
        service.dd_search.num_samples = val
        updates["dd_particles"] = val
    if request.mcts_particles is not None:
        val = max(MCTS_PARTICLES_MIN, min(MCTS_PARTICLES_MAX, request.mcts_particles))
        service.mcts.iterations = val
        updates["mcts_particles"] = val
    if request.alpha_mu_particles is not None:
        val = max(ALPHA_MU_WORLDS_MIN, min(ALPHA_MU_WORLDS_MAX, request.alpha_mu_particles))
        if service.alpha_mu_search is not None:
            service.alpha_mu_search.num_worlds = val
        updates["alpha_mu_particles"] = val
    return {"success": True, "updates": updates}


# ── 记录自动备份 ──

RECORDS_BACKUP_FILE = Path(__file__).parent.parent / "bridge_records_backup.json"
RECORDS_BACKUP_MAX = 200  # 服务器端保留最多 200 条


class RecordsBackupRequest(BaseModel):
    records: List[dict]


@app.get("/api/records/backup")
async def get_records_backup():
    """获取服务器端备份的记录（前端 localStorage 丢失时恢复用）"""
    try:
        if RECORDS_BACKUP_FILE.exists():
            with open(RECORDS_BACKUP_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"success": True, "records": data}
        return {"success": True, "records": []}
    except Exception as e:
        return {"success": False, "error": str(e), "records": []}


@app.post("/api/records/backup")
async def save_records_backup(request: RecordsBackupRequest):
    """保存记录到服务器端备份文件"""
    try:
        records = request.records
        # 去重：基于 id
        seen = set()
        unique = []
        for r in records:
            rid = r.get("id", "")
            if rid and rid not in seen:
                seen.add(rid)
                unique.append(r)
        unique = unique[:RECORDS_BACKUP_MAX]

        with open(RECORDS_BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(unique, f, ensure_ascii=False, indent=2)
        return {"success": True, "count": len(unique)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"备份失败: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
