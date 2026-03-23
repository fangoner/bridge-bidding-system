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

// AI叫牌
export const aiBid = async (hand, biddingSequence, position, dealSystem = '2D/2H/2S：自然阻击', bidHistory = '', useFallback = false) => {
  try {
    const response = await api.post('/api/bid', {
      hand,
      bidding_sequence: biddingSequence,
      position,
      deal_system: dealSystem,
      bid_history: bidHistory,
      use_fallback: useFallback
    });
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
export const imageDeal = async (imagePath) => {
  try {
    const response = await api.post('/api/image-deal', {
      image_path: imagePath
    });
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
