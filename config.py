import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

load_dotenv(BASE_DIR / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "")
DOUBAO_BASE_URL = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
DOUBAO_VISION_ENDPOINT = os.getenv("DOUBAO_VISION_ENDPOINT", "")
DOUBAO_SEED_ENDPOINT = os.getenv("DOUBAO_SEED_ENDPOINT", "")

JF_CONVENTION_FILE = BASE_DIR / "JF实战_标准自然 - Rev 3.2.docx"

DEFAULT_DEAL_SYSTEM = "2D/2H/2S：自然阻击"

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

# MCTS / DD play engine settings
DEFAULT_PLAY_ENGINE = "llm"  # "llm" | "mcts" | "dd" | "tiered" | "perfect"
MCTS_SEARCH_MODE = "mcts"  # "mcts" (tree+rollout) | "dd" (pure Monte Carlo + double-dummy)
MCTS_ITERATIONS = 5000
MCTS_TIME_LIMIT = 10.0  # seconds per play decision
MCTS_EXPLORATION_CONSTANT = 1.414
MCTS_MIN_ITERATIONS = 500  # floor for adaptive iteration scaling
ROLLOUT_GREEDY_PROB = 0.80  # probability of heuristic vs random in rollout
DD_NUM_SAMPLES = 100  # max samples per candidate card for DD search
DD_MIN_SAMPLES = 15   # floor for adaptive sample scaling
DD_TIME_LIMIT = 60.0  # seconds per DD play decision (solve_board is heavy)

# DD 残局精确枚举
DD_ENDGAME_CARD_THRESHOLD = 4    # 每手剩余牌数≤此值时触发枚举所有分布
DD_ENDGAME_MAX_ENUMERATIONS = 5000  # 枚举总数超过此值时回退采样

# Tiered 分层引擎参数
TIERED_CRITICAL_SPREAD_DECLARER = 0.2  # 庄家方：DD候选分差≤此值→升级LLM（MCTS回退路径仍用）
TIERED_CRITICAL_SPREAD_DEFENDER = 0.3  # 防守方：DD候选分差≤此值→升级LLM（MCTS回退路径仍用）
TIERED_ENDGAME_CARDS = 6               # 每手剩余牌数≤此值进入残局精确枚举
TIERED_MIN_SAMPLES = 30                # DD有效样本<此值时不升级（统计不可靠）
TIERED_OVERRIDE_THRESHOLD = 1.5        # LLM选择与DD最优差>此值墩时否决LLM

# Tiered 三信号关键决策检测（DD路径，替代固定阈值）
TIERED_FUSION_SPREAD = 3      # 候选牌 min-max 跨度≥此值 → strategy fusion 信号
TIERED_CLUSTER_SE = 2.0       # 距 #1 N×SE 内视为同一集群
TIERED_TYPICAL_SD = 1.5       # solve_board 赢墩典型标准差，用于动态 SE 估计
TIERED_MCTS_CLUSTER_THRESHOLD = 0.5  # MCTS回退路径固定集群阈值（墩）

# 信念状态跟踪 / 粒子滤波参数
BELIEF_NUM_PARTICLES = 60       # 粒子数（每次DD搜索前生成的假设分布数）
BELIEF_SIGNAL_WEIGHT = 1.3      # 信号一致时权重乘数
BELIEF_SIGNAL_PENALTY = 0.7     # 信号不一致时权重乘数
BELIEF_SIGNAL_MIN_RANK = 8      # ≥此值（8=8）视为高牌信号（欢迎）
BELIEF_ENABLE = True            # 是否启用信念跟踪（False回退到纯随机采样）

# αμ 搜索参数（残局多步前瞻，解决 strategy fusion）
ALPHA_MU_ENABLE = True            # 是否启用 αμ 搜索
ALPHA_MU_ENDGAME_CARDS = 8        # 每手剩余牌数≤此值时启用 αμ（残局）
ALPHA_MU_NUM_WORLDS = 20          # possible worlds 数量（粒子数）
ALPHA_MU_MAX_DEPTH = 4            # 最大搜索深度（Max moves 数）
ALPHA_MU_TIME_LIMIT = 8.0         # 时间限制（秒）
