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
DEFAULT_PLAY_ENGINE = "llm"  # "llm" | "mcts" | "dd" | "hybrid"
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

# 分层引擎 (tiered) 参数
TIERED_CRITICAL_SPREAD_DECLARER = 0.5  # 庄家方：分差≤此值→MCTS不确定→升级LLM
TIERED_CRITICAL_SPREAD_DEFENDER = 0.8  # 防守方：分差≤此值→MCTS不确定→升级LLM（噪声大，阈值更宽）
TIERED_ENDGAME_CARDS = 4               # 每手剩余牌数≤此值进入残局阶段
