import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

# override=True：让 .env 中的配置始终优先于系统/父进程环境变量，
# 避免旧环境变量（如 DEEPSEEK_API_KEY）压过 .env 中的新值
load_dotenv(BASE_DIR / ".env", override=True)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "")
DOUBAO_BASE_URL = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
DOUBAO_VISION_ENDPOINT = os.getenv("DOUBAO_VISION_ENDPOINT", "")

DEEPSEEK_VISION_MODEL = os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-v4-flash-vision-exp")
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "deepseek")
DOUBAO_SEED_2_1_PRO_CHAT_ENDPOINT = os.getenv("DOUBAO_SEED_2_1_PRO_CHAT_ENDPOINT", "")
DOUBAO_SEED_2_1_PRO_REASONING_ENDPOINT = os.getenv("DOUBAO_SEED_2_1_PRO_REASONING_ENDPOINT", "")
DOUBAO_SEED_2_1_TURBO_CHAT_ENDPOINT = os.getenv("DOUBAO_SEED_2_1_TURBO_CHAT_ENDPOINT", "")
DOUBAO_SEED_2_1_TURBO_REASONING_ENDPOINT = os.getenv("DOUBAO_SEED_2_1_TURBO_REASONING_ENDPOINT", "")

JF_CONVENTION_FILE = BASE_DIR / "JF实战_标准自然 - Rev 3.2.docx"

DEFAULT_DEAL_SYSTEM = "自然阻击"

DEEP_FINESSE_PATH = BASE_DIR / "Deep Finesse 2014 v2" / "Deep Finesse.exe"
DEEP_FINESSE_CLI_PATH = BASE_DIR / "Deep Finesse 2014 v2" / "df char mode.exe"

SHOW_FULL_LLM_OUTPUT = True

OUTPUT_MODE_GRAPHIC = "graphic"
OUTPUT_MODE_COMPACT = "compact"
OUTPUT_MODE_DEEP_FINESSE = "deep_finesse"
OUTPUT_MODE_ALL = "all"
DEFAULT_OUTPUT_MODE = OUTPUT_MODE_ALL

FALLBACK_MODEL_CHAT = "deepseek-v4-flash"
FALLBACK_MODEL_REASONER = "deepseek-v4-pro"
DEFAULT_FALLBACK_MODEL = FALLBACK_MODEL_CHAT

MAIN_PROMPT_MODEL_CHAT = "deepseek-v4-flash"
MAIN_PROMPT_MODEL_REASONER = "deepseek-v4-pro"
DEFAULT_MAIN_PROMPT_MODEL = MAIN_PROMPT_MODEL_CHAT

MAIN_PROMPT_TEMPERATURE = 0.2
FALLBACK_PROMPT_TEMPERATURE = 0.5

AI_PROVIDER_DEEPSEEK = "deepseek"
AI_PROVIDER_DOUBAO = "doubao"
DEFAULT_AI_PROVIDER = AI_PROVIDER_DEEPSEEK

# ── 模型名称常量 ──
# DeepSeek
DEEPSEEK_MODEL_FLASH = "deepseek-v4-flash"
DEEPSEEK_MODEL_PRO = "deepseek-v4-pro"
# Doubao Seed
DOUBAO_MODEL_2_1_PRO = "doubao-seed-2.1-pro"
DOUBAO_MODEL_2_1_TURBO = "doubao-seed-2.1-turbo"

# ── 统一模型列表（所有可用模型，不含 ::reasoning 后缀的视为 chat 版）──
_DS_MODELS = [DEEPSEEK_MODEL_FLASH, DEEPSEEK_MODEL_PRO]
_DB_MODELS = [DOUBAO_MODEL_2_1_PRO, DOUBAO_MODEL_2_1_TURBO]
ALL_BASE_MODELS = _DS_MODELS + _DB_MODELS
# 模型对应客户端类型
DOUBAO_MODEL_NAMES = _DB_MODELS  # 这些模型走 DoubaoSeedClient
DEEPSEEK_MODEL_NAMES = _DS_MODELS  # 这些模型走 DeepSeekClient

def is_doubao_model(model_name: str) -> bool:
    """去掉 ::reasoning 后缀后判断是否为豆包模型"""
    base = model_name.replace("::reasoning", "")
    return base in DOUBAO_MODEL_NAMES

def is_reasoning_model(model_name: str) -> bool:
    """模型名是否带思考模式后缀"""
    return "::reasoning" in model_name

def get_base_model(model_name: str) -> str:
    """去除 ::reasoning 后缀得到基础模型名"""
    return model_name.replace("::reasoning", "")

def expand_model_list(base_models: list) -> list:
    """将基础模型名展开为包含 chat/reasoning 两个版本"""
    result = []
    for m in base_models:
        result.append(m)
        result.append(f"{m}::reasoning")
    return result

ALL_MODELS = expand_model_list(ALL_BASE_MODELS)

# MCTS / DD play engine settings
DEFAULT_PLAY_ENGINE = "dd_alphamu_llm"  # 主力引擎；可选 "llm" | "mcts" | "dd" | "perfect" | "alphamu" | "dd_alphamu_llm"
MCTS_SEARCH_MODE = "mcts"  # "mcts" (tree+rollout) | "dd" (pure Monte Carlo + double-dummy)
MCTS_ITERATIONS = 5000
MCTS_TIME_LIMIT = 10.0  # seconds per play decision
MCTS_EXPLORATION_CONSTANT = 1.414
MCTS_MIN_ITERATIONS = 500  # floor for adaptive iteration scaling
ROLLOUT_GREEDY_PROB = 0.80  # probability of heuristic vs random in rollout
DD_NUM_SAMPLES = 200  # DD 引擎默认采样数
DD_MIN_SAMPLES = 15   # floor for adaptive sample scaling
DD_TIME_LIMIT = 30.0  # seconds per DD play decision (30秒预算，允许首攻冷启动)
# DD 决策计分制（全量样本口径）："imp"（期望IMP，考虑宕分/超墩/局况）|
#   "make_rate"（做成率，类似αμ）| "avg_tricks"（平均赢墩，纯MP思路）
DD_SCORING_MODE = "imp"

# DD 样本类别保留开关（默认全保留=不对任何类别过滤，等同原行为）：
#   每世界按"所有候选出牌相对所需墩的情形"分三类：
#     全赢 sure_win  = 所有候选都 ≥ 所需墩
#     全输 sure_lose = 所有候选都 < 所需墩
#     临界 critical  = 有赢有输
#   取消勾选某类 = 将该类世界排除出期望聚合（人工/未来程序根据局面选择组合）
DD_KEEP_SURE_WIN = True
DD_KEEP_CRITICAL = True
DD_KEEP_SURE_LOSE = True

# 飞牌延迟策略（识别到飞牌结构时，尽量先出无关牌拖延，观察分布后再飞）：
#   识别：合并庄家+明手每花色，存在"可飞对象"（缺K/Q/J、有上方控制+下方≥T的飞张、合计≥4张）
#   干预：候选牌按"结构相关"（飞牌花色/烧进手牌）与"无关牌"分类；
#         榜首为结构相关牌且与次优无关牌差距 ≤ 阈值时，改选无关牌拖延。
# 阈值用比值（相对成功率）统一跨计分制：次优/榜首 ≥ FINESSE_DEFER_RATIO 即视为"差距不大"。
FINESSE_DEFER_ENABLE = True          # 总开关
FINESSE_DEFER_RATIO = 0.90           # DD 引擎：次优无关牌相对成功率 ≥ 榜首的 90% 时允许拖延
FINESSE_DEFER_RATIO_ALPHA = 0.80     # αμ 引擎：比值 ≥ 0.80 时允许拖延（≈用户指定的成功率差20%）

# 8飞9砸（通用原则，不限将牌/有将定约）：飞牌花色被"被迫引发"时，
# 联手张数 ≤8 → 出飞张（间张）；≥9 → 出顶张（A/K 砸）。用比值阈值保护，差距大不干预。
FINESSE_EIGHT_NINE_ENABLE = True
FINESSE_EIGHT_NINE_RATIO = 0.95      # 改选牌相对成功率 ≥ 榜首 95% 时才允许按原则改选

# 首攻与信号方案："standard"（标准方案，源自新睿自然）| 预留扩展（如"reverse"反式信号）
LEAD_SIGNAL_SCHEME = "standard"

# DD 残局精确枚举
DD_ENDGAME_CARD_THRESHOLD = 4    # 每手剩余牌数≤此值时触发枚举所有分布
DD_ENDGAME_MAX_ENUMERATIONS = 5000  # 枚举总数超过此值时回退采样

# DD-αμ-LLM 主力引擎：中盘DD与残局αμ的切换分界（每手剩余牌数≤此值切到αμ）
DD_ALPHAMU_SWITCH_CARDS = 8

# LLM 审查触发门槛：αμ阶段 top-1 与 top-2 成功率差达到此值时视为"一边倒"，跳过审查
ALPHAMU_LLM_GAP_CAP = 0.35

# 引擎粒子数/采样数范围（供 API 配置端点校验用）
DD_PARTICLES_MIN = 100
DD_PARTICLES_MAX = 2000
MCTS_PARTICLES_MIN = 300
MCTS_PARTICLES_MAX = 1000
ALPHA_MU_WORLDS_MIN = 10
ALPHA_MU_WORLDS_MAX = 100

# 防守信号参数
SIGNAL_WEIGHT = 1.3      # 信号一致时权重乘数
SIGNAL_PENALTY = 0.7     # 信号不一致时权重乘数
SIGNAL_MIN_RANK = 8      # ≥此值（8=8）视为高牌信号（欢迎）

# αμ 搜索参数（残局多步前瞻，解决 strategy fusion）
ALPHA_MU_ENABLE = True            # 是否启用 αμ 搜索
ALPHA_MU_ENDGAME_CARDS = 8        # 每手剩余牌数≤此值时启用 αμ（残局）
ALPHA_MU_NUM_WORLDS = 20          # possible worlds 数量
ALPHA_MU_M = 2                    # 论文 M 参数：Max 递归层数（M=1 退化为 PIMC，Min 不减 M）
ALPHA_MU_MAX_DEPTH = ALPHA_MU_M   # 兼容旧引用
ALPHA_MU_TIME_LIMIT = 60.0        # 时间限制（秒）
