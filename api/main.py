#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
桥牌叫牌练习系统 - Web API服务
"""

import sys
import os
import re
import traceback
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bridge.dealer import BridgeDealer, Hand, Position, POSITION_ORDER, DealMode, parse_deal_input, parse_hand_string
from bridge.bidding import (
    extract_retrieval_keyword,
    get_partner_position,
    get_position_name,
    get_next_position,
)
from bridge.output_format import generate_all_outputs
from bridge.deep_finesse import analyze_with_deep_finesse, parse_df_deal, df_format_to_hand
from bridge.bidding_service import BiddingService
from knowledge.loader import JFLoader, JFRetriever
from llm.prompts import BIDDING_SYSTEM_PROMPT, BIDDING_FALLBACK_PROMPT, HUMAN_BID_PROMPT
from llm.deepseek_client import DeepSeekClient
from llm.doubao_client import DoubaoVisionClient, DoubaoSeedClient
from utils.screenshot import BridgeScreenshotCapture, trigger_screenshot_shortcut, read_clipboard_image
from config import JF_CONVENTION_FILE, DEFAULT_DEAL_SYSTEM, AI_PROVIDER_DEEPSEEK, AI_PROVIDER_DOUBAO, DEFAULT_AI_PROVIDER

try:
    from endplay_integration import analyze_all_contracts_endplay
    ENDPLAY_AVAILABLE = True
except ImportError:
    ENDPLAY_AVAILABLE = False
    print("警告: endplay_integration 模块不可用，双明手分析功能不可用")

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
screenshot_capture = BridgeScreenshotCapture()

current_ai_provider = DEFAULT_AI_PROVIDER

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
        result = bidding_service.human_bid(
            user_input=request.user_input,
            position=request.position,
            bidding_sequence=bidding_str,
            deal_system=request.deal_system,
            verbose=True
        )
        
        # 人类叫牌时，直接使用用户输入的叫品，而不是LLM返回的"选定叫品"
        # 避免LLM解析错误导致显示的叫品与实际不符
        bid = request.user_input.strip()
        if bid.upper() == "P":
            bid = "pass"
        meaning = result.get("叫品含义", "")
        
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
    """获取当前模型配置"""
    return {
        "fallback_model": llm_client.model,
        "available_models": ["deepseek-v4-flash", "deepseek-v4-pro"]
    }


@app.post("/api/fallback-model", response_model=FallbackModelResponse)
async def set_fallback_model(request: FallbackModelRequest):
    """设置模型"""
    valid_models = ["deepseek-v4-flash", "deepseek-v4-pro"]
    if request.fallback_model not in valid_models:
        raise HTTPException(
            status_code=400,
            detail=f"无效的模型名称。有效选项: {', '.join(valid_models)}"
        )
    
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
            {"id": AI_PROVIDER_DEEPSEEK, "name": "DeepSeek", "models": ["deepseek-v4-flash", "deepseek-v4-pro"]},
            {"id": AI_PROVIDER_DOUBAO, "name": "Doubao (豆包)", "models": ["Doubao-Seed-2.0-lite"]}
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
        
        current_llm_client = get_llm_client(request.ai_provider)
        
        original_model = None
        if request.fallback_model and request.ai_provider != AI_PROVIDER_DOUBAO:
            original_model = current_llm_client.model
            current_llm_client.model = request.fallback_model
        
        bidding_service = BiddingService(current_llm_client, jf_retriever)
        bidding_service.use_fallback = request.use_fallback
        bidding_service.set_bid_meanings(request.bid_history if request.bid_history else "")
        
        result = bidding_service.ai_bid(
            hand=hand,
            position=request.position,
            bidding_sequence=bidding_str,
            deal_system=request.deal_system,
            verbose=True
        )
        
        bid = result.get("选定叫品") or "pass"
        meaning = result.get("叫品含义") or result.get("叫品含义及后续建议") or ""
        selection_process = result.get("叫品筛选过程") or ""
        
        if original_model:
            current_llm_client.model = original_model
        
        return BidResponse(
            bid=bid,
            meaning=meaning,
            selection_process=selection_process,
            use_fallback=bidding_service.use_fallback,
            full_output=result
        )
    except Exception as e:
        print(f"[ERROR] 叫牌失败: {str(e)}")
        if original_model:
            current_llm_client.model = original_model
        return BidResponse(
            bid="pass",
            meaning=f"叫牌失败: {str(e)}",
            selection_process="出错",
            full_output=None
        )


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
        
        # 生成输出格式
        _, compact, deep_finesse = generate_all_outputs(
            hands=hands,
            bidding_str=bidding_str,
            dealer=dealer_pos,
            mode=request.game_mode,
            human_position=human_pos
        )
        
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
        
        result = analyze_with_deep_finesse(
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


def convert_10_to_T(hand_str: str) -> str:
    result = re.sub(r'([♠♥♦♣])10', r'\1T', hand_str)
    result = re.sub(r'([♠♥♦♣SsHhDdCc])10', r'\1T', result)
    result = result.replace('10', 'T')
    return result


def _format_bidding_sequence(bidding):
    """将AI识别返回的叫牌序列格式化为标准字符串"""
    if not bidding or bidding == "null":
        return None
    if isinstance(bidding, list):
        formatted_bids = []
        for item in bidding:
            if ":" in item:
                pos, bid = item.split(":", 1)
                formatted_bids.append(f"({pos}){bid}")
            else:
                formatted_bids.append(item)
        return "-".join(formatted_bids) + "-"
    return bidding


def _parse_vision_hands(result):
    """从视觉识别结果中解析手牌，返回 (hands_dict, validation_errors)"""
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
            hand_str_clean = convert_10_to_T(hand_str)
            hand_str_clean = hand_str_clean.replace("♠", " ").replace("♥", " ").replace("♦", " ").replace("♣", " ")
            hands[pos] = parse_hand_string(hand_str_clean)
    
    validation_errors = []
    for pos, hand in hands.items():
        total_cards = len(hand.spades) + len(hand.hearts) + len(hand.diamonds) + len(hand.clubs)
        if total_cards != 13:
            validation_errors.append(f"{get_position_name(pos)}手牌有{total_cards}张，不是13张")
    
    return hands, validation_errors


def _hands_to_response_dict(hands):
    """将 hands dict (Position -> Hand) 转为 API 响应格式"""
    return {get_position_name(pos): hand_to_dict(hand) for pos, hand in hands.items()}





@app.post("/api/custom-deal", response_model=CustomDealResponse)
async def custom_deal(request: CustomDealRequest):
    """自定义牌局接口"""
    try:
        lines = [l.strip() for l in request.input_text.strip().split("\n") if l.strip()]
        
        if any(line.strip().startswith("Deal:") for line in lines):
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
                return CustomDealResponse(
                    hands=hands_dict,
                    dealer="南",
                    success=True,
                    message="牌局已加载（Deep Finesse格式）"
                )
            else:
                return CustomDealResponse(
                    hands={},
                    dealer="南",
                    success=False,
                    message=f"牌局解析不完整，缺少 {4 - len(hands)} 家手牌"
                )
        elif len(lines) == 4:
            input_text = convert_10_to_T(request.input_text)
            hands = parse_deal_input(input_text)
            if hands:
                hands_dict = _hands_to_response_dict(hands)
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
                message=f"需要输入4行标准格式或Deep Finesse格式，当前输入了{len(lines)}行"
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
    page_type: Optional[str] = None


@app.post("/api/image-deal", response_model=ImageDealResponse)
async def image_deal(image: bytes = File(..., description="图片文件")):
    """从图片读取牌局接口"""
    try:
        
        print(f"[INFO] 收到图片上传请求，大小: {len(image)} bytes")
        
        # 保存上传的文件到临时目录
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
            tmp.write(image)
            image_path = tmp.name
        
        print(f"[INFO] 图片已保存到临时文件: {image_path}")
        
        try:
            print(f"[INFO] 开始调用vision_client识别图片...")
            result = vision_client.read_cards_from_image(image_path)
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
        
        if len(hands) == 4 and not validation_errors:
            hands_dict = _hands_to_response_dict(hands)
            bidding_str = _format_bidding_sequence(result.get("叫牌序列"))
            
            return ImageDealResponse(
                hands=hands_dict,
                dealer="南",
                success=True,
                message="牌局已加载",
                bidding_sequence=bidding_str,
                contract=result.get("当前定约"),
                page_type=result.get("页面类型", "未知")
            )
        else:
            if validation_errors:
                error_msg = "; ".join(validation_errors)
                print(f"[WARN] 手牌验证失败: {error_msg}")
                return ImageDealResponse(
                    hands={},
                    dealer="南",
                    success=False,
                    message=f"手牌验证失败: {error_msg}"
                )
            else:
                return ImageDealResponse(
                    hands={},
                    dealer="南",
                    success=False,
                    message=f"部分手牌识别成功，共{len(hands)}家"
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


class ScreenshotDealResponse(BaseModel):
    hands: Dict[str, dict]
    dealer: str
    success: bool
    message: Optional[str] = None
    screenshot_path: Optional[str] = None
    bidding_sequence: Optional[str] = None
    contract: Optional[str] = None
    page_type: Optional[str] = None


@app.post("/api/screenshot-deal", response_model=ScreenshotDealResponse)
async def screenshot_deal():
    """从Edge浏览器截屏读取牌局接口"""
    try:
        result = screenshot_capture.capture_and_analyze("edge")
        
        if "error" in result:
            return ScreenshotDealResponse(
                hands={},
                dealer="南",
                success=False,
                message=result['error'],
                screenshot_path=result.get("screenshot_path")
            )
        
        # 截屏识别使用不同的 key 格式（南家手牌 vs 南），需要转换
        hands = {}
        screenshot_position_map = {
            "南": Position.SOUTH,
            "西": Position.WEST,
            "北": Position.NORTH,
            "东": Position.EAST
        }
        
        for pos_name, en_pos in screenshot_position_map.items():
            hand_str = result.get(f"{pos_name}家手牌")
            if hand_str and hand_str != "null":
                hand_str_clean = convert_10_to_T(hand_str)
                hand_str_clean = hand_str_clean.replace("♠", " ").replace("♥", " ").replace("♦", " ").replace("♣", " ")
                hands[en_pos] = parse_hand_string(hand_str_clean)
        
        if len(hands) == 4:
            hands_dict = _hands_to_response_dict(hands)
            bidding_str = _format_bidding_sequence(result.get("叫牌序列"))
            
            return ScreenshotDealResponse(
                hands=hands_dict,
                dealer="南",
                success=True,
                message="牌局已加载",
                screenshot_path=result.get("screenshot_path"),
                bidding_sequence=bidding_str,
                contract=result.get("当前定约"),
                page_type=result.get("页面类型", "未知")
            )
        else:
            return ScreenshotDealResponse(
                hands={},
                dealer="南",
                success=False,
                message=f"部分手牌识别成功，共{len(hands)}家",
                screenshot_path=result.get("screenshot_path")
            )
    except Exception as e:
        print(f"[ERROR] 截屏识别失败: {str(e)}")
        traceback.print_exc()
        return ScreenshotDealResponse(
                hands={},
                dealer="南",
                success=False,
                message=f"截屏识别失败: {str(e)}"
            )


class TriggerScreenshotResponse(BaseModel):
    success: bool
    message: str
    screenshot_path: Optional[str] = None


@app.post("/api/trigger-screenshot")
async def trigger_screenshot():
    """触发系统截屏快捷键"""
    success = trigger_screenshot_shortcut()
    if success:
        return {"success": True, "message": "截屏已触发，请在截屏工具中选择区域后点击识别"}
    else:
        return {"success": False, "message": "触发截屏失败"}


@app.post("/api/read-clipboard")
async def read_clipboard():
    """从剪贴板读取截图"""
    try:
        result = read_clipboard_image()
        if result is None:
            return {"success": False, "message": "剪贴板中没有图片，请先截屏"}
        
        image_data, fmt = result
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{fmt}') as tmp:
            tmp.write(image_data)
            image_path = tmp.name
        
        print(f"[INFO] 截图已保存到: {image_path}")

        result = vision_client.read_cards_from_image(image_path)
        print(f"[DEBUG] vision_client返回结果: {result}")
        
        os.unlink(image_path)
        
        if "error" in result:
            return {
                "success": False,
                "message": f"识别失败: {result['error']}"
            }
        
        hands, validation_errors = _parse_vision_hands(result)
        
        if len(hands) == 4 and not validation_errors:
            hands_dict = _hands_to_response_dict(hands)
            bidding_str = _format_bidding_sequence(result.get("叫牌序列"))
            
            return {
                "success": True,
                "message": "牌局已加载",
                "hands": hands_dict,
                "dealer": "南",
                "bidding_sequence": bidding_str,
                "contract": result.get("当前定约"),
                "page_type": result.get("页面类型", "未知")
            }
        else:
            if validation_errors:
                error_msg = "; ".join(validation_errors)
                return {
                    "success": False,
                    "message": f"手牌验证失败: {error_msg}"
                }
            else:
                return {
                    "success": False,
                    "message": f"部分手牌识别成功，共{len(hands)}家"
                }
                
    except Exception as e:
        print(f"[ERROR] 读取剪贴板失败: {str(e)}")
        traceback.print_exc()
        return {
            "success": False,
            "message": f"读取剪贴板失败: {str(e)}"
        }


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
            error="双明手分析功能不可用，请确保已安装 endplay 库"
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
        
        result = analyze_all_contracts_endplay(hands_dict)
        
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

# 全局打牌服务实例
play_service = None


def get_play_service():
    global play_service
    if play_service is None:
        current_llm_client = get_llm_client()
        play_service = PlayService(current_llm_client)
    return play_service


class PlayInitRequest(BaseModel):
    hands: Dict[str, dict]
    contract: str
    declarer: str
    player_roles: Optional[Dict[str, str]] = None
    doubled: bool = False
    redoubled: bool = False
    bidding_sequence: Optional[str] = None


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
        service = get_play_service()
        state = service.initialize(
            hands=request.hands,
            contract_str=request.contract,
            declarer=request.declarer,
            player_roles=request.player_roles,
            doubled=request.doubled,
            redoubled=request.redoubled,
            bidding_sequence=request.bidding_sequence or "未提供"
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
        service = get_play_service()
        
        state_before = service.get_state()
        tricks_before = len(state_before.tricks) if state_before else 0
        
        card = Card(suit=request.card["suit"], rank=request.card["rank"])
        success, message = service.play_card(request.position, card)
        
        state = service.get_state()
        trick_winner = None
        trick_complete = False
        
        # 检查是否刚完成一墩（墩数增加了）
        tricks_after = len(state.tricks) if state else 0
        if tricks_after > tricks_before and state:
            trick_winner = state.current_player  # 新一墩的首攻者就是上一墩的赢家
            trick_complete = True
        
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
            message=message
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
async def undo_play():
    """撤销最近一次出牌"""
    try:
        service = get_play_service()
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
    use_reasoning: bool = True
    play_model: Optional[str] = None


class PlayAIResponse(BaseModel):
    success: bool
    card: Optional[dict] = None
    reasoning: Optional[str] = None
    follow_up: Optional[str] = None
    full_output: Optional[dict] = None
    prompt: Optional[str] = None
    used_model: Optional[str] = None
    error: Optional[str] = None


@app.post("/api/play/ai-play", response_model=PlayAIResponse)
async def ai_play(request: PlayAIRequest):
    """AI出牌"""
    try:
        service = get_play_service()
        
        # 临时切换打牌模型（不影响叫牌模型）
        original_model = None
        actual_model = llm_client.model
        if request.play_model and request.play_model in ["deepseek-v4-flash", "deepseek-v4-pro"]:
            original_model = llm_client.model
            llm_client.model = request.play_model
            actual_model = request.play_model
        
        try:
            if not service.is_human_turn():
                result = await service.get_ai_play(use_reasoning=request.use_reasoning)
                
                if result.get("card"):
                    card = Card(suit=result["card"]["suit"], rank=result["card"]["rank"])
                    current_player = service.get_current_player()
                    reason = result.get("reasoning", "")
                    success, message = service.play_card(current_player, card, is_ai=True, reason=reason)
                    
                    return PlayAIResponse(
                        success=success,
                        card=result["card"],
                        reasoning=result.get("reasoning"),
                        follow_up=result.get("follow_up"),
                        full_output=result.get("full_output"),
                        prompt=result.get("prompt"),
                        used_model=actual_model,
                    )
                else:
                    return PlayAIResponse(
                        success=False,
                        used_model=actual_model,
                        error=result.get("error", "AI无法选择出牌")
                    )
            else:
                return PlayAIResponse(
                    success=False,
                    used_model=actual_model,
                    error="当前是人类玩家回合"
                )
        finally:
            # 恢复原始模型
            if original_model:
                llm_client.model = original_model
    except Exception as e:
        print(f"[ERROR] AI出牌失败: {str(e)}")
        traceback.print_exc()
        return PlayAIResponse(
            success=False,
            error=f"AI出牌失败: {str(e)}"
        )


class UpdatePlayerRolesRequest(BaseModel):
    player_roles: Dict[str, str]


class UpdatePlayerRolesResponse(BaseModel):
    success: bool
    state: Optional[dict] = None
    is_human_turn: bool = False
    error: Optional[str] = None


@app.post("/api/play/update-roles", response_model=UpdatePlayerRolesResponse)
async def update_player_roles(request: UpdatePlayerRolesRequest):
    """更新打牌阶段的玩家角色"""
    try:
        service = get_play_service()
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
async def get_play_state():
    """获取当前打牌状态"""
    try:
        service = get_play_service()
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
