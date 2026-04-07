import axios from 'axios';

const API_BASE_URL = 'http://localhost:8003';

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
export const analyzeBidding = async (biddingSequence, position = null) => {
  try {
    const response = await api.post('/api/analyze', {
      bidding_sequence: biddingSequence,
      position,
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

// AI叫牌
export const aiBid = async (hand, biddingSequence, position, dealSystem = '2D/2H/2S：自然阻击', bidHistory = '', useFallback = false, fallbackModel = null) => {
  try {
    const requestData = {
      hand,
      bidding_sequence: biddingSequence,
      position,
      deal_system: dealSystem,
      bid_history: bidHistory,
      use_fallback: useFallback
    };
    
    // 如果指定了备用模型，添加到请求中
    if (fallbackModel) {
      requestData.fallback_model = fallbackModel;
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
export const getOutputFormats = async (hands, biddingSequence, dealer, gameMode = '四人叫牌', humanPosition = null) => {
  try {
    const response = await api.post('/api/output-formats', {
      hands,
      bidding_sequence: biddingSequence,
      dealer,
      game_mode: gameMode,
      human_position: humanPosition
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

export default api;
