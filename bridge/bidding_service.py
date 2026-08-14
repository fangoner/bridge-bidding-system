from typing import Dict, Optional, Any, List, Tuple
import json
from bridge.bidding import extract_retrieval_keyword, get_partner_position, get_position_name, is_valid_bid, parse_bidding_sequence, parse_bidding_sequence_with_positions
from llm.prompts import BIDDING_SYSTEM_PROMPT, BIDDING_FALLBACK_PROMPT, HUMAN_BID_PROMPT
from config import MAIN_PROMPT_TEMPERATURE, FALLBACK_PROMPT_TEMPERATURE

# 合规性检查重试次数配置
# 主提示词路径：最多重试 2 次（共 3 次 LLM 调用）
# 备用提示词路径：最多重试 1 次（共 2 次 LLM 调用）
# 超过后报错并暂停叫牌
MAIN_PROMPT_MAX_RETRIES = 2
FALLBACK_PROMPT_MAX_RETRIES = 1


class BiddingService:
    def __init__(self, llm_client, jf_retriever):
        self.llm_client = llm_client
        self.jf_retriever = jf_retriever
        self.use_fallback = False
        self.bid_meanings = ""
        self._slam_cache = None
        self._last_prompt = None

    def reset(self):
        self.use_fallback = False
        self.bid_meanings = ""
        self._slam_cache = None
        self._last_prompt = None

    def _get_slam_result(self, bidding_sequence, partner_name):
        if self._slam_cache is None:
            self._slam_cache = self.jf_retriever.retrieve_with_preprocess("成局与满贯", bidding_sequence, partner_name)
        return self._slam_cache
    
    def set_bid_meanings(self, bid_meanings: str):
        self.bid_meanings = bid_meanings
    
    def _is_no_valid_bid(self, result: Dict) -> bool:
        bid = result.get("选定叫品", "")
        # LLM 可能返回 dict/list 等非 str 类型，统一转为 str
        if not isinstance(bid, str):
            bid = json.dumps(bid, ensure_ascii=False) if bid is not None else ""
        bid = bid.strip()
        selection_process = result.get("叫品筛选过程", "")
        if not isinstance(selection_process, str):
            selection_process = json.dumps(selection_process, ensure_ascii=False) if selection_process is not None else ""
        
        if bid and bid not in ["pass", "JF无合格叫品", ""]:
            return False
        
        if bid == "pass":
            return False
        
        no_valid_keywords = ["JF无合格叫品", "无合格叫品", "没有合格叫品"]
        
        for keyword in no_valid_keywords:
            if keyword in selection_process:
                return True
        
        return False
    
    def _format_subsequent_bids(self, jf_result: Dict, partner_name: str, is_opener: bool) -> str:
        if not jf_result.get("subsequent_bids"):
            return ""
        
        if is_opener:
            subsequent_bids_str = "\n\n【预处理提取的开叫叫品】\n当前玩家的备选叫品：\n"
        else:
            subsequent_bids_str = "\n\n【预处理提取的后续叫品】\n队友" + partner_name + "家最近叫品：" + (jf_result.get("partner_bid") or "无") + "\n当前玩家的备选叫品：\n"
        
        for sb in jf_result.get("subsequent_bids", []):
            bid = sb.get('bid', '')
            line = sb.get('line', '')
            subsequent_bids_str += f"  {bid}：{line}\n"
        
        return subsequent_bids_str
    
    def _check_is_opener(self, bidding_sequence: str) -> bool:
        has_non_pass_bid = False
        for part in bidding_sequence.split('-'):
            part = part.strip()
            if part and 'pass' not in part.lower():
                has_non_pass_bid = True
                break
        return not has_non_pass_bid

    def _inject_computed_fields(self, result: Dict, bidding_sequence: str, player_name: str) -> None:
        result["当前叫牌序列"] = bidding_sequence if bidding_sequence else "空（开叫位置）"
        result["自己pass次数"] = str(bidding_sequence.lower().count("pass"))
        bid = result.get("选定叫品", "pass")
        # P2-28 修复：与 fallback 路径一致，dict/list 型叫品先规范化为 str，
        # 避免 _normalize_bid 内 bid.strip() 抛 AttributeError（主路径直接报错不重试的问题）
        if not isinstance(bid, str):
            bid = json.dumps(bid, ensure_ascii=False) if bid is not None else "pass"
            result["选定叫品"] = bid
        bid_normalized = self._normalize_bid(bid)
        if bid_normalized != bid:
            result["选定叫品"] = bid_normalized
            bid = bid_normalized
        bidding_prefix = bidding_sequence if bidding_sequence else ""
        result["完整叫牌序列"] = f"{bidding_prefix}({player_name}){bid}-"

    def _normalize_bid(self, bid: str) -> str:
        b = bid.strip()
        if b.lower() in ("p", "pass", "pass!"):
            return "pass"
        if b.upper() in ("X", "XX"):
            return b.upper()
        return b

    def _get_last_substantive_bid(self, bidding_sequence: str) -> Optional[str]:
        """从叫牌序列中提取最后一个非 pass 的实质叫品（用于 is_valid_bid 的 last_bid 参数）"""
        if not bidding_sequence:
            return None
        bids = parse_bidding_sequence(bidding_sequence)
        for b in reversed(bids):
            if b.lower() not in ("pass", "p"):
                return b
        return None

    def _check_bid_validity(self, result: Dict, bidding_sequence: str, player_name: str) -> Optional[str]:
        """检查叫品合规性，返回违规原因字符串（None 表示合法）。

        不修改 result，仅返回检查结果。覆盖范围：
        - 实质叫品递增规则（is_valid_bid：阶次更高或同阶更高花色）
        - 加倍合法性：仅当对方有实质叫品时可加倍
        - 再加倍合法性：仅当对方加倍时可再加倍
        """
        bid = result.get("选定叫品", "pass")
        if not isinstance(bid, str):
            bid = "pass"
        bid = bid.strip()

        # 1. 加倍/再加倍合法性（is_valid_bid 直接放行 X/XX，需要单独检查）
        if bid in ("X", "XX"):
            return self._check_double_validity(bid, bidding_sequence, player_name)

        # 2. 实质叫品递增检查
        if not is_valid_bid(bid, self._get_last_substantive_bid(bidding_sequence)):
            last_bid = self._get_last_substantive_bid(bidding_sequence)
            return f"叫品 '{bid}' 非法（上一个实质叫品: {last_bid or '无'}，未满足递增规则）"

        return None

    def _check_double_validity(self, bid: str, bidding_sequence: str, player_name: str) -> Optional[str]:
        """验证加倍/再加倍的合法性，返回违规原因字符串（合法则返回 None）。

        桥牌规则：
        - X（加倍）：仅当上一个实质叫品来自对方时合法（不能加倍队友或自己）
        - XX（再加倍）：仅当上一个叫品是对方的 X 时合法
        """
        if not bidding_sequence:
            return f"{bid} 非法：空序列不能加倍/再加倍"

        pos_bids = parse_bidding_sequence_with_positions(bidding_sequence)
        if not pos_bids:
            return f"{bid} 非法：无法解析叫牌序列"

        # 从后往前找最后一个非 pass 的叫品
        last_pos, last_bid = None, None
        for pos, b in reversed(pos_bids):
            if b.lower() != "pass":
                last_pos, last_bid = pos, b
                break

        if last_pos is None:
            return f"{bid} 非法：之前无实质叫品，不能加倍/再加倍"

        # 判断 last_pos 与 player_name 的关系
        if last_pos == player_name:
            return f"{bid} 非法：上一叫品来自自己({player_name})"
        if self._is_partner_position(player_name, last_pos):
            return f"{bid} 非法：上一叫品来自队友({last_pos})，不能加倍队友"

        # 此处 last_pos 是对方
        if bid == "X":
            if last_bid in ("X", "XX"):
                return f"X 非法：上一叫品是 {last_bid}，不能加倍"
            # 对方有实质叫品 → X 合法
            return None

        # bid == "XX"
        if last_bid != "X":
            return f"XX 非法：上一叫品是 {last_bid}（不是X），不能再加倍"
        return None

    def _is_partner_position(self, pos1: str, pos2: str) -> bool:
        """判断两个位置是否是搭档（支持中英文位置标识）"""
        partner_map = {
            "南": "北", "北": "南", "东": "西", "西": "东",
            "S": "N", "N": "S", "E": "W", "W": "E",
        }
        return partner_map.get(pos1) == pos2

    def ai_bid(
        self,
        hand: Any,
        position: str,
        bidding_sequence: str,
        deal_system: str,
        verbose: bool = False,
        use_reasoning: bool = False,
    ) -> Dict:
        if not self.llm_client.is_configured():
            return {"error": "API Key未配置", "选定叫品": "pass", "叫品含义": "API Key未配置，默认pass"}
        
        self._use_reasoning = use_reasoning
        player_name = position
        partner_name = get_partner_position(position)
        
        jf_keyword = extract_retrieval_keyword(bidding_sequence, deal_system, player_name)
        jf_result = self.jf_retriever.retrieve_with_preprocess(jf_keyword, bidding_sequence, partner_name)
        
        is_opener = self._check_is_opener(bidding_sequence)
        
        if is_opener:
            self.use_fallback = False
        
        jf_content = jf_result.get("original_content", "")
        subsequent_bids_str = self._format_subsequent_bids(jf_result, partner_name, is_opener)
        
        is_structural = jf_result.get("is_structural_convention", False)
        has_subsequent = len(jf_result.get("subsequent_bids", [])) > 0
        
        if verbose:
            print(f"[ai_bid] bidding_sequence={bidding_sequence!r}, position={player_name}, jf_keyword={jf_keyword!r}")
            print(f"[ai_bid] is_opener={is_opener}, jf_content_empty={not jf_content}, is_structural={is_structural}, has_subsequent={has_subsequent}")
            print(f"[ai_bid] subsequent_bids_count={len(jf_result.get('subsequent_bids', []))}, use_fallback={self.use_fallback}")
        
        hand_display = hand.to_display_string() if hasattr(hand, 'to_display_string') else str(hand)
        hcp = hand.hcp if hasattr(hand, 'hcp') else 0
        dist = hand.distribution if hasattr(hand, 'distribution') else ""
        
        if not jf_content:
            if verbose:
                print(f"[ai_bid] PATH: fallback - no jf_content, using 成局与满贯")
            slam_result = self._get_slam_result(bidding_sequence, partner_name)
            return self._fallback_bid(
                slam_result.get("original_content", ""),
                "",
                player_name,
                partner_name,
                hand_display,
                hcp,
                dist,
                bidding_sequence,
                is_structural,
                jf_keyword="成局与满贯",
                deal_system=deal_system,
                verbose=verbose
            )
        
        if not is_structural:
            if verbose:
                print(f"[ai_bid] PATH: fallback - not structural, jf_keyword={jf_keyword!r}")
            return self._fallback_bid(
                jf_content,
                "",
                player_name,
                partner_name,
                hand_display,
                hcp,
                dist,
                bidding_sequence,
                is_structural,
                jf_keyword=jf_keyword,
                deal_system=deal_system,
                verbose=verbose
            )
        
        if not has_subsequent:
            if verbose:
                print(f"[ai_bid] PATH: fallback - no subsequent bids, using 成局与满贯")
            slam_result = self._get_slam_result(bidding_sequence, partner_name)
            return self._fallback_bid(
                slam_result.get("original_content", ""),
                "",
                player_name,
                partner_name,
                hand_display,
                hcp,
                dist,
                bidding_sequence,
                is_structural,
                jf_keyword="成局与满贯",
                deal_system=deal_system,
                verbose=verbose
            )

        # 主提示词路径：jf_content 始终置空，LLM 依赖 subsequent_bids（预处理结果）选择叫品
        # 预处理结果已从 JF 片段中提取了备选叫品树，再注入原始 jf_content 是重复且可能干扰判断

        # 合规性检查重试循环：不合规时重新调用 LLM，重试时附加反馈
        original_bid_meanings = self.bid_meanings
        last_violation = None
        last_result = None

        for attempt in range(MAIN_PROMPT_MAX_RETRIES + 1):
            # 重试时在 bid_meanings 附加反馈，让 LLM 知道上次叫品为何非法
            if attempt > 0 and last_violation:
                feedback = f"\n[系统反馈] 上次叫品非法: {last_violation}，请严格检查合规性（叫品递增/加倍合法性）后重新选择"
                self.bid_meanings = (original_bid_meanings + feedback) if original_bid_meanings else feedback
            else:
                self.bid_meanings = original_bid_meanings

            prompt = BIDDING_SYSTEM_PROMPT.format(
                jf_content="",
                subsequent_bids=subsequent_bids_str,
                player=player_name,
                partner=partner_name,
                hand=hand_display,
                hcp=hcp,
                dist=dist,
                bidding=bidding_sequence if bidding_sequence else "空（开叫位置）",
                jf_keyword=jf_keyword,
                bid_meaning=self.bid_meanings if self.bid_meanings else "无",
                deal_system=deal_system
            )
            self._last_prompt = prompt

            try:
                result = self.llm_client.chat_bidding(prompt, temperature=MAIN_PROMPT_TEMPERATURE, thinking=self._use_reasoning)
                result["JF约定"] = jf_keyword
                result["阻击叫体系"] = deal_system

                if self._is_no_valid_bid(result):
                    # 无合格叫品，恢复 bid_meanings 并走 fallback
                    # 主提示词已用备选叫品列表验证过，原始结构性JF片段对fallback无帮助，用"成局与满贯"兜底
                    self.bid_meanings = original_bid_meanings
                    slam_result = self._get_slam_result(bidding_sequence, partner_name)
                    if not is_opener:
                        # P0-2 修复：不再设置 self.use_fallback = True
                        # 原逻辑会通过前端 setUseFallback 闭环传播，导致后续轮次跳过主提示词
                        # 现在每轮独立判断，仅在当轮走 fallback
                        main_prompt_output = {
                            "选定叫品": result.get("选定叫品", "N/A"),
                            "叫品筛选过程": result.get("叫品筛选过程", "N/A")
                        }
                        fallback_result = self._fallback_bid(
                            slam_result.get("original_content", ""),
                            "",
                            player_name,
                            partner_name,
                            hand_display,
                            hcp,
                            dist,
                            bidding_sequence,
                            is_structural,
                            jf_keyword="成局与满贯",
                            deal_system=deal_system,
                            verbose=verbose
                        )
                        fallback_result["主提示词输出"] = main_prompt_output
                        return fallback_result
                    return self._fallback_bid(
                        slam_result.get("original_content", ""),
                        "",
                        player_name,
                        partner_name,
                        hand_display,
                        hcp,
                        dist,
                        bidding_sequence,
                        is_structural,
                        jf_keyword="成局与满贯",
                        deal_system=deal_system,
                        verbose=verbose
                    )

                self._inject_computed_fields(result, bidding_sequence, player_name)

                # 合规性检查
                violation = self._check_bid_validity(result, bidding_sequence, player_name)
                if violation is None:
                    # 合法，恢复 bid_meanings 并返回
                    self.bid_meanings = original_bid_meanings
                    return result

                last_violation = violation
                last_result = result
                if verbose:
                    print(f"[ai_bid] 主提示词第 {attempt+1} 次叫品非法: {violation}")
            except Exception as e:
                self.bid_meanings = original_bid_meanings
                if verbose:
                    print(f"\n--- 主提示词异常 ---")
                    print(f"错误: {e}")
                return {"error": str(e), "选定叫品": "pass", "叫品含义": f"主提示词异常: {e}"}

        # 主路径重试耗尽，走 fallback
        # 主提示词已用备选叫品列表验证过，原始结构性JF片段对fallback无帮助，用"成局与满贯"兜底
        self.bid_meanings = original_bid_meanings
        if verbose:
            print(f"[ai_bid] 主提示词连续 {MAIN_PROMPT_MAX_RETRIES+1} 次叫品非法({last_violation})，走 fallback")

        main_prompt_output = {
            "选定叫品": last_result.get("选定叫品", "N/A") if last_result else "N/A",
            "叫品筛选过程": (last_result.get("叫品筛选过程", "N/A") if last_result else "N/A") + f"\n[合规性重试耗尽] {last_violation}",
            "合规性违规": last_violation
        }
        slam_result = self._get_slam_result(bidding_sequence, partner_name)
        fallback_result = self._fallback_bid(
            slam_result.get("original_content", ""),
            "",
            player_name,
            partner_name,
            hand_display,
            hcp,
            dist,
            bidding_sequence,
            is_structural,
            jf_keyword="成局与满贯",
            deal_system=deal_system,
            verbose=verbose
        )
        fallback_result["主提示词输出"] = main_prompt_output
        return fallback_result
    
    def _fallback_bid(
        self,
        jf_content: str,
        subsequent_bids_str: str,
        player_name: str,
        partner_name: str,
        hand_display: str,
        hcp: int,
        dist: str,
        bidding_sequence: str,
        is_structural: bool,
        jf_keyword: str = None,
        deal_system: str = "2D/2H/2S：自然阻击",
        verbose: bool = False
    ) -> Dict:
        actual_jf_content = jf_content
        actual_subsequent_bids = subsequent_bids_str
        actual_jf_keyword = jf_keyword

        # 合规性检查重试循环：不合规时重新调用 LLM，重试时附加反馈
        original_bid_meanings = self.bid_meanings
        last_violation = None
        last_result = None

        for attempt in range(FALLBACK_PROMPT_MAX_RETRIES + 1):
            # 重试时在 bid_meanings 附加反馈
            if attempt > 0 and last_violation:
                feedback = f"\n[系统反馈] 上次叫品非法: {last_violation}，请严格检查合规性（叫品递增/加倍合法性）后重新选择"
                self.bid_meanings = (original_bid_meanings + feedback) if original_bid_meanings else feedback
            else:
                self.bid_meanings = original_bid_meanings

            prompt = BIDDING_FALLBACK_PROMPT.format(
                jf_content=actual_jf_content,
                subsequent_bids=actual_subsequent_bids,
                player=player_name,
                partner=partner_name,
                hand=hand_display,
                hcp=hcp,
                dist=dist,
                bidding=bidding_sequence if bidding_sequence else "空（开叫位置）",
                jf_keyword=actual_jf_keyword,
                bid_meaning=self.bid_meanings if self.bid_meanings else "无",
                is_structural="是" if is_structural else "否",
                deal_system=deal_system
            )
            self._last_prompt = prompt

            try:
                result = self.llm_client.chat_bidding_fallback(prompt, temperature=FALLBACK_PROMPT_TEMPERATURE, thinking=self._use_reasoning)
                # LLM 偶尔返回 dict/list 类型的字段（schema 声明是 string 但未强制），
                # 这里统一规范化为 str，避免后续字符串拼接抛 TypeError
                for _k in ("叫品筛选过程", "叫品含义", "选定叫品", "叫牌位置", "手牌分析", "叫牌历史"):
                    _v = result.get(_k, "")
                    if not isinstance(_v, str):
                        result[_k] = json.dumps(_v, ensure_ascii=False) if _v is not None else ""
                result["叫品筛选过程"] = "[备用提示词] " + result.get("叫品筛选过程", "")
                result["JF约定"] = actual_jf_keyword
                result["阻击叫体系"] = deal_system

                bid = result.get("选定叫品", "").strip()
                if not bid or bid in ["jf无合格叫品", "无合格叫品", "没有合格叫品"]:
                    result["选定叫品"] = "pass"
                    result["叫品筛选过程"] += " [强制选择pass]"

                self._inject_computed_fields(result, bidding_sequence, player_name)

                # 合规性检查
                violation = self._check_bid_validity(result, bidding_sequence, player_name)
                if violation is None:
                    # 合法，恢复 bid_meanings 并返回
                    self.bid_meanings = original_bid_meanings
                    return result

                last_violation = violation
                last_result = result
                if verbose:
                    print(f"[fallback] 第 {attempt+1} 次叫品非法: {violation}")
            except Exception as e:
                self.bid_meanings = original_bid_meanings
                return {"选定叫品": "pass", "叫品含义": f"[备用提示词异常] {e}，强制选择pass", "叫品筛选过程": f"[备用提示词异常] {e}", "JF约定": actual_jf_keyword, "阻击叫体系": deal_system}

        # fallback 重试耗尽，报错并暂停叫牌
        self.bid_meanings = original_bid_meanings
        if verbose:
            print(f"[fallback] 连续 {FALLBACK_PROMPT_MAX_RETRIES+1} 次叫品非法({last_violation})，暂停叫牌")

        # 标记暂停叫牌：前端识别 暂停叫牌=True 后停止自动叫牌
        return {
            "error": f"备用提示词连续 {FALLBACK_PROMPT_MAX_RETRIES+1} 次叫品非法: {last_violation}",
            "选定叫品": "pass",
            "叫品含义": f"[合规性错误] 备用提示词连续 {FALLBACK_PROMPT_MAX_RETRIES+1} 次叫品非法({last_violation})，已暂停叫牌等待处理",
            "叫品筛选过程": (last_result.get("叫品筛选过程", "") if last_result else "") + f"\n[合规性错误] 重试耗尽: {last_violation}",
            "JF约定": actual_jf_keyword,
            "阻击叫体系": deal_system,
            "暂停叫牌": True,
        }
    
    def human_bid(
        self,
        user_input: str,
        position: str,
        bidding_sequence: str,
        deal_system: str,
        verbose: bool = False,
        use_reasoning: bool = False,
    ) -> Dict:
        bid = user_input.strip().upper()
        if bid == "P":
            bid = "pass"

        if bid.lower() == "pass":
            player_name = position
            bidding_prefix = bidding_sequence if bidding_sequence else ""
            full_sequence = f"{bidding_prefix}({player_name})pass-"
            return {"选定叫品": "pass", "叫品含义": "pass：不叫", "JF约定": "", "完整叫牌序列": full_sequence}

        player_name = position
        partner_name = get_partner_position(position)

        jf_keyword = extract_retrieval_keyword(bidding_sequence, deal_system, player_name)
        jf_result = self.jf_retriever.retrieve_with_preprocess(jf_keyword, bidding_sequence, partner_name)

        subsequent_bids = jf_result.get("subsequent_bids", [])
        for item in subsequent_bids:
            if item.get("bid", "").upper() == bid.upper():
                meaning = item.get("line", "")
                if meaning:
                    if verbose:
                        print(f"[human_bid] 从JF约定匹配到 {bid} 含义: {meaning}")
                    full_sequence = f"{bidding_sequence}({player_name}){bid}-"
                    return {"选定叫品": bid, "叫品含义": meaning, "JF约定": jf_keyword, "完整叫牌序列": full_sequence}

        if not self.llm_client.is_configured():
            full_sequence = f"{bidding_sequence}({player_name}){bid}-"
            return {"选定叫品": bid, "叫品含义": "API Key未配置，无法获取叫品含义", "JF约定": jf_keyword, "完整叫牌序列": full_sequence}

        has_subsequent = len(subsequent_bids) > 0

        if has_subsequent:
            if verbose:
                print(f"[human_bid] 结构性JF片段，{bid} 不在备选叫品中，无需调用LLM")
            full_sequence = f"{bidding_sequence}({player_name}){bid}-"
            return {"选定叫品": bid, "叫品含义": f"叫品 {bid} 不在JF约定（{jf_keyword}）的备选叫品中", "JF约定": jf_keyword, "完整叫牌序列": full_sequence}

        jf_content = jf_result.get("original_content", "")
        actual_jf_keyword = jf_keyword

        if not jf_content:
            slam_result = self._get_slam_result(bidding_sequence, partner_name)
            jf_content = slam_result.get("original_content", "")
            actual_jf_keyword = "成局与满贯"
            if verbose:
                print(f"[human_bid] PATH: fallback - no jf_content, using 成局与满贯")

        if verbose:
            print(f"[human_bid] 非结构性JF片段，注入原始内容调用AI推断")

        prompt = HUMAN_BID_PROMPT.format(
            bidding=bidding_sequence if bidding_sequence else "空",
            player=player_name,
            user_input=user_input,
            jf_content=jf_content,
            deal_system=deal_system,
            bid_meaning=self.bid_meanings if self.bid_meanings else "（暂无）"
        )
        self._last_prompt = prompt

        try:
            result = self.llm_client.chat_human_bid(prompt, temperature=0, thinking=use_reasoning)
            result["JF约定"] = actual_jf_keyword
            if "完整叫牌序列" not in result:
                result["完整叫牌序列"] = f"{bidding_sequence}({player_name}){bid}-"
            return result
        except Exception as e:
            full_sequence = f"{bidding_sequence}({player_name}){bid}-"
            return {"选定叫品": bid, "叫品含义": f"获取叫品含义失败: {e}", "JF约定": actual_jf_keyword, "完整叫牌序列": full_sequence}
