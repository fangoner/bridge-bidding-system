"""首攻与信号方案注册表。

提供标准方案（新睿自然 Rev 3.2 第十二章）作为默认实现，
同时预留接口支持扩展其他方案（如反式信号）。
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class LeadScheme:
    """首攻方案：按定约类型和花色牌型给出首攻牌张。"""
    name: str
    nt_lead_rules: str
    trump_lead_rules: str


@dataclass
class SignalScheme:
    """信号方案：姿态/张数/花色偏好信号的定义与使用规则。"""
    name: str
    attitude_rules: str
    count_rules: str
    discard_rules: str


STANDARD_LEAD_NT = """## 无将定约首攻牌张选择（标准方案）

**四张以上长套**：
- 有连张大牌攻大牌（AKQ+攻A，KQJ+攻K）
- 有中间连张攻连张中的大牌，即01攻牌（0或1张比所攻牌大）
  例：KJ1084攻J（0张比J大），AJ105攻J（1张比J大）
- 否则攻长套的第四大的牌（套中有两个连张大牌也如此），即长四首攻
  例：Q107432攻4，AK962攻6

**三张套**：
- 三张带一大牌攻小（A104攻4）
- 三张小牌攻中间张（987攻8）

**双张**：攻大（AK攻K）

**短套助攻**：三张以下短套多为助攻，考虑同伴该花色为长套

**表12-1 无将定约首攻牌张**：
| 攻牌 | 可能的牌张组合 |
|:---:|:---|
| A | AQJ+, AQ+, A, Ax, A+ |
| K | KQJ+, KQ+, Kx, K |
| Q | QJ+, AQJ+, Qx, Q |
| J | J10+, AJ10+, KJ10+, Jx, J |
| 10 | 109+, A109+, K109+, Q109+, 10x, 10 |
| X | HHxX+, HxxX+, Xx, Xxx+, xxx, Xx |
"""

STANDARD_LEAD_TRUMP = """## 有将定约首攻牌张选择（标准方案）

**基本原则**：
- 有连张大牌攻大牌
- 有中间连张攻连张中的大牌（01攻牌）
- 双张小牌攻大
- 攻单张小牌

**长套(>4)首攻**：
- 奇数张攻最小的
- 偶数张攻第3张（即3/5首攻）
- 三张小牌攻中间张

**注意**：
- 一般不从Axx中首攻最小的（保留A控制）
- 一般不从AJ10x中首攻J（保留AJ结构）

**表12-3 有将定约首攻牌张**：
| 攻牌 | 可能的牌张组合 |
|:---:|:---|
| A | AKQJ+, AKQ+, AQ+, AK, A |
| K | KQJ+, AK, KQ, K |
| Q | QJ10+, QJx+, Qx, Q |
| J | J10+, KJ10+, Jx, J |
| 10 | 109+, K109+, Q109+, 10x, 10 |
| X | Kx, Qx, Hx, xHx, Hxx, Hx, xxx, Hxx |
"""

STANDARD_SIGNAL = """## 防守信号（标准方案）

**核心原则**：赢墩是硬约束，信号是赢墩等价组内的软选择。
**绝不能为传信号而损失可能的赢墩。**

### 一、姿态信号（Attitude）
- **大牌欢迎，小牌不欢迎**
- 当同伴攻牌，自己处于第三家：
  - 盖不过第一和二家牌张时，给姿态信号
  - 首攻人出大牌时，给出姿态信号
  - 第一和二家出小牌时，出最大张（连张中小牌）

### 二、张数信号（Count）
- **大小表示偶数张，小大表示奇数张**
- 先大后小 = 偶数张
- 先小后大 = 奇数张
- 大小是**相对自己所持牌张**而言

### 三、花色偏好信号（Suit Preference）
- 特定花色的高低组合暗示偏好
- 高牌 = 偏好高级别花色（♠/♥）
- 低牌 = 偏好低级别花色（♦/♣）

### 四、垫牌
- 垫某花色大号码 = 此花色有大牌
- 可能损失赢墩时，用其他花色小牌间接显示姿态

### 信号使用示例

**无将定约**：
| 首攻出牌 | 自己持牌 | 正确选择 | 说明 |
|:---:|:---:|:---:|:---|
| A | 52 | 2 | 首攻人大牌给姿态信号，非张数信号 |
| A | Q2 | 2 | 欢迎同伴套但出Q可能损失赢墩 |
| K | J876 | 8 | 首攻人通常KQ连张，给欢迎姿态，尽量明确 |
| 5 | KQ32 | 3/Q | 第二家出A→盖不过给姿态3；第二家出小→Q |

**有将定约**：
| 首攻出牌 | 自己持牌 | 正确选择 | 说明 |
|:---:|:---:|:---:|:---|
| A | 52 | 5/2 | 有希望将吃时5（欢迎），否则2 |
| A | J962 | 2 | 不能给6表示张数，给姿态信号 |
| A | Q5 | 5 | Qx特例，出5（出Q显示QJ或单张Q） |
| K | A5 | A/5 | 有希望将吃时A，否则5 |
| 5 | KQJ10 | K/10 | 第二家出A→K；第二家出小→10 |
"""

STANDARD_LEAD_SCHEME = LeadScheme(
    name="标准方案",
    nt_lead_rules=STANDARD_LEAD_NT,
    trump_lead_rules=STANDARD_LEAD_TRUMP,
)

STANDARD_SIGNAL_SCHEME = SignalScheme(
    name="标准方案",
    attitude_rules="""姿态信号：大牌欢迎，小牌不欢迎。
- 同伴攻牌第三家：盖不过时给姿态；首攻人大牌时给姿态；第一二家小时出最大张。""",
    count_rules="""张数信号：大小=偶数张，小大=奇数张。
- 先大后小=偶数，先小后大=奇数，相对自己所持牌张而言。""",
    discard_rules="""垫牌信号：垫某花色大号码=此花色有大牌。
- 可能损失赢墩时，用其他花色小牌间接显示姿态。""",
)

_LEAD_SCHEMES: Dict[str, LeadScheme] = {
    "standard": STANDARD_LEAD_SCHEME,
}

_SIGNAL_SCHEMES: Dict[str, SignalScheme] = {
    "standard": STANDARD_SIGNAL_SCHEME,
}


def lead_scheme(name: str = None) -> LeadScheme:
    """获取首攻方案。name: 方案标识，None时读取config。"""
    if name is None:
        from config import LEAD_SIGNAL_SCHEME
        name = LEAD_SIGNAL_SCHEME
    return _LEAD_SCHEMES.get(name, STANDARD_LEAD_SCHEME)


def signal_scheme(name: str = None) -> SignalScheme:
    """获取信号方案。name: 方案标识，None时读取config。"""
    if name is None:
        from config import LEAD_SIGNAL_SCHEME
        name = LEAD_SIGNAL_SCHEME
    return _SIGNAL_SCHEMES.get(name, STANDARD_SIGNAL_SCHEME)


def register_lead_scheme(name: str, scheme: LeadScheme) -> None:
    """注册自定义首攻方案。"""
    _LEAD_SCHEMES[name] = scheme


def register_signal_scheme(name: str, scheme: SignalScheme) -> None:
    """注册自定义信号方案。"""
    _SIGNAL_SCHEMES[name] = scheme
