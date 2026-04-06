from typing import Dict, Optional, Any, List, Tuple
from bridge.bidding import extract_retrieval_keyword, get_partner_position, get_position_name
from llm.prompts import BIDDING_SYSTEM_PROMPT, BIDDING_FALLBACK_PROMPT, HUMAN_BID_PROMPT, EXPLAIN_BID_PROMPT
from config import MAIN_PROMPT_TEMPERATURE, FALLBACK_PROMPT_TEMPERATURE


class BiddingService:
    def __init__(self, llm_client, jf_retriever):
        self.llm_client = llm_client
        self.jf_retriever = jf_retriever
        self.use_fallback = False
        self.bid_meanings = ""
    
    def reset(self):
        self.use_fallback = False
        self.bid_meanings = ""
    
    def set_bid_meanings(self, bid_meanings: str):
        self.bid_meanings = bid_meanings
    
    def _is_no_valid_bid(self, result: Dict) -> bool:
        bid = result.get("选定叫品", "").strip()
        selection_process = result.get("叫品筛选过程", "")
        
        if bid and bid not in ["pass", "JF无合格叫品", ""]:
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
    
    def ai_bid(
        self,
        hand: Any,
        position: str,
        bidding_sequence: str,
        deal_system: str,
        verbose: bool = False
    ) -> Dict:
        if not self.llm_client.is_configured():
            return {"error": "API Key未配置", "选定叫品": "pass", "叫品含义": "API Key未配置，默认pass"}
        
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
        
        hand_display = hand.to_display_string() if hasattr(hand, 'to_display_string') else str(hand)
        hcp = hand.hcp if hasattr(hand, 'hcp') else 0
        dist = hand.distribution if hasattr(hand, 'distribution') else ""
        
        if not jf_content:
            slam_result = self.jf_retriever.retrieve_with_preprocess("成局与满贯", bidding_sequence, partner_name)
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
                verbose=verbose
            )
        
        if not is_structural:
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
                verbose=verbose
            )
        
        if not has_subsequent:
            slam_result = self.jf_retriever.retrieve_with_preprocess("成局与满贯", bidding_sequence, partner_name)
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
                verbose=verbose
            )
        
        if self.use_fallback and not is_opener:
            return self._fallback_bid(
                "",
                "",
                player_name,
                partner_name,
                hand_display,
                hcp,
                dist,
                bidding_sequence,
                is_structural,
                from_main_prompt=True,
                verbose=verbose
            )
        
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
            bid_meaning=self.bid_meanings if self.bid_meanings else "无"
        )
        
        try:
            result = self.llm_client.chat_bidding(prompt, temperature=MAIN_PROMPT_TEMPERATURE)
            result["JF约定"] = jf_keyword
            
            if self._is_no_valid_bid(result):
                if not is_opener:
                    self.use_fallback = True
                    main_prompt_output = {
                        "选定叫品": result.get("选定叫品", "N/A"),
                        "叫品筛选过程": result.get("叫品筛选过程", "N/A")
                    }
                    fallback_result = self._fallback_bid(
                        "",
                        "",
                        player_name,
                        partner_name,
                        hand_display,
                        hcp,
                        dist,
                        bidding_sequence,
                        is_structural,
                        from_main_prompt=True,
                        verbose=verbose
                    )
                    fallback_result["主提示词输出"] = main_prompt_output
                    return fallback_result
                return self._fallback_bid(
                    "",
                    "",
                    player_name,
                    partner_name,
                    hand_display,
                    hcp,
                    dist,
                    bidding_sequence,
                    is_structural,
                    from_main_prompt=True,
                    verbose=verbose
                )
            
            return result
        except Exception as e:
            if verbose:
                print(f"\n--- 主提示词异常 ---")
                print(f"错误: {e}")
            return {"error": str(e), "选定叫品": "pass", "叫品含义": f"主提示词异常: {e}"}
    
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
        from_main_prompt: bool = False,
        jf_keyword: str = None,
        verbose: bool = False
    ) -> Dict:
        actual_jf_content = jf_content
        actual_subsequent_bids = subsequent_bids_str
        actual_jf_keyword = jf_keyword
        
        if from_main_prompt:
            slam_result = self.jf_retriever.retrieve_with_preprocess("成局与满贯", bidding_sequence, partner_name)
            actual_jf_content = slam_result.get("original_content", "")
            actual_subsequent_bids = ""
            actual_jf_keyword = "成局与满贯"
        
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
            is_structural="是" if is_structural else "否"
        )
        
        try:
            result = self.llm_client.chat_bidding_fallback(prompt, temperature=FALLBACK_PROMPT_TEMPERATURE)
            result["叫品筛选过程"] = "[备用提示词] " + result.get("叫品筛选过程", "")
            result["JF约定"] = actual_jf_keyword
            
            bid = result.get("选定叫品", "").strip().lower()
            if not bid or bid in ["jf无合格叫品", "无合格叫品", "没有合格叫品"]:
                result["选定叫品"] = "pass"
                result["叫品筛选过程"] += " [强制选择pass]"
            
            return result
        except Exception as e:
            return {"选定叫品": "pass", "叫品含义": f"[备用提示词异常] {e}，强制选择pass", "叫品筛选过程": f"[备用提示词异常] {e}", "JF约定": actual_jf_keyword}
    
    def human_bid(
        self,
        user_input: str,
        position: str,
        bidding_sequence: str,
        deal_system: str,
        verbose: bool = False
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
        
        is_opener = self._check_is_opener(bidding_sequence)
        
        is_structural = jf_result.get("is_structural_convention", False)
        has_subsequent = len(subsequent_bids) > 0
        
        if is_structural and has_subsequent:
            jf_content = ""
            subsequent_bids_str = self._format_subsequent_bids(jf_result, partner_name, is_opener)
        else:
            jf_content = jf_result.get("original_content", "")
            subsequent_bids_str = ""
        
        if verbose:
            print(f"[human_bid] JF约定未匹配到 {bid}，调用AI推断")
        
        prompt = HUMAN_BID_PROMPT.format(
            bidding=bidding_sequence if bidding_sequence else "空",
            player=player_name,
            user_input=user_input,
            jf_content=jf_content,
            subsequent_bids=subsequent_bids_str
        )
        
        try:
            result = self.llm_client.chat_human_bid(prompt, temperature=0)
            result["JF约定"] = jf_keyword
            if "完整叫牌序列" not in result:
                result["完整叫牌序列"] = f"{bidding_sequence}({player_name}){bid}-"
            return result
        except Exception as e:
            full_sequence = f"{bidding_sequence}({player_name}){bid}-"
            return {"选定叫品": bid, "叫品含义": f"获取叫品含义失败: {e}", "JF约定": jf_keyword, "完整叫牌序列": full_sequence}
    
    def explain_bid(
        self,
        bid: str,
        bidding_sequence: str,
        position: str,
        deal_system: str = "2D/2H/2S：自然阻击",
        verbose: bool = False
    ) -> str:
        """解释某个叫品在当前序列下的含义（不知道手牌）"""
        
        if bid.lower() == "pass":
            return "pass：不叫"
        
        partner_name = get_partner_position(position)
        jf_keyword = extract_retrieval_keyword(bidding_sequence, deal_system, position)
        jf_result = self.jf_retriever.retrieve_with_preprocess(jf_keyword, bidding_sequence, partner_name)
        
        subsequent_bids = jf_result.get("subsequent_bids", [])
        for item in subsequent_bids:
            if item.get("bid", "").upper() == bid.upper():
                meaning = item.get("line", "")
                if meaning:
                    if verbose:
                        print(f"[explain_bid] 从JF约定匹配到 {bid} 含义: {meaning}")
                    return meaning
        
        jf_content = jf_result.get("original_content", "")
        if not jf_content:
            jf_content = "无相关JF约定"
        
        prompt = EXPLAIN_BID_PROMPT.format(
            bidding=bidding_sequence if bidding_sequence else "空（开叫位置）",
            position=position,
            bid=bid,
            jf_content=jf_content
        )
        
        try:
            if verbose:
                print(f"[explain_bid] 调用AI解释 {bid}")
            result = self.llm_client.chat(prompt, temperature=0)
            meaning = result.strip() if result else f"{bid}：含义未知"
            if verbose:
                print(f"[explain_bid] AI解释结果: {meaning}")
            return meaning
        except Exception as e:
            if verbose:
                print(f"[explain_bid] AI解释失败: {e}")
            return f"{bid}：含义未知"
    
    def build_bid_history(
        self,
        bidding_sequence: str,
        dealer: str = "南",
        deal_system: str = "2D/2H/2S：自然阻击",
        verbose: bool = False
    ) -> str:
        """从叫牌序列构建叫牌历史
        
        支持两种格式：
        - 带位置前缀: (南)pass-(西)2C-(北)pass-...
        - 不带位置前缀: pass-2C-pass-...
        """
        
        if not bidding_sequence:
            return ""
        
        import re
        position_pattern = re.compile(r'^\((南|西|北|东)\)(.+)$')
        
        bids = [b.strip() for b in bidding_sequence.split("-") if b.strip()]
        
        if not bids:
            return ""
        
        bid_history = []
        
        for i, bid_item in enumerate(bids):
            match = position_pattern.match(bid_item)
            if match:
                position = match.group(1)
                bid = match.group(2).strip()
            else:
                positions = ["南", "西", "北", "东"]
                dealer_idx = positions.index(dealer)
                position = positions[(dealer_idx + i) % 4]
                bid = bid_item
            
            if bid.lower() == "pass":
                bid_history.append(f"{position}家pass")
                continue
            
            partial_sequence = "-".join(bids[:i]) if i > 0 else ""
            
            meaning = self.explain_bid(
                bid=bid,
                bidding_sequence=partial_sequence,
                position=position,
                deal_system=deal_system,
                verbose=verbose
            )
            
            bid_history.append(f"{position}家{bid}：{meaning}")
        
        return "\n".join(bid_history)
