import axios from 'axios';

const API_BASE_URL = `http://${window.location.hostname}:8003`;

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
});

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
export const analyzeBidding = async (biddingSequence, position = null, dealSystem = '2D/2H/2S：自然阻击') => {
  try {
    const response = await api.post('/api/analyze', {
      bidding_sequence: biddingSequence,
      position,
      deal_system: dealSystem,
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

// 获取AI提供商配置
export const getAIProvider = async () => {
  try {
    const response = await api.get('/api/ai-provider');
    return response.data;
  } catch (error) {
    console.error('获取AI提供商配置失败:', error);
    throw error;
  }
};

// 设置AI提供商
export const setAIProvider = async (aiProvider) => {
  try {
    const response = await api.post('/api/ai-provider', {
      ai_provider: aiProvider
    });
    return response.data;
  } catch (error) {
    console.error('设置AI提供商失败:', error);
    throw error;
  }
};

// AI叫牌
export const aiBid = async (hand, biddingSequence, position, dealSystem = '2D/2H/2S：自然阻击', bidHistory = '', useFallback = false, fallbackModel = null, aiProvider = null) => {
  try {
    const requestData = {
      hand,
      bidding_sequence: biddingSequence,
      position,
      deal_system: dealSystem,
      bid_history: bidHistory,
      use_fallback: useFallback
    };
    
    if (fallbackModel) {
      requestData.fallback_model = fallbackModel;
    }
    
    if (aiProvider) {
      requestData.ai_provider = aiProvider;
    }
    
    const response = await api.post('/api/bid', requestData);
    return response.data;
  } catch (error) {
    console.error('AI叫牌失败:', error);
    throw error;
  }
};

// 人类叫牌 - 获取叫品含义
export const humanBid = async (biddingSequence, position, userInput, dealSystem = '2D/2H/2S：自然阻击') => {
  try {
    const response = await api.post('/api/human-bid', {
      bidding_sequence: biddingSequence,
      position,
      user_input: userInput,
      deal_system: dealSystem
    });
    return response.data;
  } catch (error) {
    console.error('人类叫牌失败:', error);
    throw error;
  }
};

// 获取输出格式（紧凑格式和Deep Finesse格式）
export const getOutputFormats = async (hands, biddingSequence, dealer, gameMode = '四人叫牌', positionRoles = null) => {
  try {
    const response = await api.post('/api/output-formats', {
      hands,
      bidding_sequence: biddingSequence,
      dealer,
      game_mode: gameMode,
      position_roles: positionRoles
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

// 从图片读取牌局
export const imageDeal = async (imageFile) => {
  try {
    const formData = new FormData();
    formData.append('image', imageFile);
    const response = await axios.post(`${API_BASE_URL}/api/image-deal`, formData);
    return response.data;
  } catch (error) {
    console.error('图片识别牌局失败:', error);
    throw error;
  }
};

// 从Edge浏览器截屏读取牌局
export const screenshotDeal = async () => {
  try {
    const response = await api.post('/api/screenshot-deal');
    return response.data;
  } catch (error) {
    console.error('截屏识别牌局失败:', error);
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

// 双明手分析
export const doubleDummyAnalysis = async (hands) => {
  try {
    const response = await api.post('/api/double-dummy', { hands });
    return response.data;
  } catch (error) {
    console.error('双明手分析失败:', error);
    throw error;
  }
};

// ==================== 打牌相关API ====================

// 初始化打牌
export const playInit = async (hands, contract, declarer, playerRoles = null, doubled = false, redoubled = false, biddingSequence = null) => {
  try {
    const response = await api.post('/api/play/init', {
      hands,
      contract,
      declarer,
      player_roles: playerRoles,
      doubled,
      redoubled,
      bidding_sequence: biddingSequence,
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
    const response = await api.post('/api/play/undo');
    return response.data;
  } catch (error) {
    console.error('撤销出牌失败:', error);
    throw error;
  }
};

// AI出牌
export const aiPlay = async (playModel = null) => {
  try {
    const requestData = {
      use_reasoning: playModel === 'deepseek-v4-pro',
    };
    
    if (playModel) {
      requestData.play_model = playModel;
    }
    
    // Reasoner模型需要更长超时（5分钟），Chat模型2分钟
    const timeout = playModel === 'deepseek-v4-pro' ? 300000 : 120000;
    const response = await api.post('/api/play/ai-play', requestData, { timeout });
    return response.data;
  } catch (error) {
    console.error('AI出牌失败:', error);
    throw error;
  }
};

// 更新打牌阶段的玩家角色
export const updatePlayPlayerRoles = async (playerRoles) => {
  try {
    const response = await api.post('/api/play/update-roles', {
      player_roles: playerRoles,
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
    const response = await api.get('/api/play/state');
    return response.data;
  } catch (error) {
    console.error('获取打牌状态失败:', error);
    throw error;
  }
};

export default api;
