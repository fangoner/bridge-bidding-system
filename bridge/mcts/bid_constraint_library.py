"""标准自然叫牌体系（JF实战）硬编码约束库。

基于《JF实战_标准自然 - Rev 3.2.docx》约定，将常见叫品直接映射为BidConstraint，
避免LLM提取约束的不稳定性和延迟。

优先级：硬编码精确约束 > LLM提取补充约束

支持两种叫牌体系：
- "natural": 标准自然叫牌法（通用，用于无历史的随机发牌）
- "jf": JF实战约定（标准自然的变种，用于有叫牌历史的牌局）

两种体系基础开叫/争叫/应叫点力范围基本一致，主要差异在约定叫部分。
"""
from typing import Dict, List, Optional, Tuple
import re

from bridge.mcts.constraints import BidConstraint

# 叫牌体系常量
SYSTEM_NATURAL = "natural"
SYSTEM_JF = "jf"

# 体系参数配置（不同体系的阈值差异）
SYSTEM_CONFIGS = {
    SYSTEM_NATURAL: {
        "opening_min_hcp": 12,          # 开叫最低点力
        "response_min_hcp": 6,          # 一盖一应叫最低点力
        "overcall_1_min_hcp": 8,        # 1阶争叫最低点力
        "overcall_2_min_hcp": 10,       # 2阶争叫最低点力
        "response_to_1nt_min_hcp": 8,   # 1NT后应叫起点（Stayman/转移）
        "first_seat_pass_max": 11,      # 第一家Pass上限
        "response_pass_max": 5,         # 同伴花色开叫后Pass上限
        "overcall_pass_max": 7,         # 争叫位置Pass上限
        "response_1nt_pass_max": 7,     # 1NT后应叫Pass上限
        "nt_opening_min": 15,           # 1NT开叫min
        "nt_opening_max": 17,           # 1NT开叫max
        "weak_two_min": 6,              # 弱二开叫min
        "weak_two_max": 10,             # 弱二开叫max
        "strong_2c_min": 22,            # 2♣强开叫min
    },
    SYSTEM_JF: {
        "opening_min_hcp": 12,          # JF: 12点开叫
        "response_min_hcp": 5,          # JF: 5点以上必须应叫（1D-1H是5点以上）
        "overcall_1_min_hcp": 8,        # JF: 1阶争叫8点起（文档明确8-16点）
        "overcall_2_min_hcp": 10,       # JF: 2阶争叫10点起（同标准）
        "response_to_1nt_min_hcp": 8,   # JF: Stayman/转移8点起
        "first_seat_pass_max": 11,      # JF: pass<12点
        "response_pass_max": 4,         # JF: 5点以上应叫 → pass≤4
        "overcall_pass_max": 7,         # JF: 8点以上争叫 → pass≤7
        "response_1nt_pass_max": 7,     # JF: 8点以上应叫 → pass≤7
        "nt_opening_min": 15,           # JF: 1NT 15-17均型
        "nt_opening_max": 17,
        "weak_two_min": 6,              # JF: 弱二6-10
        "weak_two_max": 10,
        "strong_2c_min": 22,            # JF: 2♣强开叫22+
    },
}

# 叫品解析正则
BID_PATTERN = re.compile(r'^([♠♥♦♣NT]?)(\d)?(.*)$')
SUIT_MAP = {"S": "♠", "H": "♥", "D": "♦", "C": "♣", "NT": "NT", "N": "NT"}
LEVELS = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7}
SUITS_RANK = {"♣": 0, "♦": 1, "♥": 2, "♠": 3, "NT": 4}

# 特殊叫品标记
SPECIAL_PASS = "pass"
SPECIAL_DOUBLE = "X"
SPECIAL_REDOUBLE = "XX"


def _normalize_bid(bid_text: str) -> Optional[Tuple]:
    """将叫品文本标准化。支持：
    - 常规叫品：返回 (level:int, suit:str)
    - pass：返回 ("pass", None)
    - 加倍/技术加倍：返回 ("X", None)
    - 再加倍：返回 ("XX", None)
    """
    if not bid_text:
        return None
    bid_text = bid_text.strip().upper()
    
    # Pass/X/XX特殊处理
    if bid_text in ("PASS", "不叫", "-"):
        return (SPECIAL_PASS, None)
    if bid_text in ("X", "加倍", "DBL", "加倍！"):
        return (SPECIAL_DOUBLE, None)
    if bid_text in ("XX", "再加倍", "RDBL"):
        return (SPECIAL_REDOUBLE, None)
    
    # 提取阶数和花色
    text = bid_text
    level = None
    suit = None
    
    for lv in sorted(LEVELS.keys(), reverse=True):
        if text.startswith(lv):
            level = LEVELS[lv]
            text = text[len(lv):].strip()
            break
    
    if level is None:
        return None
    
    # 花色匹配
    for s_short, s_full in [("NT", "NT"), ("N", "NT"), ("S", "♠"), ("H", "♥"), ("D", "♦"), ("C", "♣"),
                            ("♠", "♠"), ("♥", "♥"), ("♦", "♦"), ("♣", "♣")]:
        if text.startswith(s_short):
            suit = s_full
            break
    
    if suit is None:
        return None
    
    return (level, suit)


def get_takeout_double_constraint(opening_bid: str = None) -> Optional[BidConstraint]:
    """获取技术性加倍（第二家位置，对方开叫后的直接加倍）的约束。
    
    标准自然约定：
    - 12+HCP（开叫实力以上）
    - 对未叫花色有支持，特别保证未叫高花≥4张
    - 开叫花色通常短套（≤2张）
    - 牌型非均型（如果是均型通常争叫1NT）
    
    Args:
        opening_bid: 对方的开叫叫品，用于推断未叫花色
    """
    unbid_suits = ["♠", "♥", "♦", "♣"]
    opener_suit = None
    
    if opening_bid:
        parsed = _normalize_bid(opening_bid)
        if parsed and parsed[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
            level, suit = parsed
            if suit in unbid_suits:
                opener_suit = suit
                unbid_suits.remove(suit)
    
    # 对未叫花色有支持：高花优先保证4张
    suit_min: Dict[str, int] = {}
    suit_max: Dict[str, int] = {}
    for s in unbid_suits:
        if s in ("♥", "♠"):
            suit_min[s] = 4  # 未叫高花保证4张
        else:
            suit_min[s] = 3  # 未叫低花至少3张
    
    # 开叫花色短套：≤2张
    if opener_suit:
        suit_max[opener_suit] = 2
    
    return BidConstraint(
        position="",
        min_hcp=12,
        max_hcp=21,
        balanced=False,  # 技术性加倍通常不均型，均型会争叫1NT
        suit_min=suit_min,
        suit_max=suit_max,
        min_hcp_target=14,
    )


def get_opening_bid_constraint(bid: str) -> Optional[BidConstraint]:
    """获取开叫叫品的约束。"""
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    # 特殊叫品（pass/X/XX）不是开叫
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    # ========== 1阶开叫 ==========
    if level == 1:
        if suit == "NT":
            # 1NT开叫：15-17HCP，均型（允许5张高花在某些版本，但标准自然通常高花≤4）
            return BidConstraint(
                position="",
                min_hcp=15,
                max_hcp=17,
                balanced=True,
                suit_max={"♥": 4, "♠": 4},
                min_hcp_target=16,
            )
        elif suit in ("♣", "♦"):
            # 1♣/1♦开叫：12-21HCP，所叫花色≥3张
            return BidConstraint(
                position="",
                min_hcp=12,
                max_hcp=21,
                suit_min={suit: 3},
                min_hcp_target=14,
            )
        elif suit in ("♥", "♠"):
            # 1♥/1♠开叫：12-21HCP，所叫高花≥5张
            return BidConstraint(
                position="",
                min_hcp=12,
                max_hcp=21,
                suit_min={suit: 5},
                min_hcp_target=14,
            )
    
    # ========== 2阶开叫 ==========
    elif level == 2:
        if suit == "♣":
            # 2♣强开叫：22+HCP或9赢墩，逼叫
            return BidConstraint(
                position="",
                min_hcp=22,
                min_controls=5,
                min_hcp_target=24,
            )
        elif suit == "♦":
            # 2♦：约定叫（Flannery或多功能，按JF体系：自然弱二？根据默认配置"2D/2H/2S：自然阻击"）
            # 自然弱二：6-10HCP，所叫花色=6张
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=10,
                exact_suit={"♦": 6},
                min_hcp_target=8,
            )
        elif suit in ("♥", "♠"):
            # 2♥/2♠弱二阻击：6-10HCP，所叫高花=6张
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=10,
                exact_suit={suit: 6},
                min_hcp_target=8,
            )
        elif suit == "NT":
            # 2NT开叫：20-21HCP，均型
            return BidConstraint(
                position="",
                min_hcp=20,
                max_hcp=21,
                balanced=True,
                min_hcp_target=20,
            )
    
    # ========== 3阶阻击开叫 ==========
    elif level == 3:
        # 3阶阻击：6-10HCP，所叫花色=7张
        return BidConstraint(
            position="",
            min_hcp=6,
            max_hcp=10,
            exact_suit={suit: 7},
            min_hcp_target=8,
        )
    
    # ========== 3NT赌博性开叫 ==========
    elif level == 3 and suit == "NT":
        # 赌博3NT：有一坚固低花长套，边花无A/K
        return BidConstraint(
            position="",
            min_hcp=10,
            max_hcp=15,
            suit_min={"♣": 7, "♦": 0},  # 至少一个低花长套，这里简化为约束
            min_hcp_target=12,
        )
    
    # ========== 4阶开叫 ==========
    elif level == 4:
        if suit in ("♥", "♠"):
            # 4♥/4♠开叫：阻击，8张以上套，通常<10HCP
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=12,
                suit_min={suit: 8},
                min_hcp_target=9,
            )
        else:
            # Namyats？（4♣=强4♥，4♦=强4♠）按自然阻击处理
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=12,
                suit_min={suit: 8},
                min_hcp_target=9,
            )
    
    # ========== 满贯试探/直接叫满贯 ==========
    elif level in (5, 6, 7):
        if level == 5 and suit in ("♣", "♦"):
            pass  # 5阶低花成局
        elif level == 6:
            # 小满贯：通常≥33HCP联手，开叫方单跳满贯通常≥16HCP+好套
            return BidConstraint(
                position="",
                min_hcp=16,
                min_controls=7,
                min_hcp_target=18,
            )
        elif level == 7:
            # 大满贯：≥37HCP联手
            return BidConstraint(
                position="",
                min_hcp=19,
                min_controls=9,
                min_hcp_target=21,
            )
    
    return None


def get_overcall_constraint(bid: str, is_jump: bool = False, opponent_opening: str = None) -> Optional[BidConstraint]:
    """获取争叫约束（对方开叫后的争叫）。
    
    Args:
        bid: 争叫叫品
        is_jump: 是否跳争叫
        opponent_opening: 对方的开叫叫品（用于判断是否为2阶争叫）
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    # 特殊叫品（pass/X/XX）不是花色/NT争叫
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    if is_jump:
        # 跳争叫：阻击性
        if level == 2:
            # 弱二跳争叫：6-11HCP，好6张套
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=11,
                exact_suit={suit: 6},
                min_hcp_target=8,
            )
        elif level == 3:
            # 弱三跳争叫：6-11HCP，7张套
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=11,
                exact_suit={suit: 7},
                min_hcp_target=8,
            )
    else:
        # 非跳叫的简单争叫/自然争叫
        if suit == "NT":
            if level == 1:
                # 1NT争叫：15-18HCP，均型，敌花有止
                return BidConstraint(
                    position="",
                    min_hcp=15,
                    max_hcp=18,
                    balanced=True,
                    min_hcp_target=16,
                )
            elif level == 2:
                # 2NT争叫：16-19HCP，均型，敌花有止（Unusual 2NT是特殊约定，这里先按自然NT争叫处理）
                return BidConstraint(
                    position="",
                    min_hcp=16,
                    max_hcp=19,
                    balanced=True,
                    min_hcp_target=17,
                )
        elif level == 1:
            # 1阶花色争叫：8-16HCP，所叫花色≥5张（好套可4张，但标准自然通常5张）
            return BidConstraint(
                position="",
                min_hcp=8,
                max_hcp=16,
                suit_min={suit: 5},
                min_hcp_target=11,
            )
        elif level == 2:
            # 2阶花色争叫：10-17HCP，所叫花色≥5张（通常好套，点力比1阶争叫高）
            return BidConstraint(
                position="",
                min_hcp=10,
                max_hcp=17,
                suit_min={suit: 5},
                min_hcp_target=13,
            )
        elif level >= 3:
            # 3阶以上争叫：阻击性或强牌，按阻击处理：8张套，6-12HCP
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=12,
                suit_min={suit: level + 4},  # 3阶争叫通常7张，4阶8张
                min_hcp_target=9,
            )
    
    return None


def get_takeout_double_response_constraint(bid: str, is_pass_before: bool = False) -> Optional[BidConstraint]:
    """获取对同伴技术性加倍的应叫约束。
    
    对技术性加倍的应叫规则（标准自然/JF基本一致）：
    - 平叫花色（0-8HCP）：弱应叫，所叫花色≥4张（高花优先4张），不逼叫
    - 1NT应叫（6-10HCP）：均型，对方花色有挡，不逼叫
    - 跳叫花色（9-11HCP）：邀请，所叫花色≥4张，邀请进局
    - 2NT/扣叫（12+HCP）：强牌，逼叫
    - 3NT/成局叫：止叫
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    if level == 1:
        if suit == "NT":
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=10,
                balanced=True,
                inference_source="convention_takeout_double",
            )
        else:
            return BidConstraint(
                position="",
                min_hcp=0,
                max_hcp=8,
                suit_min={suit: 4},
                min_hcp_target=5,
                inference_source="convention_takeout_double",
            )
    elif level == 2:
        if suit == "NT":
            return BidConstraint(
                position="",
                min_hcp=11,
                max_hcp=12,
                balanced=True,
                inference_source="convention_takeout_double",
            )
        else:
            return BidConstraint(
                position="",
                min_hcp=0,
                max_hcp=8,
                suit_min={suit: 4},
                min_hcp_target=5,
                inference_source="convention_takeout_double",
            )
    elif level == 3:
        if suit == "NT":
            return BidConstraint(
                position="",
                min_hcp=13,
                max_hcp=16,
                balanced=True,
                inference_source="convention_takeout_double",
            )
        else:
            return BidConstraint(
                position="",
                min_hcp=9,
                max_hcp=11,
                suit_min={suit: 4},
                min_hcp_target=10,
                inference_source="convention_takeout_double",
            )
    
    return None


def get_jacoby_transfer_constraint(bid: str, opener_nt_level: int = 1) -> Optional[BidConstraint]:
    """获取雅各比转移叫(Jacoby Transfer)的应叫人约束。
    
    在1NT开叫后：
    - 2♦ 转移到 2♥：应叫人持有5+♥，任意点力（0+HCP）
    - 2♥ 转移到 2♠：应叫人持有5+♠，任意点力（0+HCP）
    - 完成转移叫后再叫新花/NT/跳叫才显示点力，这里只约束转移叫本身
    
    转移叫本身不承诺点力，只承诺花色长度≥5张
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    if opener_nt_level == 1 and level == 2:
        if suit == "♦":
            return BidConstraint(
                position="",
                min_hcp=0,
                max_hcp=None,
                suit_min={"♥": 5},
                inference_source="convention_jacoby_transfer",
            )
        elif suit == "♥":
            return BidConstraint(
                position="",
                min_hcp=0,
                max_hcp=None,
                suit_min={"♠": 5},
                inference_source="convention_jacoby_transfer",
            )
    
    return None


def get_stayman_constraint(bid: str, opener_nt_level: int = 1) -> Optional[BidConstraint]:
    """获取斯台曼(Stayman)问叫的应叫人约束。
    
    在1NT开叫后：
    - 2♣ 斯台曼问叫：应叫人持有8+HCP（不叫过头可能更低），至少一个4张高花，无5张高花（有5张高花用转移叫）
    
    JF体系用傀儡斯台曼，但2♣问叫的基础约束相同：至少一个4张高花，8+HCP
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    if opener_nt_level == 1 and level == 2 and suit == "♣":
        return BidConstraint(
            position="",
            min_hcp=8,
            max_hcp=None,
            # 斯台曼保证至少一门高花4张，但不确定是哪一门，用min(♠≥4 OR ♥≥4)，这里不设死suit_min
            # 但可以放宽：suit_min 不设，因为可能是4-4高花或者单4张高花
            inference_source="convention_stayman",
        )
    
    return None


def get_landy_overcall_constraint(bid: str, opponent_nt_level: int = 1) -> Optional[BidConstraint]:
    """获取兰迪(Landy)约定叫对抗1NT开叫的争叫约束。
    
    兰迪约定是对抗1NT开叫最常用的自然约定：
    - X: 惩罚性加倍（15+HCP，均型，对方套有挡张）
    - 2♣: 双高花套（♥+♠ 至少4-4，通常5-4，10-16HCP）
    - 2♦/♥/♠: 自然争叫，所叫套≥5张，8-16HCP
    - 2NT: 不寻常无将，双低花（♣+♦ 至少5-5，10-15HCP）
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    if opponent_nt_level == 1 and level == 2:
        if suit == "♣":
            # 2♣: 兰迪约定，双高套，♥和♠至少4张（通常5-4）
            return BidConstraint(
                position="",
                min_hcp=10,
                max_hcp=16,
                suit_min={"♥": 4, "♠": 4},
                balanced=False,
                inference_source="convention_landy",
            )
        elif suit in ("♦", "♥", "♠"):
            # 二阶自然争叫：所叫套≥5张
            return BidConstraint(
                position="",
                min_hcp=8,
                max_hcp=16,
                suit_min={suit: 5},
                balanced=False,
                inference_source="overcall_2level",
            )
        elif suit == "NT":
            # 2NT: 不寻常无将，双低花 ♣+♦ ≥5-5
            return BidConstraint(
                position="",
                min_hcp=10,
                max_hcp=15,
                suit_min={"♣": 5, "♦": 5},
                balanced=False,
                inference_source="unusual_nt",
            )
    
    return None


def get_puppet_stayman_constraint(bid: str, nt_level: int = 2) -> Optional[BidConstraint]:
    """获取傀儡斯台曼(Puppet Stayman)的约束。
    
    傀儡斯台曼用于：
    - 2NT开叫后的3♣问叫（0+HCP，问高花）
    - 1NT开叫后跳叫3♣（10+HCP，逼局实力，问高花）
    
    答叫：
    - 3♦: 无4张高花
    - 3♥: 4张♠
    - 3♠: 4张♥
    - 3NT: 双高套4-4
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    # 傀儡斯台曼是3♣叫品
    if level == 3 and suit == "♣":
        min_hcp = 10 if nt_level == 1 else 0
        return BidConstraint(
            position="",
            min_hcp=min_hcp,
            max_hcp=40,
            # 至少有一门4张高花（OR关系，权重中处理），这里给3张软约束
            suit_min={"♥": 3, "♠": 3},
            inference_source="convention_puppet_stayman",
        )
    
    return None


def get_blackwood_constraint(bid: str, is_asker: bool = True) -> Optional[BidConstraint]:
    """获取黑木/罗马关键张问叫(RKCB)的约束。
    
    4NT问叫：问A/关键张数量。
    - 问叫人：至少开叫实力，确定将牌配合，有满贯兴趣
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    if is_asker and level == 4 and suit == "NT":
        return BidConstraint(
            position="",
            min_hcp=12,
            max_hcp=40,
            inference_source="convention_blackwood",
        )
    
    return None


def get_nt_rebid_constraint(bid: str, partner_transfer_suit: str = None, is_opener: bool = True) -> Optional[BidConstraint]:
    """获取1NT开叫方在同伴雅各比转移叫后的再叫约束。
    
    开叫人在转移叫后的再叫：
    - 平叫接受转移（2♥/2♠）：低限或高限（15-17），通常2张支持，超转移3张好支持+高限
    - 跳叫接受转移（3♥/3♠）：高限17HCP，4张支持，超级接受
    - 直接叫4♥/4♠：选择最终定约，接受进局，15-17，通常2+张支持
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    if not partner_transfer_suit:
        return None
    
    # 开叫人接受转移叫
    if suit == partner_transfer_suit:
        if level == 2:
            # 平叫接受：15-17HCP，2+张支持
            return BidConstraint(
                position="",
                min_hcp=15,
                max_hcp=17,
                suit_min={suit: 2},
                inference_source="convention_transfer_accept",
            )
        elif level == 3:
            # 跳叫接受：高限17HCP，4张支持
            return BidConstraint(
                position="",
                min_hcp=17,
                max_hcp=17,
                suit_min={suit: 4},
                inference_source="convention_transfer_super_accept",
            )
        elif level == 4:
            # 直接进局：15-17HCP，2+张支持（认为有成局实力）
            return BidConstraint(
                position="",
                min_hcp=15,
                max_hcp=17,
                suit_min={suit: 2},
                min_hcp_target=16,
                inference_source="convention_transfer_to_game",
            )
    
    return None


def get_transfer_responder_rebid_constraint(bid: str, transfer_suit: str) -> Optional[BidConstraint]:
    """获取雅各比转移叫后应叫人的再叫约束。
    
    应叫人在开叫人接受转移后的再叫：
    - pass: 弱牌，0-7HCP，5+转移套，满足于部分定约
    - 2NT: 邀请进局，8-9HCP，5张套，均型或半均型
    - 3♣/3♦/3新花: 逼叫，显示第二套，寻求满贯/3NT
    - 3M/跳叫原花: 邀请进局，8-9HCP，6+张套
    - 3NT: 进局选择，10-15HCP，5张套，均型，可能有其他止
    - 4M: 进局止叫，10-17HCP（含牌型），6+张套，满足于4M
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    if suit == transfer_suit:
        if level == 3:
            # 3M邀请：8-9HCP，6+张套
            return BidConstraint(
                position="",
                min_hcp=8,
                max_hcp=9,
                suit_min={suit: 6},
                inference_source="convention_transfer_rebid_invite",
            )
        elif level == 4:
            # 4M进局：0+HCP（含牌型），5+张套，满足于4M定约
            # 可以是弱牌关煞（6+张，0-9HCP）或强牌但无满贯兴趣（10-16HCP）
            return BidConstraint(
                position="",
                min_hcp=0,
                max_hcp=16,
                suit_min={suit: 5},
                min_hcp_target=10,
                inference_source="convention_transfer_rebid_game",
            )
    elif suit == "NT":
        if level == 2:
            # 2NT邀请：8-9HCP
            return BidConstraint(
                position="",
                min_hcp=8,
                max_hcp=9,
                balanced=True,
                suit_min={transfer_suit: 5},
                min_hcp_target=8,
                inference_source="convention_transfer_rebid_2nt",
            )
        elif level == 3:
            # 3NT：10-15HCP，成局选择
            return BidConstraint(
                position="",
                min_hcp=10,
                max_hcp=15,
                balanced=True,
                suit_min={transfer_suit: 5},
                min_hcp_target=12,
                inference_source="convention_transfer_rebid_3nt",
            )
    else:
        # 新花：逼叫，10+HCP，第二套≥4张
        if level >= 2:
            return BidConstraint(
                position="",
                min_hcp=10,
                suit_min={suit: 4, transfer_suit: 5},
                min_hcp_target=12,
                inference_source="convention_transfer_rebid_new_suit",
            )
    
    return None


def get_response_constraint(bid: str, opener_suit: str = None, is_pass_before: bool = False) -> Optional[BidConstraint]:
    """获取应叫约束。
    
    Args:
        bid: 应叫叫品
        opener_suit: 开叫花色（用于加叫判断）
        is_pass_before: 应叫人之前pass过（不叫过头）
    """
    parsed = _normalize_bid(bid)
    if not parsed:
        return None
    # 特殊叫品（pass/X/XX）不在这里处理
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    level, suit = parsed
    
    # 不叫过头的牌：<12HCP
    pass_hcp_cap = 11 if is_pass_before else None
    
    if level == 1:
        if suit == "NT":
            # 1NT应叫：6-10HCP（标准自然，不逼叫），均型，未pass时6-10，pass后可能6-9
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=10 if not is_pass_before else 9,
                balanced=True,
                min_hcp_target=8,
            )
        elif opener_suit and suit != opener_suit and SUITS_RANK[suit] > SUITS_RANK[opener_suit]:
            # 一盖一应叫新花：6+HCP，所叫花色≥4张，逼叫一轮
            c = BidConstraint(
                position="",
                min_hcp=6,
                suit_min={suit: 4},
                min_hcp_target=10,
            )
            if pass_hcp_cap:
                c.max_hcp = pass_hcp_cap
            return c
    elif level == 2:
        if opener_suit and suit == opener_suit:
            # 简单加叫开叫花色：6-9点（含牌型点），支持≥3张
            return BidConstraint(
                position="",
                min_hcp=6,
                max_hcp=9 if not is_pass_before else 10,
                suit_min={suit: 3},
                min_hcp_target=7,
            )
        elif suit == "NT":
            # 2NT应叫：12-15HCP（Jacoby 2NT不同体系，这里按标准自然进局逼叫邀请）
            c = BidConstraint(
                position="",
                min_hcp=11,
                max_hcp=15,
                balanced=True,
                min_hcp_target=13,
            )
            return c
        elif opener_suit and SUITS_RANK[suit] < SUITS_RANK[opener_suit]:
            # 二盖一应叫新花：12+HCP，通常≥5张套（低花开叫应叫高花可能4张），逼叫进局
            c = BidConstraint(
                position="",
                min_hcp=12,
                suit_min={suit: 5 if suit in ("♣", "♦") else 4},
                min_hcp_target=14,
            )
            if pass_hcp_cap:
                c.max_hcp = pass_hcp_cap
            return c
        else:
            # 二盖一高花（1♠-2♥）：12+HCP，♥≥5张
            c = BidConstraint(
                position="",
                min_hcp=12,
                suit_min={suit: 5},
                min_hcp_target=14,
            )
            return c
    elif level == 3:
        if opener_suit and suit == opener_suit:
            # 跳加叫开叫花色：阻击性/限制性，10-12点，4张支持
            return BidConstraint(
                position="",
                min_hcp=10,
                max_hcp=12,
                suit_min={suit: 4},
                min_hcp_target=11,
            )
    
    return None


def get_rebid_constraint(
    bid: str,
    first_bid_by_player: str,
    partner_suit: Optional[str] = None,
    is_jump: bool = False,
    is_reverse: bool = False,
) -> Optional[BidConstraint]:
    """获取同一位置第二次叫牌（再叫）的约束。

    自然叫牌体系标准再叫规则：

    开叫人再叫：
    - 平叫原花：12-15HCP，原花色≥6张
    - 跳叫原花：16-18HCP，原花色≥6张，进局邀请
    - 顺叫新花：12-18HCP，新花≥4张
    - 逆叫新花：16+HCP，非均型，原花≥5，新花≥4
    - 平加叫同伴花色：12-14HCP，同伴花色≥3张支持
    - 跳加叫同伴花色：16-18HCP，同伴花色≥4张支持，邀请
    - 平叫NT（1NT/2NT）：12-15HCP（1阶后1NT是6-10不对，开叫人再叫1NT是12-14；2NT是18-19）
    - 跳叫NT：18-19HCP，均型

    应叫人再叫：
    - 平叫原花：6-9HCP，6张套，示弱
    - 跳叫原花：10-12HCP，6张套，邀请
    """
    parsed = _normalize_bid(bid)
    first_parsed = _normalize_bid(first_bid_by_player)
    if not parsed or not first_parsed:
        return None
    if parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None
    if first_parsed[0] in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
        return None

    level, suit = parsed
    first_level, first_suit = first_parsed

    # ========== 开叫人再叫 ==========
    if is_reverse:
        # 逆叫新花：16+HCP，非均型，第一套≥5张，新套≥4张
        return BidConstraint(
            position="",
            min_hcp=16,
            balanced=False,
            suit_min={first_suit: 5, suit: 4},
            min_hcp_target=18,
        )

    if suit == first_suit:
        # 再叫原花色
        if is_jump:
            # 跳叫原花：16-18HCP，原花≥6张，邀请进局
            return BidConstraint(
                position="",
                min_hcp=16,
                max_hcp=18,
                suit_min={suit: 6},
                min_hcp_target=17,
            )
        else:
            # 平叫原花：12-15HCP，原花≥6张（低限再叫）
            return BidConstraint(
                position="",
                min_hcp=12,
                max_hcp=15,
                suit_min={suit: 6},
                min_hcp_target=13,
            )

    if partner_suit and suit == partner_suit:
        # 加叫同伴花色
        if is_jump:
            # 跳加叫：16-18HCP，将牌≥4张支持，邀请
            return BidConstraint(
                position="",
                min_hcp=16,
                max_hcp=18,
                suit_min={suit: 4},
                min_hcp_target=17,
            )
        else:
            # 平加叫：12-14HCP，将牌≥3张支持
            return BidConstraint(
                position="",
                min_hcp=12,
                max_hcp=15,
                suit_min={suit: 3},
                min_hcp_target=13,
            )

    if suit == "NT":
        if is_jump or level >= 3:
            # 跳叫NT：18-19HCP，均型（2NT通常是18-19）
            return BidConstraint(
                position="",
                min_hcp=18,
                max_hcp=19,
                balanced=True,
                min_hcp_target=18,
            )
        else:
            # 平叫NT：12-15HCP，均型
            return BidConstraint(
                position="",
                min_hcp=12,
                max_hcp=15,
                balanced=True,
                min_hcp_target=13,
            )

    # 新花再叫（非逆叫、非加叫、非NT、非原花）：顺叫新花，12-18HCP，新花≥4张
    if not is_jump:
        return BidConstraint(
            position="",
            min_hcp=12,
            max_hcp=18,
            suit_min={suit: 4},
            min_hcp_target=15,
        )

    return None


def _is_reverse(level: int, suit: str, first_level: int, first_suit: str) -> bool:
    """判断是否是逆叫：在二阶叫出比开叫花色级别高的新花，显示16+HCP。
    
    逆叫条件：
    1. 叫品在二阶及以上
    2. 所叫新花级别高于开叫花色
    3. 开叫在一阶（开叫1♣后叫2♠是逆叫；开叫1♠后没有逆叫新花，因为所有花色都比♠低）
    """
    if first_level != 1:
        return False
    if level < 2:
        return False
    if suit == "NT" or first_suit == "NT":
        return False
    return SUITS_RANK[suit] > SUITS_RANK[first_suit]


def extract_constraints_from_bid_history(bid_history: str, system: str = SYSTEM_NATURAL) -> Dict[str, BidConstraint]:
    """从叫牌历史文本中提取硬编码约束。
    
    Args:
        bid_history: 格式如 "(南)1♣：12+HCP，♣≥3 -(西)X：技术性加倍 -(北)2♣：低花加叫-..."
        system: 叫牌体系，"natural"（标准自然）或"jf"（JF实战约定）。
                - 有叫牌历史（实际牌局）使用 SYSTEM_JF
                - 无叫牌历史（随机发牌采样）使用 SYSTEM_NATURAL
    
    Returns:
        {position: BidConstraint} 约束映射
    """
    # 空叫牌历史直接返回空约束
    if not bid_history or not bid_history.strip():
        return {}
    
    # 获取体系配置
    if system not in SYSTEM_CONFIGS:
        system = SYSTEM_NATURAL
    cfg = SYSTEM_CONFIGS[system]
    
    constraints: Dict[str, BidConstraint] = {}
    
    # 解析每轮叫牌
    # 匹配 (位置)叫品：描述 - 格式
    pos_map = {"南": "南", "西": "西", "北": "北", "东": "东",
               "S": "南", "W": "西", "N": "北", "E": "东"}
    
    # 先提取所有叫品序列（保留所有叫品，包括pass，保持正确叫牌顺序）
    bid_sequence: List[Tuple[str, str]] = []
    pattern = re.compile(r'\(([南西北东SWNE])\)\s*([^-：:]+)')
    for match in pattern.finditer(bid_history):
        pos_str, bid_str = match.groups()
        pos = pos_map.get(pos_str.upper() if len(pos_str) == 1 else pos_str)
        if pos:
            bid_str = bid_str.strip()
            if bid_str:
                # 保留所有叫品，包括pass/X/XX，保证叫牌顺序正确
                parsed = _normalize_bid(bid_str)
                if parsed:
                    bid_sequence.append((pos, bid_str))
    
    if not bid_sequence:
        return constraints
    
    opener_pos = bid_sequence[0][0]
    opening_bid = bid_sequence[0][1]  # 记录开叫叫品
    
    # 叫牌序列状态跟踪（用于约定叫识别）
    opening_parsed = _normalize_bid(opening_bid)
    is_1nt_opening = False
    nt_opener_pos = None
    if opening_parsed and opening_parsed[0] == 1 and opening_parsed[1] == "NT":
        is_1nt_opening = True
        nt_opener_pos = opener_pos
    
    # 跟踪雅各比转移叫状态：记录谁转移到了什么花色
    # {responder_pos: transfer_suit}
    pending_transfer: Dict[str, str] = {}
    # 跟踪已完成的转移叫：{opener_pos: (acceptor_pos, transfer_suit)}
    completed_transfers: List[Tuple[str, str, str]] = []  # (opener_pos, responder_pos, suit)
    
    # 记录每位置的叫品历史
    pos_bids: Dict[str, List[str]] = {}
    passed_before: Dict[str, bool] = {}
    for pos, _ in bid_sequence:
        pos_bids.setdefault(pos, [])
    
    # 判断是否第二家加倍（开叫人下家直接加倍，即第二个叫品是X）
    is_second_seat_double = False
    if len(bid_sequence) >= 2:
        second_bid_parsed = _normalize_bid(bid_sequence[1][1])
        if second_bid_parsed and second_bid_parsed[0] == SPECIAL_DOUBLE:
            is_second_seat_double = True
    
    for idx, (pos, bid_str) in enumerate(bid_sequence):
        # 判断之前是否pass过（该位置自己之前pass过）
        has_passed = False
        for pb in pos_bids.get(pos, []):
            pb_p = _normalize_bid(pb)
            if pb_p and pb_p[0] == SPECIAL_PASS:
                has_passed = True
                break
        passed_before[pos] = has_passed
        
        # 解析当前叫品
        parsed = _normalize_bid(bid_str)
        if not parsed:
            # 解析失败，不处理
            pos_bids[pos].append(bid_str)
            continue
        
        # pass 叫品：记录但不生成约束
        if parsed[0] == SPECIAL_PASS:
            pos_bids[pos].append(bid_str)
            continue
        
        # 尝试识别叫品类型
        constraint = None
        
        # ========== 预先计算：判断是否是再叫（该位置之前已有实质性叫品） ==========
        has_substantive_before = False
        first_substantive_bid = None
        for pb in pos_bids[pos]:
            pb_p = _normalize_bid(pb)
            if pb_p and pb_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                has_substantive_before = True
                if first_substantive_bid is None:
                    first_substantive_bid = pb
        is_rebid = has_substantive_before
        
        # ========== 优先检查跨序列约定叫（需要状态跟踪的） ==========
        # 1. 1NT开叫方接受同伴雅各比转移叫（属于开叫人再叫）
        if pos == nt_opener_pos and pos in pending_transfer:
            transfer_suit = pending_transfer[pos]
            nt_rebid_c = get_nt_rebid_constraint(bid_str, transfer_suit, is_opener=True)
            if nt_rebid_c:
                constraint = nt_rebid_c
                # 转移叫已被接受，记录到completed_transfers
                responder_partner = {"南": "北", "北": "南", "东": "西", "西": "东"}[pos]
                completed_transfers.append((pos, responder_partner, transfer_suit))
                del pending_transfer[pos]
        
        # 2. 应叫人在转移叫被接受后的再叫
        if constraint is None:
            for (opener, responder, tsuit) in completed_transfers:
                if pos == responder and is_rebid:
                    resp_rebid_c = get_transfer_responder_rebid_constraint(bid_str, tsuit)
                    if resp_rebid_c:
                        constraint = resp_rebid_c
                        break
        
        # 3. 全局约定叫检查：傀儡斯台曼（任意位置在NT开叫后叫3♣）
        if constraint is None:
            nt_level = 0
            for prev_idx in range(idx-1, -1, -1):
                prev_pos, prev_bid = bid_sequence[prev_idx]
                prev_p = _normalize_bid(prev_bid)
                if prev_p and prev_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                    pl, ps = prev_p
                    if ps == "NT" and pl in (1, 2):
                        nt_level = pl
                        break
            if nt_level > 0:
                puppet_c = get_puppet_stayman_constraint(bid_str, nt_level=nt_level)
                if puppet_c:
                    constraint = puppet_c
        
        # 4. 全局约定叫检查：黑木/罗马关键张问叫（任意位置叫4NT）
        if constraint is None:
            bw_c = get_blackwood_constraint(bid_str, is_asker=True)
            if bw_c:
                constraint = bw_c
        
        # 常规叫品处理
        if constraint is None:
            if idx == 0:
                # 开叫
                constraint = get_opening_bid_constraint(bid_str)
            elif parsed[0] == SPECIAL_DOUBLE:
                # 加倍：第二家位置是技术性加倍
                if idx == 1:
                    # 第二家直接加倍：技术性加倍
                    constraint = get_takeout_double_constraint(opening_bid)
                # 其他位置加倍（应叫性加倍/惩罚性加倍）暂不处理
            elif parsed[0] == SPECIAL_REDOUBLE:
                # 再加倍暂不处理
                pass
            else:
                level, suit = parsed
                partner = {"南": "北", "北": "南", "东": "西", "西": "东"}[pos]

                if is_rebid:
                    first_bid_by_player = first_substantive_bid  # 该位置第一次实质性叫品
                    first_parsed_p = _normalize_bid(first_bid_by_player)

                    # 找同伴的最后一个花色叫品（用于加叫判断）
                    partner_suit = None
                    for pb in reversed(pos_bids.get(partner, [])):
                        pb_p = _normalize_bid(pb)
                        if pb_p and pb_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE) and pb_p[1] != "NT":
                            partner_suit = pb_p[1]
                            break

                    # 判断是否跳叫：找上一个我方的实质性叫品，对比阶数
                    is_jump_rebid = False
                    prev_own_parsed = None
                    for pb in reversed(pos_bids[pos]):
                        pb_p = _normalize_bid(pb)
                        if pb_p and pb_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                            prev_own_parsed = pb_p
                            break
                    if prev_own_parsed:
                        prev_level, prev_suit_own = prev_own_parsed
                        if suit == prev_suit_own and level > prev_level + 1:
                            is_jump_rebid = True
                        elif partner_suit and suit == partner_suit:
                            # 加叫同伴：如果跳一阶以上算跳叫
                            if level > 2:  # 平加叫通常到2阶（1M-2M是平加）
                                is_jump_rebid = True
                        elif suit == "NT":
                            # NT跳叫
                            if level >= 3:
                                is_jump_rebid = True
                        else:
                            # 新花跳叫
                            # 简化判断：如果比同伴叫品高两阶以上算跳叫
                            if partner_suit and first_parsed_p and first_parsed_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                                natural_new_level = first_parsed_p[0]
                                if SUITS_RANK[suit] > SUITS_RANK[first_parsed_p[1]]:
                                    natural_new_level = first_parsed_p[0]
                                else:
                                    natural_new_level = first_parsed_p[0] + 1
                                if level > natural_new_level + 1:
                                    is_jump_rebid = True

                    # 判断是否逆叫
                    is_reverse_bid = False
                    if first_parsed_p and first_parsed_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                        is_reverse_bid = _is_reverse(level, suit, first_parsed_p[0], first_parsed_p[1])

                    constraint = get_rebid_constraint(
                        bid_str,
                        first_bid_by_player,
                        partner_suit,
                        is_jump_rebid,
                        is_reverse_bid,
                    )
                else:
                    # 第一次叫牌：争叫或应叫
                    our_side_opened = False
                    if idx >= 2:
                        # 检查是否是同伴开叫后的应叫（同伴已经在序列中叫过牌）
                        prev_positions = [p for p, _ in bid_sequence[:idx]]
                        if partner in prev_positions:
                            our_side_opened = True

                    if our_side_opened:
                        # 应叫：找同伴的第一个叫品和第一个实质性花色叫品
                        partner_bid = pos_bids.get(partner, [None])[0]
                        
                        # 找同伴的第一个花色/NT实质性叫品
                        partner_substantive_bid = None
                        partner_has_takeout_double = False
                        partner_first_substantive_parsed = None
                        for pb in pos_bids.get(partner, []):
                            pb_p = _normalize_bid(pb)
                            if pb_p and pb_p[0] == SPECIAL_DOUBLE:
                                partner_has_takeout_double = True
                            if pb_p and pb_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                                if partner_substantive_bid is None:
                                    partner_substantive_bid = pb
                                    partner_first_substantive_parsed = pb_p
                                break
                        
                        opener_parsed = partner_first_substantive_parsed
                        opener_suit = opener_parsed[1] if opener_parsed and opener_parsed[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE) else None
                        
                        # ========== 约定叫检测优先 ==========
                        if constraint is None:
                            # 1. 对同伴技术性加倍的应叫（同伴叫过加倍，且还没有叫过其他实质性花色/NT）
                            if partner_has_takeout_double and partner_substantive_bid is None:
                                constraint = get_takeout_double_response_constraint(bid_str, has_passed)
                            # 2. 斯台曼问叫：同伴开叫1NT，应叫2♣
                            elif partner_first_substantive_parsed and partner_first_substantive_parsed[0] == 1 and partner_first_substantive_parsed[1] == "NT":
                                stayman_c = get_stayman_constraint(bid_str, opener_nt_level=1)
                                if stayman_c:
                                    constraint = stayman_c
                                else:
                                    # 3. 雅各比转移叫：同伴开叫1NT，应叫2♦/2♥
                                    jt_constraint = get_jacoby_transfer_constraint(bid_str, opener_nt_level=1)
                                    if jt_constraint:
                                        constraint = jt_constraint
                                        # 记录pending转移：等待开叫人接受
                                        jt_parsed = _normalize_bid(bid_str)
                                        if jt_parsed:
                                            _, jt_suit = jt_parsed
                                            if jt_suit == "♦":
                                                target_suit = "♥"
                                            elif jt_suit == "♥":
                                                target_suit = "♠"
                                            else:
                                                target_suit = None
                                            if target_suit:
                                                pending_transfer[partner] = target_suit
                                    else:
                                        # 普通自然应叫
                                        constraint = get_response_constraint(bid_str, opener_suit, has_passed)
                            else:
                                constraint = get_response_constraint(bid_str, opener_suit, has_passed)
                    else:
                        # 争叫：判断是否是对抗1NT开叫的兰迪约定叫
                        is_landy_overcall = False
                        if is_1nt_opening and idx >= 1:
                            # 第二家/第四家位置争叫对抗1NT：使用兰迪约定
                            landy_c = get_landy_overcall_constraint(bid_str, opponent_nt_level=1)
                            if landy_c:
                                constraint = landy_c
                                is_landy_overcall = True
                        
                        if not is_landy_overcall:
                            # 普通自然争叫：判断是否跳叫
                            is_jump = False
                            if parsed[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                                # 找上一个实质性非加倍叫品
                                prev_substantive_bid = None
                                for prev_idx in range(idx-1, -1, -1):
                                    prev_p = _normalize_bid(bid_sequence[prev_idx][1])
                                    if prev_p and prev_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                                        prev_substantive_bid = prev_p
                                        break

                                first_parsed = _normalize_bid(bid_sequence[0][1])
                                if prev_substantive_bid and first_parsed and first_parsed[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                                    prev_level, prev_suit = prev_substantive_bid
                                    first_level, first_suit = first_parsed
                                    # 判断是否跳叫：比自然争叫需要的阶数高
                                    natural_min_level = first_level
                                    if SUITS_RANK[suit] <= SUITS_RANK[first_suit]:
                                        natural_min_level = first_level + 1
                                    if level > natural_min_level:
                                        is_jump = True

                                constraint = get_overcall_constraint(bid_str, is_jump, opening_bid)
        
        if constraint:
            constraint.position = pos
            # 如果该位置已有约束，取更严格的（合并约束）
            if pos in constraints:
                existing = constraints[pos]
                constraint = _merge_constraints(existing, constraint)
            constraints[pos] = constraint

        # 记录当前叫品到该位置的历史（用于再叫判断）
        pos_bids[pos].append(bid_str)
    
    # 应用动态推断：否定推断（从Pass推导上限），使用体系特定阈值
    constraints = _apply_negative_inference(constraints, bid_sequence, cfg)
    
    # 应用动态推断：点力守恒（总HCP=40，一方强则另一方受限）
    constraints = _apply_hcp_conservation(constraints)
    
    # 标记所有硬编码约束的来源体系
    for pos, c in constraints.items():
        if c.inference_source == "hard_coded":
            c.inference_source = f"hard_coded_{system}"
    
    return constraints


def _merge_constraints(c1: BidConstraint, c2: BidConstraint) -> BidConstraint:
    """合并两个约束：取更严格的限制。"""
    merged = BidConstraint(position=c1.position)
    
    # HCP范围取交集
    merged.min_hcp = max(c1.min_hcp or 0, c2.min_hcp or 0)
    if merged.min_hcp == 0:
        merged.min_hcp = None
    
    max_candidates = []
    if c1.max_hcp is not None:
        max_candidates.append(c1.max_hcp)
    if c2.max_hcp is not None:
        max_candidates.append(c2.max_hcp)
    if max_candidates:
        merged.max_hcp = min(max_candidates)
    
    # 控制数取高
    merged.min_controls = max(c1.min_controls or 0, c2.min_controls or 0)
    if merged.min_controls == 0:
        merged.min_controls = None
    
    # balanced: 如果一个说True一个说False，矛盾——保留更严格的（通常后续叫牌会更明确）
    if c1.balanced is not None and c2.balanced is not None:
        merged.balanced = c1.balanced if c1.balanced == c2.balanced else None
    else:
        merged.balanced = c1.balanced if c1.balanced is not None else c2.balanced
    
    # 花色张数：suit_min取大值，suit_max取小值
    merged.suit_min = {}
    for suit in set(list(c1.suit_min.keys()) + list(c2.suit_min.keys())):
        m1 = c1.suit_min.get(suit, 0)
        m2 = c2.suit_min.get(suit, 0)
        merged.suit_min[suit] = max(m1, m2)
    
    merged.suit_max = {}
    for suit in set(list(c1.suit_max.keys()) + list(c2.suit_max.keys())):
        m1 = c1.suit_max.get(suit, 13)
        m2 = c2.suit_max.get(suit, 13)
        merged.suit_max[suit] = min(m1, m2)
    
    # exact_suit: 如果有冲突取更严格的（长套）
    merged.exact_suit = {}
    for suit in set(list(c1.exact_suit.keys()) + list(c2.exact_suit.keys())):
        e1 = c1.exact_suit.get(suit)
        e2 = c2.exact_suit.get(suit)
        if e1 is not None and e2 is not None:
            merged.exact_suit[suit] = max(e1, e2)
        elif e1 is not None:
            merged.exact_suit[suit] = e1
        else:
            merged.exact_suit[suit] = e2
    
    # HCP目标值取平均
    targets = []
    if c1.min_hcp_target is not None:
        targets.append(c1.min_hcp_target)
    if c2.min_hcp_target is not None:
        targets.append(c2.min_hcp_target)
    if targets:
        merged.min_hcp_target = int(sum(targets) / len(targets))
    
    # specific_cards: 必须持有的特定牌张取并集（两个约束要求的牌都要有）
    merged.specific_cards = c1.specific_cards.union(c2.specific_cards)
    
    # inference_source: 优先保留约定叫/否定推断/守恒来源，普通hard_coded优先级最低
    # 来源优先级：convention_* > negative_inference > hcp_conservation > hard_coded
    source_priority = {
        "convention": 4,
        "negative_inference": 3,
        "hcp_conservation": 2,
        "hard_coded": 1,
    }
    def _source_priority(src: str) -> int:
        if not src:
            return 0
        for key, prio in source_priority.items():
            if src.startswith(key):
                return prio
        return 1
    p1 = _source_priority(c1.inference_source)
    p2 = _source_priority(c2.inference_source)
    merged.inference_source = c1.inference_source if p1 >= p2 else c2.inference_source
    
    return merged


def _apply_negative_inference(
    constraints: Dict[str, BidConstraint],
    bid_sequence: List[Tuple[str, str]],
    cfg: Dict,
) -> Dict[str, BidConstraint]:
    """应用否定推断：从Pass行为推断牌力上限。
    
    根据约定卡中的叫牌最低点力要求，反向推导：
    - 不叫说明不满足叫牌条件，牌力低于叫牌所需最低点力
    
    Args:
        constraints: 已提取的正向约束
        bid_sequence: 完整叫牌序列 [(pos, bid_str), ...]
        cfg: 体系配置参数，包含不同场景的HCP阈值
    
    Returns:
        更新后的constraints，添加否定推断的max_hcp
    """
    if not bid_sequence:
        return constraints
    
    pos_map_partner = {"南": "北", "北": "南", "东": "西", "西": "东"}
    
    # 记录每个位置是否有pass，以及pass时的上下文
    pos_passed_before: Dict[str, bool] = {}
    pos_pass_context: Dict[str, str] = {}  # 'first_seat_pass', 'response_to_suit', 'response_to_1nt', 'overcall_pass'
    
    for idx, (pos, bid_str) in enumerate(bid_sequence):
        parsed = _normalize_bid(bid_str)
        if not parsed:
            continue
        
        if parsed[0] == SPECIAL_PASS:
            already_has_substantive = False
            for pb_pos, pb_bid in bid_sequence[:idx]:
                if pb_pos == pos:
                    pb_p = _normalize_bid(pb_bid)
                    if pb_p and pb_p[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                        already_has_substantive = True
                        break
            
            if not already_has_substantive:
                pos_passed_before[pos] = True
                
                partner = pos_map_partner[pos]
                prev_substantive_pos = None
                prev_substantive_bid = None
                for prev_idx in range(idx-1, -1, -1):
                    prev_p, prev_bid_str = bid_sequence[prev_idx]
                    prev_p_parsed = _normalize_bid(prev_bid_str)
                    if prev_p_parsed and prev_p_parsed[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                        prev_substantive_pos = prev_p
                        prev_substantive_bid = prev_bid_str
                        break
                
                if idx == 0:
                    pos_pass_context[pos] = 'first_seat_pass'
                elif prev_substantive_pos is not None and prev_substantive_pos == partner:
                    prev_parsed = _normalize_bid(prev_substantive_bid)
                    if prev_parsed and prev_parsed[0] == 1 and prev_parsed[1] == 'NT':
                        pos_pass_context[pos] = 'response_to_1nt'
                    elif prev_parsed and prev_parsed[0] not in (SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE):
                        pos_pass_context[pos] = 'response_to_suit'
                elif prev_substantive_pos is not None and prev_substantive_pos != partner:
                    pos_pass_context[pos] = 'overcall_pass'
    
    for pos in pos_passed_before:
        hcp_cap = None
        context = pos_pass_context.get(pos, '')
        
        if context == 'first_seat_pass':
            hcp_cap = cfg["first_seat_pass_max"]
        elif context == 'response_to_suit':
            hcp_cap = cfg["response_pass_max"]
        elif context == 'response_to_1nt':
            hcp_cap = cfg["response_1nt_pass_max"]
        elif context == 'overcall_pass':
            hcp_cap = cfg["overcall_pass_max"]
        
        if hcp_cap is not None:
            if pos in constraints:
                existing = constraints[pos]
                if existing.max_hcp is None or hcp_cap < existing.max_hcp:
                    existing.max_hcp = hcp_cap
                    existing.inference_source = "negative_inference"
            else:
                c = BidConstraint(
                    position=pos,
                    max_hcp=hcp_cap,
                    inference_source="negative_inference",
                )
                constraints[pos] = c
    
    return constraints


def _apply_hcp_conservation(
    constraints: Dict[str, BidConstraint],
) -> Dict[str, BidConstraint]:
    """应用点力守恒约束：全桌总HCP=40，一方显示强牌则另一方受限。
    
    基本原理：
    - 南北是搭档，东西是搭档
    - 13张牌总共40HCP
    - 当一方两人都有min_hcp约束时，可计算另一方总HCP上限
    - 当一方两人都有max_hcp约束时，可计算另一方总HCP下限
    - 单个牌手的HCP不可能超过同伴双方总剩余HCP
    
    Args:
        constraints: 已提取的约束（已含正向约束和否定推断）
    
    Returns:
        更新后的constraints，应用点力守恒
    """
    if not constraints:
        return constraints
    
    # 分组：NS和EW
    ns_positions = ["南", "北"]
    ew_positions = ["东", "西"]
    
    def _get_hcp_range(pos: str) -> Tuple[int, int]:
        """获取某位置的HCP范围 (min, max)"""
        if pos not in constraints:
            return (0, 40)
        c = constraints[pos]
        mn = c.min_hcp if c.min_hcp is not None else 0
        mx = c.max_hcp if c.max_hcp is not None else 40
        return (mn, mx)
    
    # 计算双方总HCP范围
    ns_min = 0
    ns_max = 0
    for p in ns_positions:
        mn, mx = _get_hcp_range(p)
        ns_min += mn
        ns_max += mx
    
    ew_min = 0
    ew_max = 0
    for p in ew_positions:
        mn, mx = _get_hcp_range(p)
        ew_min += mn
        ew_max += mx
    
    # 点力守恒：ns_total + ew_total = 40
    # 所以：
    # ew_max_calculated = 40 - ns_min
    # ew_min_calculated = 40 - ns_max
    # ns_max_calculated = 40 - ew_min
    # ns_min_calculated = 40 - ew_max
    
    ew_max_conserved = min(ew_max, 40 - ns_min)
    ew_min_conserved = max(ew_min, 40 - ns_max)
    ns_max_conserved = min(ns_max, 40 - ew_min)
    ns_min_conserved = max(ns_min, 40 - ew_max)
    
    # 将总范围约束分配给个人（作为软约束，收紧上限即可，下限不好直接分配给个人）
    # 简单策略：如果一方总max_hcp已经收紧，则给该方没有明确max的个人设置一个合理上限
    # 更保守的做法：只对没有任何max_hcp约束的位置，设置总上限减去同伴已知min
    
    # 处理NS方
    for pos in ns_positions:
        partner = "北" if pos == "南" else "南"
        p_mn, p_mx = _get_hcp_range(pos)
        part_mn, _ = _get_hcp_range(partner)
        
        # 个人最大HCP不可能超过: 总max - 同伴最小
        personal_max_possible = ns_max_conserved - part_mn
        if personal_max_possible < 37 and (p_mx is None or personal_max_possible < p_mx):
            if pos in constraints:
                if constraints[pos].max_hcp is None or personal_max_possible < constraints[pos].max_hcp:
                    constraints[pos].max_hcp = personal_max_possible
                    old_src = constraints[pos].inference_source or ""
                    # 保留约定叫和否定推断来源标记，不覆盖
                    if not old_src.startswith("convention_") and old_src != "negative_inference":
                        constraints[pos].inference_source = "hcp_conservation"
            else:
                constraints[pos] = BidConstraint(
                    position=pos,
                    max_hcp=personal_max_possible,
                    inference_source="hcp_conservation",
                )
    
    # 处理EW方
    for pos in ew_positions:
        partner = "东" if pos == "西" else "西"
        p_mn, p_mx = _get_hcp_range(pos)
        part_mn, _ = _get_hcp_range(partner)
        
        personal_max_possible = ew_max_conserved - part_mn
        if personal_max_possible < 37 and (p_mx is None or personal_max_possible < p_mx):
            if pos in constraints:
                if constraints[pos].max_hcp is None or personal_max_possible < constraints[pos].max_hcp:
                    constraints[pos].max_hcp = personal_max_possible
                    old_src = constraints[pos].inference_source or ""
                    if not old_src.startswith("convention_") and old_src != "negative_inference":
                        constraints[pos].inference_source = "hcp_conservation"
            else:
                constraints[pos] = BidConstraint(
                    position=pos,
                    max_hcp=personal_max_possible,
                    inference_source="hcp_conservation",
                )
    
    # 安全检查：确保每个位置的min_hcp <= max_hcp，防止范围反转
    for pos in list(constraints.keys()):
        c = constraints[pos]
        if c.min_hcp is not None and c.max_hcp is not None and c.min_hcp > c.max_hcp:
            # 范围反转时，放宽max到min（假设约束提取有误，点力守恒是软约束）
            c.max_hcp = max(c.max_hcp, c.min_hcp)
    
    return constraints
