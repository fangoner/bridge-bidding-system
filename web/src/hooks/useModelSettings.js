import { useState, useCallback, useEffect } from 'react'
import { setFallbackModel, getFallbackModel, healthCheck, reloadJF, getParticleSettings, setParticleSettings } from '../services/api'
import { useGame } from '../context/GameContext'

const FALLBACK_MODEL_KEY = 'bridge_fallback_model'
const PLAY_MODEL_KEY = 'bridge_play_model'
const DD_SAMPLE_COUNT_KEY = 'bridge_dd_sample_count'
const DD_PARTICLES_KEY = 'bridge_dd_particles'
const MCTS_PARTICLES_KEY = 'bridge_mcts_particles'
const ALPHA_MU_PARTICLES_KEY = 'bridge_alpha_mu_particles'
const SWITCH_CARDS_KEY = 'bridge_dd_alphamu_switch_cards'

// 解析组合模型值 "model::reasoning" → { model, reasoning }
export function parseModelValue(value) {
  const parts = (value || 'deepseek-v4-flash').split('::')
  return { model: parts[0], reasoning: parts[1] === 'reasoning' }
}

// 模型配置相关逻辑：备用模型 / 打牌模型 / DD 采样数 / API 状态 / JF 重载
export function useModelSettings() {
  const {
    fallbackModel, setFallbackModelState,
    setPlayModelState,
    setApiStatus,
  } = useGame()

  const [ddSampleCount, setDDSampleCount] = useState(() => {
    try {
      return parseInt(localStorage.getItem(DD_SAMPLE_COUNT_KEY)) || 200
    } catch {
      return 200
    }
  })

  // 从后端获取当前可用的模型列表（只含已配置 endpoint 的）
  const [availableModels, setAvailableModels] = useState([])
  const fetchAvailableModels = useCallback(async () => {
    try {
      const data = await getFallbackModel()
      setAvailableModels(data.available_models || [])
    } catch {
      // 后端不通时保留上次结果
    }
  }, [])

  // 同步备用模型到后端
  const syncFallbackModel = useCallback(async () => {
    try {
      await setFallbackModel(parseModelValue(fallbackModel).model)
    } catch (err) {
      console.error('同步备用模型失败:', err)
    }
  }, [fallbackModel])

  // 处理备用模型变更
  const handleFallbackModelChange = useCallback(async (event) => {
    const newModel = event.target.value
    setFallbackModelState(newModel)
    try { localStorage.setItem(FALLBACK_MODEL_KEY, newModel) } catch {/* empty */}
    try {
      await setFallbackModel(parseModelValue(newModel).model)
    } catch (err) {
      console.error('设置备用模型失败:', err)
    }
  }, [setFallbackModelState])

  const handlePlayModelChange = useCallback((event) => {
    const newModel = event.target.value
    setPlayModelState(newModel)
    try { localStorage.setItem(PLAY_MODEL_KEY, newModel) } catch {/* empty */}
  }, [setPlayModelState])

  const handleDDSampleCountChange = useCallback((value) => {
    const num = parseInt(value) || 200
    setDDSampleCount(num)
    try { localStorage.setItem(DD_SAMPLE_COUNT_KEY, num) } catch {/* empty */}
  }, [])

  // 粒子数状态（按引擎分别配置，localStorage 持久化）
  const [ddParticles, setDDParticles] = useState(() => {
    try { return parseInt(localStorage.getItem(DD_PARTICLES_KEY)) || 200 } catch { return 200 }
  })
  const [ddParticlesRange, setDDParticlesRange] = useState({ min: 100, max: 500 })
  const [mctsParticles, setMCTSParticles] = useState(() => {
    try { return parseInt(localStorage.getItem(MCTS_PARTICLES_KEY)) || 500 } catch { return 500 }
  })
  const [mctsParticlesRange] = useState({ min: 300, max: 1000 })
  const [alphaMuParticles, setAlphaMuParticles] = useState(() => {
    try { return parseInt(localStorage.getItem(ALPHA_MU_PARTICLES_KEY)) || 100 } catch { return 100 }
  }, [])

  const [alphaMuParticlesRange] = useState({ min: 30, max: 500 })

  // DD-αμ-LLM 引擎：中盘DD/残局αμ切换分界（每手剩余牌数≤此值切αμ，0=全程DD，13=全程αμ）
  const [switchCards, setSwitchCards] = useState(() => {
    try {
      const v = parseInt(localStorage.getItem(SWITCH_CARDS_KEY), 10)
      return Number.isNaN(v) ? 8 : v
    } catch { return 8 }
  })
  const [switchCardsRange] = useState({ min: 0, max: 13 })

  const handleSwitchCardsChange = useCallback((value) => {
    const v = parseInt(value, 10)
    const num = Number.isNaN(v) ? 8 : v
    setSwitchCards(num)
    try { localStorage.setItem(SWITCH_CARDS_KEY, num) } catch {/* empty */}
  }, [])

  const handleParticleChange = useCallback((engine, value) => {
    const setters = {
      dd: [setDDParticles, DD_PARTICLES_KEY],
      mcts: [setMCTSParticles, MCTS_PARTICLES_KEY],
      alphaMu: [setAlphaMuParticles, ALPHA_MU_PARTICLES_KEY],
    }
    const [setter, key] = setters[engine]
    if (setter) {
      setter(value)
      try { localStorage.setItem(key, value) } catch {/* empty */}
    }
    // 同步到后端
    const payload = {}
    if (engine === 'dd') payload.dd_particles = value
    if (engine === 'mcts') payload.mcts_particles = value
    if (engine === 'alphaMu') payload.alpha_mu_particles = value
    setParticleSettings(payload).catch(() => {})
  }, [])

  // 启动时同步粒子数范围和当前值到后端
  useEffect(() => {
    getParticleSettings().then(data => {
      if (data) {
        if (data.dd_min) setDDParticlesRange({ min: data.dd_min, max: data.dd_max })
        if (data.mcts_min) setMCTSParticlesRange({ min: data.mcts_min, max: data.mcts_max })
        if (data.alpha_mu_min) setAlphaMuParticlesRange({ min: data.alpha_mu_min, max: data.alpha_mu_max })
      }
    }).catch(() => {})
    // 同步 localStorage 保存的值到后端
    setParticleSettings({
      dd_particles: parseInt(localStorage.getItem(DD_PARTICLES_KEY)) || undefined,
      mcts_particles: parseInt(localStorage.getItem(MCTS_PARTICLES_KEY)) || undefined,
      alpha_mu_particles: parseInt(localStorage.getItem(ALPHA_MU_PARTICLES_KEY)) || undefined,
    }).catch(() => {})
  }, [])

  const checkApiStatus = useCallback(async () => {
    try {
      const status = await healthCheck()
      setApiStatus(status)
    } catch {
      setApiStatus({ error: 'API服务未启动' })
    }
  }, [setApiStatus])

  const handleReloadJF = useCallback(async () => {
    try {
      const result = await reloadJF()
      if (result.status === 'success') {
        setApiStatus({ jf_segments_loaded: result.jf_segments_loaded })
        alert(`约定片段已重新加载，共 ${result.jf_segments_loaded} 条`)
      } else {
        alert('加载失败: ' + result.message)
      }
    } catch (err) {
      alert('加载失败: ' + err.message)
    }
  }, [setApiStatus])

  // 初始同步备用模型 & 拉取可用模型列表
  useEffect(() => {
    syncFallbackModel()
    fetchAvailableModels()
  }, [syncFallbackModel, fetchAvailableModels])

  return {
    ddSampleCount,
    handleDDSampleCountChange,
    handleFallbackModelChange,
    handlePlayModelChange,
    checkApiStatus,
    handleReloadJF,
    syncFallbackModel,
    parseModelValue,
    availableModels,
    fetchAvailableModels,
    // 粒子数
    ddParticles, ddParticlesRange,
    mctsParticles, mctsParticlesRange,
    alphaMuParticles, alphaMuParticlesRange,
    handleParticleChange,
    // DD-αμ-LLM 分界
    switchCards, switchCardsRange,
    handleSwitchCardsChange,
  }
}

export default useModelSettings
