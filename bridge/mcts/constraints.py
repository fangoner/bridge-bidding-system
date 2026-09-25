"""叫牌约束：从叫牌含义中提取的点力/牌型限制，用于采样过滤。

约束不按来源分级：进入样本验证的所有约束都视为叫牌明确承诺（LLM 转换
或前端确认的家约束）。inference_source 仅作来源标记/诊断保留，不参与过滤
（v1.79：删除旧分级——规则库退役后硬/忽略分类失去区分对象，structured
产生的白名单外来源导致约束系统性失效，见 CHANGELOG v1.79）。
"""
from dataclasses import dataclass, field, copy as dc_copy
from typing import Dict, List, Optional, Set, Tuple

from bridge.play_types import Card, POSITION_ORDER

CONTROL_MAP = {"A": 2, "K": 1}  # A=2控制，K=1控制


def relax_constraint(c: "BidConstraint") -> "BidConstraint":
    """生成放宽版约束：HCP ±2，suit_min 减半。"""
    relaxed = BidConstraint(position=c.position, inference_source="relaxed")
    if c.min_hcp is not None:
        relaxed.min_hcp = max(0, c.min_hcp - 2)
    if c.max_hcp is not None:
        relaxed.max_hcp = min(37, c.max_hcp + 2)
    if c.min_controls is not None:
        relaxed.min_controls = max(0, c.min_controls - 1)
    if c.min_keycards is not None:
        relaxed.min_keycards = max(0, c.min_keycards - 1)
    relaxed.suit_min = {s: max(1, n // 2) for s, n in c.suit_min.items()}
    # suit_max / exact_suit / specific_cards / suit_controls / balanced / length_above 放宽时不保留
    return relaxed


_RANK_ORDER = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
_BIG_RANKS = {"A", "K", "Q", "J", "T"}  # 大牌 = 10 及以上（H 定义含 10）


def _rank_value_of(rank: str) -> int:
    try:
        return _RANK_ORDER.index(rank)
    except ValueError:
        return -1


# ── 首攻顶张连张：新睿表12-1 形态白名单（v2.15）──
# 每个模式串转成 (大牌集合, 小牌最小张数, 小牌最大张数)：
#   A/K/Q/J/10 → 大牌集合成员；x → 一张小牌占位；+ → 可追加任意小牌；
#   无 + 时小牌数 = x 数（精确）；有 + 时小牌数 ≥ x 数（上不封顶）。
# 攻 A 行：AKQJ+, AKQ+, AKx, AK, Ax+, A
# 攻 K 行：KQJ+, KQ+, Kx, K
# 攻 Q 行：QJ+, AQJ+, Qx, Q
# 攻 J 行：J10+, AJ10+, KJ10+, Jx, J
# 攻10 行：109+, A109+, K109+, Q109+, 10x, 10
_LEAD_SHAPE_NT = {
    "A": ["AKQJ+", "AKQ+", "AKx", "AK", "Ax+", "A"],
    "K": ["KQJ+", "KQ+", "Kx", "K"],
    "Q": ["QJ+", "AQJ+", "Qx", "Q"],
    "J": ["J10+", "AJ10+", "KJ10+", "Jx", "J"],
    "T": ["109+", "A109+", "K109+", "Q109+", "10x", "10"],
}
# 有将顶张（表12-3）：与 NT 不同——A 行含 AKx+ 无 AK；K 行含 AK（AK 双张攻 K）
# 无 KQJ+；Q 行为 QJ10+/QJx+；J 行无 AJ10+；10 行无 A109+
_LEAD_SHAPE_TRUMP = {
    "A": ["AKQJ+", "AKQ+", "AKx+", "Ax+", "A"],
    "K": ["KQ+", "AK", "Kx", "K"],
    "Q": ["QJ10+", "QJx+", "Qx", "Q"],
    "J": ["J10+", "KJ10+", "Jx", "J"],
    "T": ["109+", "K109+", "Q109+", "10x", "10"],
}


def parse_lead_shape_patterns(pattern_list: List[str]):
    """把新睿表12-1 形态模式串转为 (大牌集合, 小牌min, 小牌max) 列表。"""
    result = []
    for p in pattern_list:
        bigs = set()
        x_count = 0
        has_plus = p.endswith("+")
        body = p[:-1] if has_plus else p
        i = 0
        while i < len(body):
            ch = body[i]
            if ch == "1" and i + 1 < len(body) and body[i + 1] == "0":
                bigs.add("T")
                i += 2
                continue
            if ch in _BIG_RANKS:
                bigs.add(ch)
            elif ch == "x" or ch == "9":
                x_count += 1
            i += 1
        if has_plus:
            result.append((bigs, x_count, 99))
        else:
            result.append((bigs, x_count, x_count))
    return result


def filter_lead_shape_long(entries) -> list:
    """顶张大牌首攻的"长套限定"白名单：仅保留花色 ≥4 张的形态。

    助攻信号分流用（v2.15）：无将大牌首攻时，若队友未叫过该花色，首攻
    大牌来自首攻人自己的长套（花色 ≥4 张）——把形态的小牌下限抬到
    4 - 大牌数，使总张数 ≥4；无法达到的形态（短套如 Kx/K）剔除。
    条目格式同 parse_lead_shape_patterns：(大牌集, 小牌min, 小牌max)。
    """
    result = []
    for bigs, smin, smax in entries:
        need = max(0, 4 - len(bigs))
        new_smin = max(smin, need)
        if new_smin <= smax:
            result.append((bigs, new_smin, smax))
    return result


def match_suit_shape(cards: List[Card], lead_shape: tuple) -> bool:
    """检查花色形态是否命中白名单（完整口径或剩余口径自洽）。

    cards: 该位置剩余手牌。
    lead_shape: (花色, 首攻牌面, [(bigs, small_min, small_max), ...])。
    完整口径（初始约束）：形态 bigs 含首攻牌 → 把首攻牌加回再比对（完整 =
    剩余 ∪ 首攻牌）；剩余口径（随出牌递减后的最新约束）：形态已剔首攻牌 →
    不加回，直接比对剩余牌。两个口径由"形态是否仍含首攻牌"自动区分，
    采样中局始终用递减后的剩余口径。
    """
    suit, lead_rank, pattern_entries = lead_shape[0], lead_shape[1], lead_shape[2]
    bigs = set()
    small = 0
    for c in cards:
        if c.suit != suit:
            continue
        if c.rank in _BIG_RANKS:
            bigs.add(c.rank)
        else:
            small += 1
    if any(lead_rank in eb for eb, _smin, _smax in pattern_entries):
        bigs.add(lead_rank)
    for (ent_bigs, smin, smax) in pattern_entries:
        if bigs == ent_bigs and smin <= small <= smax:
            return True
    return False


def match_suit_small_shapes(cards: List[Card], lead_small_shapes: tuple) -> bool:
    """检查首攻小牌形态白名单（含长四/三张攻最小/三张攻中间/双张）。

    cards: 该位置剩余手牌（不含首攻牌）。
    lead_small_shapes: (花色, 首攻牌面, [(total_min, total_max, above_min, above_max,
                         big_min, big_max), ...])
    完整该花色张数 = 剩余张数 + 1（含首攻牌）；>首攻牌的张数 = 剩余中
    点数高于首攻牌的张数（首攻牌本身不比自身大，不计入）；big = 其中大牌(≥10)数。
    big_min/big_max 表达"上面的牌里大牌限定"：三张攻最小要求 ≥1 大牌在上，
    三张攻中间要求唯一上面的那张是小牌（big=0）。
    """
    suit, lead_rank, entries = lead_small_shapes[0], lead_small_shapes[1], lead_small_shapes[2]
    lead_rv = _rank_value_of(lead_rank)
    total = 1  # 首攻牌
    above = 0
    above_big = 0
    for c in cards:
        if c.suit != suit:
            continue
        total += 1
        if _rank_value_of(c.rank) > lead_rv:
            above += 1
            if c.rank in _BIG_RANKS:
                above_big += 1
    for entry in entries:
        tmin, tmax, amin, amax = entry[0], entry[1], entry[2], entry[3]
        bmin = entry[4] if len(entry) > 4 else 0
        bmax = entry[5] if len(entry) > 5 else 99
        if not (tmin <= total <= tmax and amin <= above <= amax):
            continue
        if not (bmin <= above_big <= bmax):
            continue
        return True
    return False


def _build_trump_small_shapes(lead_rank: str) -> List[Tuple[int, int, int, int, int, int]]:
    """有将小牌首攻白名单（3/5 首攻，表12-3 X 行 + 表12-4）。

    有将长套：奇数张(5/7/…)攻最小（above = 总张-1）；偶数张(4/6/…)攻第3大
    （above = 2，第3张是攻牌上方有2张）。短套：
      Xx   双张攻大（above=0）
      xXx  三张小牌攻中间（above=1 且上面那张是小牌）
      HxX  三张带大牌攻最小（above=2 且含大牌）
    返回 [(total_min, total_max, above_min, above_max, big_min, big_max), ...]
    """
    entries = [
        (2, 2, 0, 0, 0, 99),       # Xx 双张攻大
        (3, 3, 1, 1, 0, 0),        # xXx 三张小牌攻中间（唯一上面的是小牌）
        (3, 3, 2, 2, 1, 99),       # HxX 三张带大牌攻最小（上面2张含大牌）
        (4, 4, 2, 2, 0, 99),       # 4张偶数：攻第3大
        (5, 5, 4, 4, 0, 99),       # 5张奇数：攻最小
        (6, 6, 2, 2, 0, 99),       # 6张偶数：攻第3大
        (7, 7, 6, 6, 0, 99),       # 7张奇数：攻最小
        (8, 8, 2, 2, 0, 99),       # 8张偶数：攻第3大
        (9, 9, 8, 8, 0, 99),       # 9张奇数：攻最小
        (10, 10, 2, 2, 0, 99),     # 10张偶数：攻第3大
        (11, 13, 10, 12, 0, 99),   # 11+张奇数：攻最小（上限兜底）
    ]
    return entries


@dataclass
class BidConstraint:
    """一个牌手在叫牌中暴露的约束。

    inference_source 标记约束来源，由约束来源分类使用：
    - 硬约束（采样验证）：hard_coded*, meaning_parsed, convention_*, cue_bid, overcall_*, unusual_nt
    - 忽略（不参与采样）：negative_inference, hcp_conservation
    """
    position: str
    min_hcp: Optional[int] = None
    max_hcp: Optional[int] = None
    balanced: Optional[bool] = None
    suit_min: Dict[str, int] = field(default_factory=dict)
    suit_max: Dict[str, int] = field(default_factory=dict)
    exact_suit: Dict[str, int] = field(default_factory=dict)
    min_controls: Optional[int] = None
    min_hcp_target: Optional[int] = None  # 已废弃：Phase 0a 后不再用于分布引导
    specific_cards: Set[Tuple[str, str]] = field(default_factory=set)
    suit_controls: Set[str] = field(default_factory=set)  # 有控制的花色（A/K 或单/缺，来自扣叫承诺）
    min_keycards: Optional[int] = None  # 关键张数量（4NT/5NT 问叫答叫承诺）
    length_above: Dict[str, Tuple[str, int]] = field(default_factory=dict)
    """该花色中点数大于基准牌的牌至少 n 张（长四首攻协议专用）。

    键=花色，值=(基准牌面, 至少张数)。如 ("♠",("8",3)) = 黑桃中
    大于 8 的牌至少 3 张（攻 8 意味该花色第 4 大是 8，比它大有 3 张）。
    只约束防守方采样；放宽/中局扣减路径按 specific_cards 同类处理。
    """
    lead_shape: Optional[Tuple[str, str, List[Tuple[Set[str], int, int]]]] = None
    """首攻顶张连张白名单（v2.15 新睿表12-1 排除法）。

    (花色, 首攻牌面, [(完整花色大牌集合, 小牌最小张数, 小牌最大张数), ...])。
    语义：该首攻牌下，该花色完整构成（剩余牌∪首攻牌）必须与某个 (大牌集, 小牌区间)
    匹配——完整花色的大牌集合（A/K/Q/J/T）必须恰好等于某白名单大牌集，
    小牌（≤9）张数落在对应区间。任何不匹配的世界（如攻K但花色含A）排除。
    例 攻K：白名单 = [({K,Q,J},0,99), ({K,Q},0,99), ({K},1,1), ({K},0,0)]。
    与 specific_cards"必持某牌"不同：它含 Kx/K 等无连张小牌的合法边界，同时
    排除 specific_cards 拦不住的"含多余大牌"形态（AK 攻K / KQ10 攻K）。
    仅首攻那张约束上持有；中局扣减（花色再出第二张）后失效。
    """
    lead_small_shapes: Optional[Tuple[str, str, List[Tuple[int, int, int, int]]]] = None
    """首攻小牌白名单（v2.15 新睿表12-1 X 行 + 表12-2 短套，排除法）。

    (花色, 首攻牌面, [(完整花色总张数min, max, 大于首攻牌张数min, max), ...])。
    覆盖与长四混淆的全部小牌首攻形态：
      · 长四  (4+ 张, ≥3 张 > X)：HHxX+ / HxxX+ / xxxX+
      · 三张  (3  张, ≥1 张 > X)：带大牌攻最小（1074→4）或 三张小牌攻中间（987→8）
      · 双张  (2  张, 0  张 > X)：双张攻大（Xx）
    完整张数、>X 张数均计入已出首攻牌（首攻牌本身不计入 >X）。
    取代旧 v2.10 单一 length_above≥3 长四（会把三张/双张世界全滤掉）。
    仅首攻那张约束上持有；中局扣减（花色再出第二张）后失效。
    """
    inference_source: str = "hard_coded"


def validate_hard(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, "BidConstraint"],
) -> bool:
    """硬约束验证：检查采样手牌是否满足所有传入约束（v1.79 起不过滤来源）。"""
    for pos, constraint in constraints.items():
        cards = hands.get(pos, [])
        if not cards:
            continue
        if not _check_constraint(cards, constraint):
            return False
    return True


def validate_relaxed(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, "BidConstraint"],
) -> bool:
    """放宽约束验证：HCP ±2, suit_min 减半（v1.79 起不过滤来源）。"""
    for pos, constraint in constraints.items():
        cards = hands.get(pos, [])
        if not cards:
            continue
        relaxed = relax_constraint(constraint)
        if not _check_constraint(cards, relaxed):
            return False
    return True


def validate_voids_only(
    hands: Dict[str, List[Card]],
    known_voids: Dict[str, Set[str]],
) -> bool:
    """仅 void 验证：只检查已知缺门（看到垫牌推得的花色张数 = 0）。"""
    for pos, void_suits in known_voids.items():
        cards = hands.get(pos, [])
        for c in cards:
            if c.suit in void_suits:
                return False
    return True


def _check_constraint(cards: List[Card], constraint: "BidConstraint") -> bool:
    """检查一手牌是否满足单个约束的所有条件。"""
    dist = _count_distribution(cards)
    hcp = _compute_hcp(cards)
    controls = _compute_controls(cards)

    if constraint.min_hcp is not None and hcp < constraint.min_hcp:
        return False
    if constraint.max_hcp is not None and hcp > constraint.max_hcp:
        return False
    if constraint.min_controls is not None and controls < constraint.min_controls:
        return False
    for suit, min_len in constraint.suit_min.items():
        if dist.get(suit, 0) < min_len:
            return False
    for suit, max_len in constraint.suit_max.items():
        if dist.get(suit, 0) > max_len:
            return False
    for suit, exact_len in constraint.exact_suit.items():
        if dist.get(suit, 0) != exact_len:
            return False
    if constraint.balanced is not None:
        is_balanced = _is_balanced(dist)
        if constraint.balanced and not is_balanced:
            return False
        if not constraint.balanced and is_balanced:
            return False
    for (suit, rank) in constraint.specific_cards:
        if not any(c.suit == suit and c.rank == rank for c in cards):
            return False
    for suit, (base_rank, need_n) in constraint.length_above.items():
        above = sum(1 for c in cards if c.suit == suit
                    and c.rank_value > _rank_value_of(base_rank))
        if above < need_n:
            return False
    if constraint.lead_shape is not None:
        if not match_suit_shape(cards, constraint.lead_shape):
            return False
    if constraint.lead_small_shapes is not None:
        if not match_suit_small_shapes(cards, constraint.lead_small_shapes):
            return False
    # v1.68 决策：扣叫（suit_controls）与关键张（min_keycards）约束
    # 只看手牌实际张数校验，对庄家/明手（手牌已知）无意义，只对防守方采样有价值；
    # 当前集中攻坐庄，暂不用在样本生成上（仍保留字段与提取链路，见 docs/约束生成优化.md
    # 「决策记录」）。防守打牌研究启用时恢复下列两段校验，并同步处理中局扣减折算。
    return True


def validate_sample(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, "BidConstraint"],
) -> bool:
    """检查采样出的手牌是否满足所有约束（v1.79 起不过滤来源）。

    等同于 validate_hard()，保留用于向后兼容。
    """
    return validate_hard(hands, constraints)



HCP_MAP = {"A": 4, "K": 3, "Q": 2, "J": 1}


def _compute_hcp(cards: List[Card]) -> int:
    return sum(HCP_MAP.get(c.rank, 0) for c in cards)


def _compute_controls(cards: List[Card]) -> int:
    return sum(CONTROL_MAP.get(c.rank, 0) for c in cards)


def _count_keycards(cards: List[Card]) -> int:
    """关键张计数：A 与 K 的总数（4NT 问叫答叫按最宽松口径 A+K 计数）。"""
    return sum(1 for c in cards if c.rank in ("A", "K"))


def _count_distribution(cards: List[Card]) -> Dict[str, int]:
    dist = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
    for c in cards:
        dist[c.suit] = dist.get(c.suit, 0) + 1
    return dist


def _is_balanced(dist: Dict[str, int]) -> bool:
    counts = list(dist.values())
    if any(c >= 6 for c in counts):
        return False
    if any(c <= 1 for c in counts):
        return False
    # 55双套也不是均型
    if sorted(counts, reverse=True)[:2] == [5, 5]:
        return False
    # 允许5332（5张低花）的半均型
    sorted_counts = sorted(counts, reverse=True)
    if sorted_counts[0] == 5 and sorted_counts[1] == 3 and sorted_counts[2] == 3 and sorted_counts[3] == 2:
        return True
    return True
