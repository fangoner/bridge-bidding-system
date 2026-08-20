import axios from 'axios';

const API_BASE_URL = `http://${window.location.hostname}:8003`;

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── 请求级超时预算（P1-1：前端超时与后端预算对齐）──
// 后端 /api/time-budgets 是唯一数据源；此处兜底值与后端公式保持一致
//（LLM chat 30s/thinking 120s × chat_json 内部 2 次尝试；bid = 主3+备2条链；play = 引擎预算 + LLM 链）
const BUDGET_FALLBACK = {
  bid: { chat: 310, reasoning: 1210 },
  play: {
    llm: { chat: 35, reasoning: 125 },
    mcts: { chat: 15, reasoning: 15 },
    dd: { chat: 35, reasoning: 35 },
    perfect: { chat: 5, reasoning: 5 },
    alphamu: { chat: 126, reasoning: 306 },
    dd_alphamu_llm: { chat: 126, reasoning: 306 },
  },
};
const BUDGET_MARGIN_S = 10; // 预算外网络余量

let timeBudgets = null;
let timeBudgetsPromise = null;

const getTimeBudgets = async () => {
  if (timeBudgets) return timeBudgets;
  if (!timeBudgetsPromise) {
    timeBudgetsPromise = api.get('/api/time-budgets')
      .then((res) => {
        timeBudgets = res.data;
        return timeBudgets;
      })
      .catch((e) => {
        console.warn('获取超时预算失败，使用兜底值:', e?.message);
        return BUDGET_FALLBACK;
      })
      .finally(() => { timeBudgetsPromise = null; });
  }
  return timeBudgetsPromise;
};

// 发牌
export const dealCards = async (mode = 'free') => {
  try {
    const response = await api.post('/api/deal', { mode });
    return response.data;
  } catch (error) {
    console.error('发牌失败:', error);
    throw error;
  }
};

// 分析叫牌序列
export const analyzeBidding = async (biddingSequence, position = null, dealSystem = '2D/2H/2S：自然阻击', bidSystem = 'jf') => {
  try {
    const response = await api.post('/api/analyze', {
      bidding_sequence: biddingSequence,
      position,
      deal_system: dealSystem,
      bid_system: bidSystem,
    });
    return response.data;
  } catch (error) {
    console.error('分析叫牌失败:', error);
    throw error;
  }
};

// 健康检查
export const healthCheck = async () => {
  try {
    const response = await api.get('/api/health');
    return response.data;
  } catch (error) {
    console.error('健康检查失败:', error);
    throw error;
  }
};

// 重新加载约定片段
export const reloadJF = async () => {
  try {
    const response = await api.post('/api/reload-jf');
    return response.data;
  } catch (error) {
    console.error('重新加载约定片段失败:', error);
    throw error;
  }
};

// 获取备用模型配置
export const getFallbackModel = async () => {
  try {
    const response = await api.get('/api/fallback-model');
    return response.data;
  } catch (error) {
    console.error('获取备用模型配置失败:', error);
    throw error;
  }
};

// 设置备用模型
export const setFallbackModel = async (fallbackModel) => {
  try {
    const response = await api.post('/api/fallback-model', {
      fallback_model: fallbackModel
    });
    return response.data;
  } catch (error) {
    console.error('设置备用模型失败:', error);
    throw error;
  }
};

const isAbortError = (e) => e?.name === 'CanceledError' || e?.name === 'AbortError';

// ── 任务化轮询（P0-5）：提交任务 → 短轮询取结果，前端不再受超时限制 ──
// 自适应间隔：快任务（引擎几百ms~几秒）前几次用 300ms 快速探测，避免睡满 2s；
// 长任务逐步放宽到 2s，不增加请求负担
const POLL_INTERVAL_FAST_MS = 300;
const POLL_INTERVAL_SLOW_MS = 2000;

const cancelTaskQuiet = (taskId) => {
  api.post(`/api/tasks/${taskId}/cancel`, {}, { timeout: 5000 }).catch(() => {});
};

const pollTask = async (taskId, { signal, onProgress } = {}) => {
  let pollCount = 0;
  const t0 = performance.now();
  for (;;) {
    let task = null;
    try {
      const res = await api.get(`/api/tasks/${taskId}`, { timeout: 15000, signal });
      task = res.data;
    } catch (e) {
      if (isAbortError(e)) {
        cancelTaskQuiet(taskId);
        throw e;
      }
      if (e?.response?.status === 404) {
        // 任务已消失（后端重启/过期回收）：不可无限重试
        const err = new Error('任务不存在或已过期，后端可能已重启，请重试');
        err.taskError = true;
        throw err;
      }
      // 瞬时轮询失败（网络抖动等）：下一轮重试
    }
    if (task) {
      if (onProgress && task.progress) onProgress(task.progress, task.status);
      if (task.status === 'done') {
        console.log(`[pollTask] ${taskId} done: polls=${pollCount + 1}, wait=${Math.round(performance.now() - t0)}ms`);
        return task.result;
      }
      if (task.status === 'error') {
        const err = new Error(task.error || '任务执行失败');
        err.taskError = true;
        throw err;
      }
      if (task.status === 'cancelled' || task.cancel_requested) {
        cancelTaskQuiet(taskId);
        const err = new Error('canceled');
        err.name = 'AbortError';
        throw err;
      }
    }
    if (signal?.aborted) {
      cancelTaskQuiet(taskId);
      const err = new Error('canceled');
      err.name = 'AbortError';
      throw err;
    }
    // 自适应轮询间隔：前 6 次 300ms 快速探测（快任务几百ms完成，取回延迟从~2s降到~300ms），
    // 之后 1s，超过 ~15 次放宽到 2s（长任务不浪费请求）
    const delayMs = pollCount < 6 ? POLL_INTERVAL_FAST_MS
      : pollCount < 15 ? 1000
      : POLL_INTERVAL_SLOW_MS;
    pollCount += 1;
    await new Promise((r) => setTimeout(r, delayMs));
  }
};

// AI叫牌
export const aiBid = async (hand, biddingSequence, position, dealSystem = '2D/2H/2S：自然阻击', bidHistory = '', useFallback = false, fallbackModel = null, aiProvider = null, useReasoning = false, signal = null, onProgress = null, bidSystem = 'jf') => {
  const requestData = {
    hand,
    bidding_sequence: biddingSequence,
    position,
    deal_system: dealSystem,
    bid_history: bidHistory,
    use_fallback: useFallback,
    use_reasoning: useReasoning,
    bid_system: bidSystem,
  };

  if (fallbackModel) {
    requestData.fallback_model = fallbackModel;
  }

  if (aiProvider) {
    requestData.ai_provider = aiProvider;
  }

  try {
    let submit;
    try {
      submit = await api.post('/api/bid-async', requestData, { timeout: 15000, signal });
    } catch (e) {
      if (isAbortError(e)) throw e;
      if (e?.response?.status === 404) {
        // 旧后端无任务端点：回退同步路径（预算对齐超时，P1-1）
        const budgets = await getTimeBudgets();
        const budgetS = budgets?.bid?.[useReasoning ? 'reasoning' : 'chat'] ?? BUDGET_FALLBACK.bid.chat;
        const config = { timeout: (budgetS + BUDGET_MARGIN_S) * 1000 };
        if (signal) config.signal = signal;
        const response = await api.post('/api/bid', requestData, config);
        return response.data;
      }
      throw e;
    }
    return await pollTask(submit.data.task_id, { signal, onProgress });
  } catch (error) {
    if (isAbortError(error)) {
      throw error; // 用户主动取消，交由调用方处理
    }
    console.error('AI叫牌失败:', error);
    throw error;
  }
};

// 人类叫牌 - 获取叫品含义
export const humanBid = async (biddingSequence, position, userInput, dealSystem = '2D/2H/2S：自然阻击', bidHistory = '', bidSystem = 'jf') => {
  try {
    const response = await api.post('/api/human-bid', {
      bidding_sequence: biddingSequence,
      position,
      user_input: userInput,
      deal_system: dealSystem,
      bid_history: bidHistory,
      bid_system: bidSystem,
    });
    return response.data;
  } catch (error) {
    console.error('人类叫牌失败:', error);
    throw error;
  }
};

// 获取输出格式（紧凑格式和Deep Finesse格式）
export const getOutputFormats = async (hands, biddingSequence, dealer, gameMode = '四人叫牌', positionRoles = null, openingLead = null) => {
  try {
    const response = await api.post('/api/output-formats', {
      hands,
      bidding_sequence: biddingSequence,
      dealer,
      game_mode: gameMode,
      position_roles: positionRoles,
      opening_lead: openingLead,
    });
    return response.data;
  } catch (error) {
    console.error('获取输出格式失败:', error);
    throw error;
  }
};

// 检验定约 - 调用Deep Finesse
export const analyzeContract = async (deepFinesseFormat) => {
  try {
    const response = await api.post('/api/analyze-contract', {
      deep_finesse_format: deepFinesseFormat
    });
    return response.data;
  } catch (error) {
    console.error('检验定约失败:', error);
    throw error;
  }
};

// 自定义牌局
export const customDeal = async (inputText) => {
  try {
    const response = await api.post('/api/custom-deal', {
      input_text: inputText
    });
    return response.data;
  } catch (error) {
    console.error('自定义牌局失败:', error);
    throw error;
  }
};

// 上传类请求：不带 Content-Type（axios 自动为 FormData 设置 multipart boundary），带超时
const apiUpload = axios.create({
  baseURL: API_BASE_URL,
  timeout: 90000,
});

// 从图片读取牌局（P1-7：带超时，避免豆包 Vision 异常时无限等待）
export const imageDeal = async (imageFile) => {
  try {
    const formData = new FormData();
    formData.append('image', imageFile);
    const response = await apiUpload.post('/api/image-deal', formData);
    return response.data;
  } catch (error) {
    console.error('图片识别牌局失败:', error);
    throw error;
  }
};

// 上传单家手牌图片识别（移动端/相册路径）（P1-7：带超时）
export const uploadSingleHandImage = async (position, imageFile, knownHands = null) => {
  try {
    const formData = new FormData();
    formData.append('image', imageFile);
    let url = `/api/single-hand-image?position=${encodeURIComponent(position)}`;
    if (knownHands) url += `&known=${encodeURIComponent(knownHands)}`;
    const response = await apiUpload.post(url, formData);
    return response.data;
  } catch (error) {
    console.error('上传单家手牌识别失败:', error);
    throw error;
  }
};

// 触发系统截屏
export const triggerScreenshot = async () => {
  try {
    const response = await api.post('/api/trigger-screenshot');
    return response.data;
  } catch (error) {
    console.error('触发截屏失败:', error);
    throw error;
  }
};

// 从剪贴板读取截图并识别
export const readClipboardDeal = async () => {
  try {
    const response = await api.post('/api/read-clipboard');
    return response.data;
  } catch (error) {
    console.error('读取剪贴板失败:', error);
    throw error;
  }
};

// 从剪贴板读取截图并识别单家手牌
export const readSingleHandClipboard = async (position, knownHands = null) => {
  try {
    let url = `/api/read-hand-clipboard?position=${encodeURIComponent(position)}`;
    if (knownHands) url += `&known=${encodeURIComponent(knownHands)}`;
    const response = await api.post(url);
    return response.data;
  } catch (error) {
    console.error('单家识别失败:', error);
    throw error;
  }
};

// 上传截图识别叫牌过程（仅叫牌序列+定约，不识别手牌）
export const biddingImageDeal = async (imageFile) => {
  try {
    const formData = new FormData();
    formData.append('image', imageFile);
    const response = await apiUpload.post('/api/bidding-image', formData);
    return response.data;
  } catch (error) {
    console.error('叫牌过程识别失败:', error);
    throw error;
  }
};

// 从剪贴板读取截图识别叫牌过程（后端兜底路径）
export const readBiddingClipboard = async () => {
  try {
    const response = await api.post('/api/read-bidding-clipboard', {}, { timeout: 150000 });
    return response.data;
  } catch (error) {
    console.error('叫牌剪贴板识别失败:', error);
    throw error;
  }
};

// 双明手分析（P1-8：支持 AbortController 取消）
export const doubleDummyAnalysis = async (hands, signal = null) => {
  try {
    const config = { timeout: 180000 };
    if (signal) config.signal = signal;
    const response = await api.post('/api/double-dummy', { hands }, config);
    return response.data;
  } catch (error) {
    if (error.name === 'CanceledError' || error.name === 'AbortError') {
      throw error;
    }
    console.error('双明手分析失败:', error);
    throw error;
  }
};

// ==================== 打牌相关API ====================

// 打牌会话标识：每个浏览器标签页/用户独立一个后端 PlayService 会话，
// 避免多用户/多局并发互相覆盖共享状态（窜牌根因）。
const PLAY_SESSION_ID = `play_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;

// 初始化打牌
export const playInit = async (hands, contract, declarer, playerRoles = null, doubled = false, redoubled = false, biddingSequence = null, bidHistory = '', bidMeanings = '', vulnerability = null, bidSystem = 'jf') => {
  try {
    const response = await api.post('/api/play/init', {
      hands,
      contract,
      declarer,
      player_roles: playerRoles,
      doubled,
      redoubled,
      bidding_sequence: biddingSequence,
      bid_history: bidHistory,
      bid_meanings: bidMeanings,
      vulnerability,
      session_id: PLAY_SESSION_ID,
      bid_system: bidSystem,
    });
    return response.data;
  } catch (error) {
    console.error('初始化打牌失败:', error);
    throw error;
  }
};

// 出牌
export const playCard = async (position, card) => {
  try {
    const response = await api.post('/api/play/card', {
      position,
      card,
      session_id: PLAY_SESSION_ID,
    });
    return response.data;
  } catch (error) {
    console.error('出牌失败:', error);
    throw error;
  }
};

// 撤销出牌
export const undoPlay = async () => {
  try {
    const response = await api.post('/api/play/undo', null, { params: { session_id: PLAY_SESSION_ID } });
    return response.data;
  } catch (error) {
    console.error('撤销出牌失败:', error);
    throw error;
  }
};

// AI出牌
export const aiPlay = async (playModel = null, useReasoning = false, playEngine = null, ddSampleCount = null, signal = null, ddAlphamuSwitchCards = null, useLlmReview = false, ddScoringMode = null, onProgress = null) => {
  const requestData = {
    use_reasoning: useReasoning,
    use_llm_review: useLlmReview,
    session_id: PLAY_SESSION_ID,
  };

  if (playModel) {
    requestData.play_model = playModel;
  }
  if (playEngine) {
    requestData.play_engine = playEngine;
  }
  if (ddSampleCount) {
    requestData.dd_sample_count = ddSampleCount;
  }
  if (ddAlphamuSwitchCards != null) {
    requestData.dd_alphamu_switch_cards = ddAlphamuSwitchCards;
  }
  if (ddScoringMode) {
    requestData.dd_scoring_mode = ddScoringMode;
  }

  try {
    let submit;
    try {
      submit = await api.post('/api/play/ai-play-async', requestData, { timeout: 15000, signal });
    } catch (e) {
      if (isAbortError(e)) throw e;
      if (e?.response?.status === 404) {
        // 旧后端无任务端点：回退同步路径（预算对齐超时，P1-1）
        const budgets = await getTimeBudgets();
        const engineKey = playEngine || 'dd_alphamu_llm';
        const budgetS = budgets?.play?.[engineKey]?.[useReasoning ? 'reasoning' : 'chat']
          ?? BUDGET_FALLBACK.play.dd_alphamu_llm.chat;
        const config = { timeout: (budgetS + BUDGET_MARGIN_S) * 1000, signal };
        const response = await api.post('/api/play/ai-play', requestData, config);
        return response.data;
      }
      throw e;
    }
    return await pollTask(submit.data.task_id, { signal, onProgress });
  } catch (error) {
    if (isAbortError(error)) {
      console.log('[AI Play] 请求已被用户中止')
      throw error
    }
    console.error('AI出牌失败:', error);
    throw error;
  }
};

// 更新打牌阶段的玩家角色
export const updatePlayPlayerRoles = async (playerRoles) => {
  try {
    const response = await api.post('/api/play/update-roles', {
      player_roles: playerRoles,
      session_id: PLAY_SESSION_ID,
    });
    return response.data;
  } catch (error) {
    console.error('更新玩家角色失败:', error);
    throw error;
  }
};

// 获取打牌状态
export const getPlayState = async () => {
  try {
    const response = await api.get('/api/play/state', { params: { session_id: PLAY_SESSION_ID } });
    return response.data;
  } catch (error) {
    console.error('获取打牌状态失败:', error);
    throw error;
  }
};

// 设置打牌阶段的手牌（如首攻后输入明手）
export const setPlayHand = async (position, hand) => {
  try {
    const response = await api.post('/api/play/set-hand', {
      position,
      hand,
      session_id: PLAY_SESSION_ID,
    });
    return response.data;
  } catch (error) {
    console.error('设置手牌失败:', error);
    throw error;
  }
};

// 获取DD出牌提示（完美双明手分析）
export const getDDHints = async (signal = null) => {
  try {
    const config = { params: { session_id: PLAY_SESSION_ID } };
    if (signal) config.signal = signal;
    const response = await api.get('/api/play/dd-hints', config);
    return response.data;
  } catch (error) {
    console.error('获取DD提示失败:', error);
    throw error;
  }
};

// 复盘模式：根据游标位置获取DD提示
export const getDDHintsReview = async (playState, cursor, signal = null) => {
  try {
    const config = signal ? { signal } : {};
    const response = await api.post('/api/play/dd-hints-review', {
      play_state: playState,
      cursor: cursor,
    }, config);
    return response.data;
  } catch (error) {
    console.error('获取复盘DD提示失败:', error);
    throw error;
  }
};

// 获取粒子数设置
export const getParticleSettings = async () => {
  try {
    const response = await api.get('/api/play/particle-settings', { params: { session_id: PLAY_SESSION_ID } });
    return response.data;
  } catch (error) {
    console.error('获取粒子设置失败:', error);
    throw error;
  }
};

// 设置粒子数
export const setParticleSettings = async (settings) => {
  try {
    const response = await api.post('/api/play/particle-settings', { ...settings, session_id: PLAY_SESSION_ID });
    return response.data;
  } catch (error) {
    console.error('设置粒子数失败:', error);
    throw error;
  }
};

export default api;
