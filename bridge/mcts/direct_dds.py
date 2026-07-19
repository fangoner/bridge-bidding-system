"""DirectDDS：绕过 endplay PBN/Deal，直接通过 ctypes 调用 Bo Haglund 的 DDS 库。

消除 endplay 的 Card→PBN→Deal→DDS 链路，改为 Card→bitfield→DDS。

DDS 数据格式 (from endplay._dds):
- Player: North=0, East=1, South=2, West=3
- Denom: Spades=0, Hearts=1, Diamonds=2, Clubs=3, NT=4
- remainCards[player][suit]: bitfield, bit_i = 1 << i (i=2 for 2, ..., i=14 for Ace)
- deal struct: trump, first, currentTrickSuit[3], currentTrickRank[3], remainCards[4][4]
- futureTricks: nodes, cards, suit[13], rank[13], equals[13], score[13]
"""

import ctypes
import os
import sys
import threading
from typing import Dict, List, Optional, Tuple

from bridge.play_types import Card

# ── 常量：card → bit position ──
_RANK_TO_BIT = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
}

_SUIT_TO_IDX = {'♠': 0, '♥': 1, '♦': 2, '♣': 3, 'S': 0, 'H': 1, 'D': 2, 'C': 3}
_POS_TO_PLAYER = {'北': 0, '东': 1, '南': 2, '西': 3}
_PLAYER_TO_POS = {0: '北', 1: '东', 2: '南', 3: '西'}

# DDS Denom 常量
_DENOM_SPADES = 0
_DENOM_HEARTS = 1
_DENOM_DIAMONDS = 2
_DENOM_CLUBS = 3
_DENOM_NT = 4

_SUIT_TO_DENOM = {'♠': 0, '♥': 1, '♦': 2, '♣': 3, 'NT': 4}

MAXNOOFBOARDS = 200

# ── 加载 DDS DLL ──
_dds_dll = None
_dll_lock = threading.Lock()


def _load_dll():
    global _dds_dll
    if _dds_dll is not None:
        return _dds_dll
    with _dll_lock:
        if _dds_dll is not None:
            return _dds_dll
        import endplay._dds
        dds_dir = os.path.dirname(endplay._dds.__file__)
        dll_path = os.path.join(dds_dir, "dds.dll")
        if sys.platform == "win32":
            _dds_dll = ctypes.WinDLL(dll_path)
        else:
            _dds_dll = ctypes.CDLL(dll_path)
    return _dds_dll


# ── DDS 结构体定义 ──

class _deal(ctypes.Structure):
    _fields_ = [
        ("trump", ctypes.c_int),
        ("first", ctypes.c_int),
        ("currentTrickSuit", ctypes.c_int * 3),
        ("currentTrickRank", ctypes.c_int * 3),
        ("remainCards", (ctypes.c_uint * 4) * 4),
    ]


class _futureTricks(ctypes.Structure):
    _fields_ = [
        ("nodes", ctypes.c_int),
        ("cards", ctypes.c_int),
        ("suit", ctypes.c_int * 13),
        ("rank", ctypes.c_int * 13),
        ("equals", ctypes.c_int * 13),
        ("score", ctypes.c_int * 13),
    ]


class _boards(ctypes.Structure):
    _fields_ = [
        ("noOfBoards", ctypes.c_int),
        ("deals", _deal * MAXNOOFBOARDS),
        ("target", ctypes.c_int * MAXNOOFBOARDS),
        ("solutions", ctypes.c_int * MAXNOOFBOARDS),
        ("mode", ctypes.c_int * MAXNOOFBOARDS),
    ]


class _solvedBoards(ctypes.Structure):
    _fields_ = [
        ("noOfBoards", ctypes.c_int),
        ("solvedBoard", _futureTricks * MAXNOOFBOARDS),
    ]


# ── 构建 deal ──

def _hands_to_remain_cards(hands: Dict[str, List[Card]]) -> List[List[int]]:
    """将 {pos: [Card]} 转为 remainCards[4][4] 位域。

    remainCards[player][suit] = sum(1 << bit for each card in that suit)
    """
    rc = [[0] * 4 for _ in range(4)]
    for pos, cards in hands.items():
        p = _POS_TO_PLAYER.get(pos)
        if p is None:
            continue
        for c in cards:
            s = _SUIT_TO_IDX.get(c.suit)
            if s is None:
                continue
            bit = _RANK_TO_BIT.get(c.rank)
            if bit is None:
                continue
            rc[p][s] |= (1 << bit)
    return rc


def _build_deal(
    hands: Dict[str, List[Card]],
    trump: str,
    first_player: str,
    trick_cards: List[Tuple[str, Card]] = None,
) -> _deal:
    """直接从手牌构建 DDS deal 结构，无需 PBN/Deal 中间层。"""
    d = _deal()
    d.trump = _SUIT_TO_DENOM.get(trump, _DENOM_NT)
    d.first = _POS_TO_PLAYER.get(first_player, 0)

    # currentTrickSuit/Rank: 最多 3 张已出牌
    if trick_cards:
        for i, (pos, card) in enumerate(trick_cards[:3]):
            d.currentTrickSuit[i] = _SUIT_TO_IDX.get(card.suit, 0)
            d.currentTrickRank[i] = _RANK_TO_BIT.get(card.rank, 2)
    # 剩余位置保持 0（DDS 用 0 表示空）

    # remainCards
    rc = _hands_to_remain_cards(hands)
    for p in range(4):
        for s in range(4):
            d.remainCards[p][s] = rc[p][s]

    return d


# ── 解析结果 ──

def _parse_future_tricks(ft: _futureTricks) -> List[Tuple[int, int, int, int]]:
    """解析 DDS 返回的 futureTricks。

    Returns: List[(suit_id, rank_bit, equals, score)]
      suit_id: 0=S, 1=H, 2=D, 3=C
      rank_bit: 2-14 (同 _RANK_TO_BIT)
      equals: bitfield of equal cards
      score: 当前出牌方所在阵营的剩余赢墩数
    """
    results = []
    n = ft.cards
    for i in range(min(n, 13)):
        results.append((
            ft.suit[i],
            ft.rank[i],
            ft.equals[i],
            ft.score[i],
        ))
    return results


# ── 主接口 ──

def solve_all_boards_raw(
    deals_data: List[Tuple[Dict[str, List[Card]], str, str, List[Tuple[str, Card]]]],
    target: int = -1,
    mode: int = 1,
) -> List[Optional[List[Tuple[int, int, int, int]]]]:
    """批量 DDS 求解，直接传手牌，无 PBN 转换。

    Args:
        deals_data: [(hands, trump, first_player, trick_cards), ...]
        target: -1 = 不限制目标（与 endplay 一致）
        mode: 1 = 不限制

    Returns:
        与 deals_data 等长的结果列表。每条结果 = [(suit, rank_bit, equals, score), ...]
        失败时对应位置为 None。
    """
    dll = _load_dll()
    n = len(deals_data)
    if n == 0:
        return []
    if n > MAXNOOFBOARDS:
        raise ValueError(f"Too many boards ({n}), max {MAXNOOFBOARDS}")

    bop = _boards()
    bop.noOfBoards = n
    for i, (hands, trump, first_player, trick_cards) in enumerate(deals_data):
        bop.deals[i] = _build_deal(hands, trump, first_player, trick_cards)
        bop.target[i] = target
        bop.solutions[i] = 3  # solutions=3 = 返回所有可能出牌（与 endplay SolveMode.Default 一致）
        bop.mode[i] = mode

    solvedp = _solvedBoards()

    # 调用 DDS（argtypes/restype 确保 64-bit 指针正确传递）
    dll.SolveAllBoardsBin.argtypes = [ctypes.POINTER(_boards), ctypes.POINTER(_solvedBoards)]
    dll.SolveAllBoardsBin.restype = ctypes.c_int
    ret = dll.SolveAllBoardsBin(ctypes.byref(bop), ctypes.byref(solvedp))
    if ret != 1:
        return [None] * n

    results = []
    for i in range(n):
        try:
            ft = solvedp.solvedBoard[i]
            if ft.cards == 0:
                results.append(None)
            else:
                results.append(_parse_future_tricks(ft))
        except Exception:
            results.append(None)

    return results


# ── 便捷接口（兼容现有 _evaluate_leaf / _evaluate_min_dds 的调用方式）──

def solve_from_next_states(
    next_states: List[Tuple[Dict[str, List[Card]], dict]],
    trump: str,
    declarer: str,
) -> List[Optional[List[Tuple[int, int, int, int]]]]:
    """从 _evaluate_leaf 的 next_states 格式批量求解。

    每个 next_state = (hands, ns_info)
      ns_info["new_trick"] = {"leader": str, "cards": [(pos, Card), ...]}
      ns_info["new_current"] = player after applying the move

    Returns: 与 next_states 等长的结果列表。
    """
    batch = []
    for hands, ns_info in next_states:
        if ns_info.get("impossible") or hands is None:
            batch.append(None)
            continue
        trick_info = ns_info.get("new_trick", {})
        trick_cards = trick_info.get("cards", [])
        first = trick_info.get("leader") or ns_info.get("new_current", "北")
        batch.append((hands, trump, first, trick_cards))

    # 只对非 None 的求解
    valid_indices = []
    valid_data = []
    for i, item in enumerate(batch):
        if item is not None:
            valid_indices.append(i)
            valid_data.append(item)

    if not valid_data:
        return [None] * len(next_states)

    raw_results = solve_all_boards_raw(valid_data)
    # 合并回去
    all_results = [None] * len(next_states)
    for j, raw in zip(valid_indices, raw_results):
        all_results[j] = raw
    return all_results


# ── 结果格式转换（兼容现有 _compute_decl_tricks_from_solved）──

def dds_result_to_decl_tricks(
    solved,
    decl_tricks: int,
    def_tricks: int,
    declarer: str,
    dummy: str,
    first_player: str,
    trick_cards_count: int = 0,
) -> Optional[int]:
    """将 DDS 原始结果转为庄家总赢墩数。

    与 _compute_decl_tricks_from_solved 语义一致。
    solved: [(suit, rank_bit, equals, score), ...]
    score = 当前出牌方所在阵营的剩余赢墩数
    """
    if not solved:
        return None
    try:
        # DDS 的 curplayer = (first + len(trick_cards)) % 4
        first_p = _POS_TO_PLAYER.get(first_player, 0)
        cur_p = (first_p + trick_cards_count) % 4
        cur_pos = _PLAYER_TO_POS.get(cur_p, first_player)
        curplayer_is_declarer = cur_pos in (declarer, dummy)
        remaining_tricks = 13 - (decl_tricks + def_tricks)
        side_tricks = max(score for _, _, _, score in solved)
        if curplayer_is_declarer:
            return decl_tricks + side_tricks
        else:
            return decl_tricks + (remaining_tricks - side_tricks)
    except Exception:
        return None


# ── Bitmap 直接输入（跳过 Card→bit 转换）──

def _build_deal_from_bits(
    hands_bits: Dict[str, int],
    trump: str,
    first_player: str,
    trick_cards: List[Tuple[str, any]] = None,
) -> _deal:
    """从 bitmap 手牌直接构建 DDS deal，零 Card 迭代。"""
    d = _deal()
    d.trump = _SUIT_TO_DENOM.get(trump, _DENOM_NT)
    d.first = _POS_TO_PLAYER.get(first_player, 0)

    if trick_cards:
        for i, (pos, card) in enumerate(trick_cards[:3]):
            if hasattr(card, 'suit'):
                d.currentTrickSuit[i] = _SUIT_TO_IDX.get(card.suit, 0)
                d.currentTrickRank[i] = _RANK_TO_BIT.get(card.rank, 0)
            elif isinstance(card, int) and card != 0:
                s_idx = 0
                for si in range(4):
                    if (card >> (si * 16)) & 0xFFFF:
                        s_idx = si
                        break
                suit_bits = (card >> (s_idx * 16)) & 0xFFFF
                r_bit = (suit_bits & -suit_bits).bit_length() - 1
                d.currentTrickSuit[i] = s_idx
                d.currentTrickRank[i] = r_bit

    # 从 bitmap 直接提取 remainCards[4][4]
    for pos, bits in hands_bits.items():
        p = _POS_TO_PLAYER.get(pos)
        if p is None:
            continue
        for s in range(4):
            d.remainCards[p][s] = (bits >> (s * 16)) & 0xFFFF

    return d


def solve_all_boards_bits(
    deals_data: List[Tuple[Dict[str, int], str, str, List[Tuple[str, any]]]],
    target: int = -1,
    mode: int = 1,
) -> List[Optional[List[Tuple[int, int, int, int]]]]:
    """Bitmap 版批量 DDS 求解。hands 是 {pos: int}，直接构造 DDS 结构。

    Args:
        deals_data: [(hands_bits, trump, first_player, trick_cards), ...]
    """
    dll = _load_dll()
    n = len(deals_data)
    if n == 0:
        return []

    all_results = []
    for batch_start in range(0, n, MAXNOOFBOARDS):
        batch_end = min(batch_start + MAXNOOFBOARDS, n)
        batch = deals_data[batch_start:batch_end]
        bn = len(batch)

        bop = _boards()
        bop.noOfBoards = bn
        for i, (hands_bits, trump, first_player, trick_cards) in enumerate(batch):
            bop.deals[i] = _build_deal_from_bits(hands_bits, trump, first_player, trick_cards)
            bop.target[i] = target
            bop.solutions[i] = 3
            bop.mode[i] = mode

        solvedp = _solvedBoards()
        dll.SolveAllBoardsBin.argtypes = [ctypes.POINTER(_boards), ctypes.POINTER(_solvedBoards)]
        dll.SolveAllBoardsBin.restype = ctypes.c_int
        ret = dll.SolveAllBoardsBin(ctypes.byref(bop), ctypes.byref(solvedp))
        if ret != 1:
            all_results.extend([None] * bn)
            continue

        for i in range(bn):
            try:
                ft = solvedp.solvedBoard[i]
                if ft.cards == 0:
                    all_results.append(None)
                else:
                    all_results.append(_parse_future_tricks(ft))
            except Exception:
                all_results.append(None)

    return all_results
