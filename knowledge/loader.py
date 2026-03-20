from docx import Document
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import re


class JFLoader:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.segments: List[Dict[str, str]] = []
        
    def load(self) -> List[Dict[str, str]]:
        self.segments = []
        doc = Document(self.file_path)
        
        current_segment = []
        empty_count = 0
        
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                empty_count += 1
                if empty_count >= 2 and current_segment:
                    segment_text = "\n".join(current_segment)
                    self.segments.append({
                        "content": segment_text,
                        "keywords": self._extract_keywords(segment_text)
                    })
                    current_segment = []
            else:
                if empty_count >= 2 and current_segment:
                    segment_text = "\n".join(current_segment)
                    self.segments.append({
                        "content": segment_text,
                        "keywords": self._extract_keywords(segment_text)
                    })
                    current_segment = []
                current_segment.append(text)
                empty_count = 0
        
        if current_segment:
            segment_text = "\n".join(current_segment)
            self.segments.append({
                "content": segment_text,
                "keywords": self._extract_keywords(segment_text)
            })
        
        return self.segments
    
    def _extract_keywords(self, text: str) -> List[str]:
        keywords = []
        lines = text.split("\n")
        
        for i, line in enumerate(lines[:3]):
            line = line.strip()
            if line:
                keywords.append(line)
        
        return keywords


def parse_indent_level(line: str) -> int:
    count = 0
    i = 0
    while i < len(line):
        if i + 5 <= len(line) and line[i:i+5] == '│----':
            count += 1
            i += 5
        elif i + 5 <= len(line) and line[i:i+5] == '├----':
            count += 1
            i += 5
        elif i + 6 <= len(line) and line[i] == '│' and line[i+1:i+6] == '-----':
            count += 1
            i += 6
        elif i + 6 <= len(line) and line[i] == '├' and line[i+1:i+6] == '-----':
            count += 1
            i += 6
        elif line[i] == '│' and i + 1 < len(line) and line[i+1] == ' ':
            count += 1
            i += 6
        elif line[i] in '│├':
            i += 1
        elif line[i] in '- ':
            i += 1
        else:
            break
    return count


def extract_bid_from_line(line: str) -> Optional[str]:
    stripped = line.lstrip('│├- ')
    match = re.match(r'^(\d[CDHSNT]|pass|X{1,2}|[1-7][CDHSNT])', stripped, re.IGNORECASE)
    if match:
        bid = match.group(1).upper()
        bid = bid.replace('10', 'T')
        if bid.endswith('N') and len(bid) >= 2 and bid[0].isdigit():
            bid = bid[:-1] + 'NT'
        return bid
    return None


def normalize_bid(bid: str) -> str:
    if not bid:
        return ""
    bid = bid.upper().replace('10', 'T')
    if bid.endswith('NT'):
        return bid
    if bid.endswith('N') and len(bid) >= 2 and bid[0].isdigit():
        return bid[:-1] + 'NT'
    return bid


def parse_content_to_tree(content: str) -> Optional[Dict]:
    lines = [l.rstrip() for l in content.splitlines() if l.strip()]
    
    root = {}
    stack = [(-1, root)]
    
    keyword_bids = []
    keyword_line_idx = -1
    for i, line in enumerate(lines[:5]):
        m = re.search(r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)$', line)
        if m:
            keyword_bids = m.group(0).split('-')
            keyword_line_idx = i
            break
    
    third_fourth_opening = None
    third_fourth_line_idx = -1
    if not keyword_bids:
        for i, line in enumerate(lines[:5]):
            if re.match(r'第三四家开叫[1-7][HS]', line):
                m = re.search(r'[1-7][HS]', line)
                if m:
                    third_fourth_opening = m.group(0)
                    third_fourth_line_idx = i
                    break
    
    start_line = 0
    if keyword_bids and len(keyword_bids) >= 2:
        start_line = keyword_line_idx + 1
        
        first_keyword = normalize_bid(keyword_bids[0])
        second_keyword = normalize_bid(keyword_bids[1])
        
        root[first_keyword] = {"description": "", "children": {}}
        root[first_keyword]["children"][second_keyword] = {"description": "", "children": {}}
        
        stack = [(-1, root), (-1, root[first_keyword]["children"][second_keyword]["children"])]
    elif third_fourth_opening:
        start_line = third_fourth_line_idx + 1
        
        opening_bid = normalize_bid(third_fourth_opening)
        
        root[opening_bid] = {"description": "", "children": {}}
        
        stack = [(-1, root), (-1, root[opening_bid]["children"])]
    
    for line in lines[start_line:]:
        depth = parse_indent_level(line)
        
        m = re.search(r'[├└]([A-Z0-9NT/]+)', line)
        if not m:
            continue
        
        bids_str = m.group(1)
        
        if '/' in bids_str:
            bids_list = bids_str.split('/')
        else:
            bids_list = [bids_str]
        
        m_desc = re.search(r'：(.+)', line)
        description = m_desc.group(1).strip() if m_desc else ""
        
        for bid in bids_list:
            if re.match(r'^[CDHS]$', bid):
                bid = '3' + bid
            
            bid = normalize_bid(bid)
            
            node = {"description": description, "children": {}}
            
            while stack and stack[-1][0] >= depth:
                stack.pop()
            
            parent = stack[-1][1]
            parent[bid] = node
            stack.append((depth, node["children"]))
    
    if keyword_bids and len(keyword_bids) >= 2:
        return root, keyword_bids
    elif third_fourth_opening:
        return root, [third_fourth_opening]
    
    return root, keyword_bids


def navigate_tree_by_bids(tree: Dict, bids: List[str], start_idx: int = 0) -> Tuple[Optional[Dict], Optional[str]]:
    if not tree or not bids or start_idx >= len(bids):
        return None, None
    
    node = tree
    
    first_keyword = list(tree.keys())[0] if tree else None
    
    if first_keyword:
        first_bid = normalize_bid(bids[0])
        if first_bid == first_keyword:
            node = node.get(first_keyword)
            if node is None:
                return None, None
            
            node = node.get("children", {})
            if node is None:
                return None, None
            
            for i in range(start_idx, len(bids)):
                bid = normalize_bid(bids[i])
                next_node = node.get(bid)
                if next_node is None:
                    break
                if i == len(bids) - 1:
                    return next_node, bid
                node = next_node
                node = node.get("children", {})
                if node is None:
                    break
            
            return None, None
    
    for i in range(start_idx, len(bids)):
        bid = normalize_bid(bids[i])
        next_node = node.get(bid)
        if next_node is None:
            break
        if i == len(bids) - 1:
            return next_node, bid
        node = next_node
        node = node.get("children", {})
        if node is None:
            break
    
    return None, None


def get_subsequent_bids_from_node(node: Dict, content: str = "") -> List[Dict[str, any]]:
    if not node:
        return []
    
    subsequent_bids = []
    
    if "children" in node:
        children = node["children"]
        for bid, child in children.items():
            description = child.get("description", "") if isinstance(child, dict) else ""
            if description:
                import re
                description = re.sub(r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)[：:]\s*', '', description)
            subsequent_bids.append({
                "bid": bid,
                "line": description,
                "indent": 0
            })
    else:
        for bid, child in node.items():
            description = child.get("description", "") if isinstance(child, dict) else ""
            if description:
                import re
                description = re.sub(r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)[：:]\s*', '', description)
            subsequent_bids.append({
                "bid": bid,
                "line": description,
                "indent": 0
            })
    
    return subsequent_bids


def is_opening_keyword(keyword: str) -> bool:
    opening_patterns = [
        r'^花色开叫$',
        r'^\d+\.\d+\s*花色开叫$',
        r'^[1-7](?:[CDHS]|NT)?开叫$',
        r'^\d+\.\d+\s*[1-7](?:[CDHS]|NT)?开叫$',
        r'^开叫$',
    ]
    for pattern in opening_patterns:
        if re.match(pattern, keyword):
            return True
    return False


def is_structural_convention(keyword: str, content: str) -> bool:
    if is_opening_keyword(keyword):
        return True
    
    if re.match(r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)$', keyword):
        return True
    
    if re.match(r'^第三四家开叫[1-7][HS]$', keyword):
        return True
    
    return False


def extract_subsequent_bids(content: str, partner_bid_line_idx: int) -> List[Dict[str, any]]:
    if partner_bid_line_idx < 0:
        return []
    
    lines = content.split('\n')
    if partner_bid_line_idx >= len(lines):
        return []
    
    partner_line = lines[partner_bid_line_idx]
    partner_indent = parse_indent_level(partner_line)
    stripped = partner_line.strip()
    
    is_keyword_line = False
    if partner_indent == 0 and not stripped.startswith('├'):
        bids_in_line = len(re.findall(r'[1-7](?:[CDHS]|NT)', partner_line))
        if bids_in_line >= 2:
            is_keyword_line = True
    
    subsequent_bids = []
    
    if is_keyword_line:
        for i in range(partner_bid_line_idx + 1, len(lines)):
            line = lines[i]
            current_indent = parse_indent_level(line)
            
            if current_indent == 0:
                bid = extract_bid_from_line(line)
                if bid:
                    subsequent_bids.append({
                        "bid": bid,
                        "line": line.strip(),
                        "indent": current_indent
                    })
    else:
        target_indent = partner_indent + 1
        for i in range(partner_bid_line_idx + 1, len(lines)):
            line = lines[i]
            current_indent = parse_indent_level(line)
            
            if current_indent == target_indent:
                bid = extract_bid_from_line(line)
                if bid:
                    subsequent_bids.append({
                        "bid": bid,
                        "line": line.strip(),
                        "indent": current_indent
                    })
            elif current_indent <= partner_indent and line.strip():
                break
    
    return subsequent_bids


def preprocess_jf_content(content: str, bidding_sequence: str, partner_name: str, keyword: str = "") -> Dict[str, any]:
    result = {
        "original_content": content,
        "partner_bid": None,
        "subsequent_bids": [],
        "is_structural_convention": is_structural_convention(keyword, content) if keyword else False
    }
    
    bids_in_sequence = extract_bids_from_sequence(bidding_sequence)
    
    if is_opening_keyword(keyword):
        if not bids_in_sequence:
            subsequent_bids = extract_first_level_bids(content)
            if subsequent_bids:
                result["subsequent_bids"] = subsequent_bids
        else:
            opening_bid = bids_in_sequence[0] if bids_in_sequence else None
            if opening_bid:
                subsequent_bids = extract_response_bids(content, opening_bid)
                if subsequent_bids:
                    result["subsequent_bids"] = subsequent_bids
        return result
    
    if re.match(r'^第三四家开叫[1-7][HS]$', keyword):
        if len(bids_in_sequence) <= 1:
            opening_bid = bids_in_sequence[0] if bids_in_sequence else None
            subsequent_bids = extract_first_level_bids_excluding_opening(content, opening_bid)
            if subsequent_bids:
                result["subsequent_bids"] = subsequent_bids
        else:
            tree, keyword_bids = parse_content_to_tree(content)
            if tree:
                start_idx = 1
                partner_node, partner_bid = navigate_tree_by_bids(tree, bids_in_sequence, start_idx=start_idx)
                if partner_node:
                    result["partner_bid"] = partner_bid
                    subsequent_bids = get_subsequent_bids_from_node(partner_node, content)
                    if subsequent_bids:
                        result["subsequent_bids"] = subsequent_bids
            else:
                partner_bid, partner_line_idx = find_partner_bid_in_tree(content, bids_in_sequence)
                result["partner_bid"] = partner_bid
                if partner_line_idx >= 0:
                    subsequent_bids = extract_subsequent_bids(content, partner_line_idx)
                    if subsequent_bids:
                        result["subsequent_bids"] = subsequent_bids
        return result
    
    if re.match(r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)$', keyword):
        keyword_bids = keyword.split('-')
        keyword_bids_count = len(keyword_bids)
        
        if len(bids_in_sequence) == keyword_bids_count:
            subsequent_bids = extract_first_level_bids(content)
            if subsequent_bids:
                result["subsequent_bids"] = subsequent_bids
                result["partner_bid"] = keyword_bids[-1]
        else:
            tree, tree_keyword_bids = parse_content_to_tree(content)
            if tree:
                start_idx = 0
                if tree_keyword_bids and len(tree_keyword_bids) >= 2:
                    start_idx = 1
                partner_node, partner_bid = navigate_tree_by_bids(tree, bids_in_sequence, start_idx=start_idx)
                if partner_node:
                    result["partner_bid"] = partner_bid
                    subsequent_bids = get_subsequent_bids_from_node(partner_node, content)
                    if subsequent_bids:
                        result["subsequent_bids"] = subsequent_bids
            else:
                partner_bid, partner_line_idx = find_partner_bid_in_tree(content, bids_in_sequence)
                result["partner_bid"] = partner_bid
                if partner_line_idx >= 0:
                    subsequent_bids = extract_subsequent_bids(content, partner_line_idx)
                    if subsequent_bids:
                        result["subsequent_bids"] = subsequent_bids
        return result
    
    return result


def extract_bids_from_sequence(bidding_sequence: str) -> List[str]:
    if not bidding_sequence:
        return []
    
    bids = []
    parts = re.split(r'[-—－]', bidding_sequence)
    for part in parts:
        match = re.search(r'\(?\s*([1-7](?:[CDHS]|NT)?|X{1,2}|pass)\s*\)?', part, re.IGNORECASE)
        if match:
            bid = match.group(1).upper().replace('10', 'T')
            if bid.endswith('N') and len(bid) >= 2 and bid[0].isdigit():
                bid = bid[:-1] + 'NT'
            if bid.lower() != 'pass':
                bids.append(bid)
    return bids


def extract_first_level_bids(content: str) -> List[Dict[str, any]]:
    lines = content.split('\n')
    subsequent_bids = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        if stripped.startswith('-') or stripped.startswith('•'):
            continue
        
        if '：' not in stripped and ':' not in stripped:
            continue
        
        bid = extract_bid_from_line(stripped)
        if bid:
            indent = parse_indent_level(line)
            if indent == 0:
                subsequent_bids.append({
                    "bid": bid,
                    "line": stripped,
                    "indent": indent
                })
    
    return subsequent_bids


def extract_first_level_bids_excluding_opening(content: str, opening_bid: str = None) -> List[Dict[str, any]]:
    lines = content.split('\n')
    subsequent_bids = []
    found_opening = False
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        bid = extract_bid_from_line(stripped)
        if bid:
            indent = parse_indent_level(line)
            if indent == 0:
                if not found_opening and opening_bid and normalize_bid(bid) == normalize_bid(opening_bid):
                    found_opening = True
                    continue
                if found_opening:
                    subsequent_bids.append({
                        "bid": bid,
                        "line": stripped,
                        "indent": indent
                    })
    
    return subsequent_bids


def extract_response_bids(content: str, opening_bid: str) -> List[Dict[str, any]]:
    lines = content.split('\n')
    subsequent_bids = []
    
    opening_pattern = re.escape(opening_bid) + r'[-—－]'
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        if '：' not in stripped and ':' not in stripped:
            continue
        
        match = re.match(opening_pattern + r'\s*([1-7](?:[CDHS]|NT)|X{1,2}|pass)\s*[:：]', stripped, re.IGNORECASE)
        if match:
            response_bid = match.group(1).upper().replace('10', 'T')
            description = re.sub(r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)[：:]\s*', '', stripped)
            subsequent_bids.append({
                "bid": response_bid,
                "line": description,
                "indent": 0
            })
    
    return subsequent_bids


def find_partner_bid_in_tree(content: str, bids: List[str]) -> Tuple[Optional[str], int]:
    if not bids:
        return None, -1
    
    partner_bid = bids[-1]
    lines = content.split('\n')
    
    keyword_line_idx = -1
    keyword_bids_count = 0
    
    for i, line in enumerate(lines[:5]):
        stripped = line.strip()
        if '-' in stripped:
            line_bids = stripped.split('-')
            line_bids = [b.strip() for b in line_bids if b.strip()]
            if len(line_bids) >= 2:
                keyword_line_idx = i
                keyword_bids_count = len(line_bids)
                break
    
    if keyword_line_idx < 0:
        for i, line in enumerate(lines[:5]):
            stripped = line.strip()
            if not stripped:
                continue
            bid_in_line = extract_bid_from_line(stripped)
            if bid_in_line:
                keyword_line_idx = i
                keyword_bids_count = 1
                break
    
    if keyword_line_idx < 0:
        last_occurrence = -1
        for i, line in enumerate(lines):
            bid_in_line = extract_bid_from_line(line)
            if bid_in_line and normalize_bid(bid_in_line) == normalize_bid(partner_bid):
                last_occurrence = i
        return partner_bid, last_occurrence
    
    start_idx = keyword_bids_count
    current_line_idx = keyword_line_idx
    current_indent = 0
    
    for bid_idx in range(start_idx, len(bids)):
        target_bid = bids[bid_idx]
        
        is_first = (bid_idx == start_idx)
        
        found = False
        for i in range(current_line_idx + 1, len(lines)):
            line = lines[i]
            indent = parse_indent_level(line)
            bid_in_line = extract_bid_from_line(line)
            
            if bid_in_line:
                if normalize_bid(bid_in_line) == normalize_bid(target_bid):
                    if is_first:
                        if indent == current_indent:
                            current_line_idx = i
                            current_indent = indent
                            found = True
                            break
                    else:
                        if indent > current_indent:
                            current_line_idx = i
                            current_indent = indent
                            found = True
                            break
        
        if not found:
            break
    
    if current_line_idx > keyword_line_idx:
        return partner_bid, current_line_idx
    
    last_occurrence = -1
    for i, line in enumerate(lines):
        bid_in_line = extract_bid_from_line(line)
        if bid_in_line and normalize_bid(bid_in_line) == normalize_bid(partner_bid):
            last_occurrence = i
    
    return partner_bid, last_occurrence


class JFRetriever:
    def __init__(self, segments: List[Dict[str, str]]):
        self.segments = segments
        self.keyword_index: Dict[str, int] = {}
        self._build_index()
    
    def _build_index(self):
        for i, segment in enumerate(self.segments):
            content = segment["content"]
            lines = content.split("\n")
            
            for j, line in enumerate(lines[:3]):
                line = line.strip()
                if line and line not in self.keyword_index:
                    self.keyword_index[line] = i
    
    def retrieve(self, query: str) -> str:
        if query in self.keyword_index:
            return self.segments[self.keyword_index[query]]["content"]
        
        return ""
    
    def retrieve_with_preprocess(self, query: str, bidding_sequence: str, partner_name: str) -> Dict[str, any]:
        content = self.retrieve(query)
        if not content:
            return {
                "original_content": "",
                "partner_bid": None,
                "subsequent_bids": [],
                "is_structural_convention": False
            }
        
        return preprocess_jf_content(content, bidding_sequence, partner_name, query)
    
    def list_keywords(self) -> List[str]:
        return list(self.keyword_index.keys())
