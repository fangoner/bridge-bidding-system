import { useState, useCallback, useEffect, useRef } from 'react'
import { setFallbackModel, getFallbackModel, healthCheck, reloadJF, getParticleSettings, setParticleSettings, getVisionProvider, setVisionProvider, setDdWorldFilter, setDdFinesseEnable, setDdFinesseDelta } from '../services/api'
import { useGame } from '../context/GameContext'

const FALLBACK_MODEL_KEY = 'bridge_fallback_model'
const PLAY_MODEL_KEY = 'bridge_play_model'
const DD_SAMPLE_COUNT_KEY = 'bridge_dd_sample_count'
const DD_PARTICLES_KEY = 'bridge_dd_particles'
const ALPHA_MU_PARTICLES_KEY = 'bridge_alpha_mu_particles'
const ALPHA_MU_M_KEY = 'bridge_alpha_mu_m'
const DD_SCORING_MODE_KEY = 'bridge_dd_scoring_mode'
const DD_KEEP_WIN_KEY = 'bridge_dd_keep_sure_win'
const DD_KEEP_CRIT_KEY = 'bridge_dd_keep_critical'
const DD_KEEP_LOSE_KEY = 'bridge_dd_keep_sure_lose'
const DD_FINESSE_ENABLE_KEY = 'bridge_dd_finesse_enable'
const DD_FINESSE_DELTA_KEY = 'bridge_dd_finesse_delta'
const DD_FINESSE_DELTA_DEFAULT = 0.4
const VISION_PROVIDER_KEY = 'bridge_vision_provider'

// 解析组合模型值 "model::reasoning" → { model, reasoning }
export function parseModelValue(value) {
  const parts = (value || 'deepseek-flash').split('::')
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
      return parseInt(localStorage.getItem(DD_SAMPLE_COUNT_KEY)) || 250
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

  // 滑块拖动会连续触发 onChange，后端持久化做 debounce，避免拖动卡顿
  const particleSyncTimer = useRef(null)
  const scheduleParticleSync = useCallback((payload) => {
    if (particleSyncTimer.current) clearTimeout(particleSyncTimer.current)
    particleSyncTimer.current = setTimeout(() => {
      setParticleSettings(payload).catch(() => {})
    }, 300)
  }, [])

  const handleDDSampleCountChange = useCallback((value) => {
    const num = parseInt(value) || 250
    setDDSampleCount(num)
    try { localStorage.setItem(DD_SAMPLE_COUNT_KEY, num) } catch {/* empty */}
    // 全局DD样本数同步到后端，持久作用于 DD 引擎
    scheduleParticleSync({ dd_particles: num })
  }, [scheduleParticleSync])

  // 粒子数状态（按引擎分别配置，localStorage 持久化）
  const [ddParticles, setDDParticles] = useState(() => {
    try { return parseInt(localStorage.getItem(DD_PARTICLES_KEY)) || 200 } catch { return 200 }
  })
  const [ddParticlesRange, setDDParticlesRange] = useState({ min: 100, max: 500 })
  const [alphaMuParticles, setAlphaMuParticles] = useState(() => {
    try { return parseInt(localStorage.getItem(ALPHA_MU_PARTICLES_KEY)) || 100 } catch { return 100 }
  }, [])

  const [alphaMuParticlesRange, setAlphaMuParticlesRange] = useState({ min: 10, max: 100 })

  // DD 决策计分制（localStorage 持久化），随 aiPlay 请求下发到后端 DD 引擎
  const [ddScoringMode, setDdScoringMode] = useState(() => {
    try { return localStorage.getItem(DD_SCORING_MODE_KEY) || 'imp' } catch { return 'imp' }
  })
  const handleDdScoringModeChange = useCallback((value) => {
    const v = ['imp', 'make_rate', 'avg_tricks'].includes(value) ? value : 'imp'
    setDdScoringMode(v)
    try { localStorage.setItem(DD_SCORING_MODE_KEY, v) } catch {/* empty */}
  }, [])

  // DD 样本类别保留开关（全赢/临界/全输，独立可多选；localStorage 缓存 + 启动时推送后端）
  const loadKeep = (key) => {
    try { return localStorage.getItem(key) !== 'false' } catch { return true }
  }
  const [keepSureWin, setKeepSureWin] = useState(() => loadKeep(DD_KEEP_WIN_KEY))
  const [keepCritical, setKeepCritical] = useState(() => loadKeep(DD_KEEP_CRIT_KEY))
  const [keepSureLose, setKeepSureLose] = useState(() => loadKeep(DD_KEEP_LOSE_KEY))
  const syncDdWorldFilter = useCallback(async () => {
    const payload = {
      keep_sure_win: loadKeep(DD_KEEP_WIN_KEY),
      keep_critical: loadKeep(DD_KEEP_CRIT_KEY),
      keep_sure_lose: loadKeep(DD_KEEP_LOSE_KEY),
    }
    try { await setDdWorldFilter(payload) } catch {/* empty */}
  }, [])
  const handleKeepClassChange = useCallback(async (cls, enabled) => {
    const setters = {
      win: [setKeepSureWin, DD_KEEP_WIN_KEY],
      critical: [setKeepCritical, DD_KEEP_CRIT_KEY],
      lose: [setKeepSureLose, DD_KEEP_LOSE_KEY],
    }
    const [setter, key] = setters[cls]
    setter(enabled)
    try { localStorage.setItem(key, enabled ? 'true' : 'false') } catch {/* empty */}
    try {
      await setDdWorldFilter({
        keep_sure_win: cls === 'win' ? enabled : undefined,
        keep_critical: cls === 'critical' ? enabled : undefined,
        keep_sure_lose: cls === 'lose' ? enabled : undefined,
      })
    } catch (err) {
      console.error('设置DD样本类别开关失败:', err)
    }
  }, [])

  // DD 引擎飞牌管理开关（localStorage 持久化 + 启动时推送后端；运行时即时生效）
  const [ddFinesseEnable, setDdFinesseEnableState] = useState(() => loadKeep(DD_FINESSE_ENABLE_KEY))
  const handleDdFinesseChange = useCallback(async (enabled) => {
    setDdFinesseEnableState(enabled)
    try { localStorage.setItem(DD_FINESSE_ENABLE_KEY, enabled ? 'true' : 'false') } catch {/* empty */}
    try {
      await setDdFinesseEnable(enabled)
    } catch (err) {
      console.error('设置DD飞牌管理开关失败:', err)
    }
  }, [])

  // DD 探针 Δ 阈值（localStorage 持久化 + 启动时同步后端；运行时即时生效）
  const [ddFinesseDelta, setDdFinesseDeltaState] = useState(() => {
    try {
      const v = Number(localStorage.getItem(DD_FINESSE_DELTA_KEY))
      if (!Number.isNaN(v) && v >= 0.2 && v <= 0.5) return v
    } catch {/* empty */}
    return DD_FINESSE_DELTA_DEFAULT
  })
  const handleDdFinesseDeltaChange = useCallback(async (delta) => {
    const clamped = Math.min(0.5, Math.max(0.2, Math.round(delta * 100) / 100))
    setDdFinesseDeltaState(clamped)
    try { localStorage.setItem(DD_FINESSE_DELTA_KEY, String(clamped)) } catch {/* empty */}
    try {
      await setDdFinesseDelta(clamped)
    } catch (err) {
      console.error('设置DD探针Δ阈值失败:', err)
    }
  }, [])

  // 视觉识别模型 provider（截屏/图片识别）；localStorage 持久化 + 启动时同步到后端
  const [visionProvider, setVisionProviderState] = useState(() => {
    try { return localStorage.getItem(VISION_PROVIDER_KEY) || 'deepseek' } catch { return 'deepseek' }
  })
  const [visionProviders, setVisionProviders] = useState([])
  const fetchVisionProvider = useCallback(async () => {
    try {
      const data = await getVisionProvider()
      setVisionProviders(data.available_providers || [])
    } catch {/* empty */}
  }, [])
  const syncVisionProvider = useCallback(async () => {
    try { await setVisionProvider(visionProvider) } catch {/* empty */}
  }, [visionProvider])
  const handleVisionProviderChange = useCallback(async (event) => {
    const newProvider = event.target.value
    setVisionProviderState(newProvider)
    try { localStorage.setItem(VISION_PROVIDER_KEY, newProvider) } catch {/* empty */}
    try {
      await setVisionProvider(newProvider)
    } catch (err) {
      console.error('切换视觉模型失败:', err)
    }
  }, [])

  const handleParticleChange = useCallback((engine, value) => {
    const setters = {
      dd: [setDDParticles, DD_PARTICLES_KEY],
      alphaMu: [setAlphaMuParticles, ALPHA_MU_PARTICLES_KEY],
    }
    const [setter, key] = setters[engine]
    if (setter) {
      setter(value)
      try { localStorage.setItem(key, value) } catch {/* empty */}
    }
    // 同步到后端（debounce）
    const payload = {}
    if (engine === 'dd') payload.dd_particles = value
    if (engine === 'alphaMu') payload.alpha_mu_particles = value
    scheduleParticleSync(payload)
  }, [scheduleParticleSync])

  // αμ 层数 M（Max 递归层数，M=1 退化为 PIMC；localStorage 持久化 + 后端实时生效）
  const [alphaMuM, setAlphaMuM] = useState(() => {
    try {
      const v = parseInt(localStorage.getItem(ALPHA_MU_M_KEY), 10)
      return Number.isNaN(v) ? 2 : v
    } catch { return 2 }
  })
  const [alphaMuMRange, setAlphaMuMRange] = useState({ min: 1, max: 3 })

  const handleAlphaMuMChange = useCallback((value) => {
    const v = parseInt(value, 10)
    const num = Number.isNaN(v) ? 2 : v
    setAlphaMuM(num)
    try { localStorage.setItem(ALPHA_MU_M_KEY, num) } catch {/* empty */}
    scheduleParticleSync({ alpha_mu_m: num })
  }, [scheduleParticleSync])

  // 启动时同步粒子数范围和当前值到后端
  useEffect(() => {
    getParticleSettings().then(data => {
      if (data) {
        if (data.dd_min) setDDParticlesRange({ min: data.dd_min, max: data.dd_max })
        if (data.alpha_mu_min) setAlphaMuParticlesRange({ min: data.alpha_mu_min, max: data.alpha_mu_max })
        if (data.alpha_mu_m_min) setAlphaMuMRange({ min: data.alpha_mu_m_min, max: data.alpha_mu_m_max })
      }
    }).catch(() => {})
    // 同步 localStorage 保存的值到后端
    setParticleSettings({
      dd_particles: parseInt(localStorage.getItem(DD_SAMPLE_COUNT_KEY)) || undefined,
      alpha_mu_particles: parseInt(localStorage.getItem(ALPHA_MU_PARTICLES_KEY)) || undefined,
      alpha_mu_m: parseInt(localStorage.getItem(ALPHA_MU_M_KEY)) || undefined,
    }).catch(() => {})
    // 以前端 localStorage 为准推送样本类别开关到后端
    syncDdWorldFilter()
    // 同步 DD 飞牌管理开关到后端
    setDdFinesseEnable(loadKeep(DD_FINESSE_ENABLE_KEY)).catch(() => {})
    // 同步 DD 探针 Δ 阈值到后端（前端 localStorage 为准）
    const storedDelta = (() => {
      try {
        const v = Number(localStorage.getItem(DD_FINESSE_DELTA_KEY))
        if (!Number.isNaN(v) && v >= 0.2 && v <= 0.5) return v
      } catch {/* empty */}
      return DD_FINESSE_DELTA_DEFAULT
    })()
    setDdFinesseDelta(storedDelta).catch(() => {})
  }, [syncDdWorldFilter])

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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetchAvailableModels 为 async，setState 在 await 后异步触发
    fetchAvailableModels()
  }, [syncFallbackModel, fetchAvailableModels])

  // 初始同步视觉模型 provider & 拉取可用列表（后端 config 中 VISION_PROVIDER 与前端 localStorage 可能不一致，以 localStorage 为准推送给后端）
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetchVisionProvider 为 async，setState 在 await 后异步触发
    fetchVisionProvider()
    syncVisionProvider()
  }, [fetchVisionProvider, syncVisionProvider])

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
    alphaMuParticles, alphaMuParticlesRange,
    handleParticleChange,
    // αμ 层数 M
    alphaMuM, alphaMuMRange,
    handleAlphaMuMChange,
    // DD 决策计分制
    ddScoringMode,
    handleDdScoringModeChange,
    // DD 样本类别保留开关（全赢/临界/全输）
    keepSureWin, keepCritical, keepSureLose,
    handleKeepClassChange,
    // DD 引擎飞牌管理开关
    ddFinesseEnable,
    handleDdFinesseChange,
    // DD 探针 Δ 阈值
    ddFinesseDelta,
    handleDdFinesseDeltaChange,
    // 视觉识别模型 provider
    visionProvider,
    visionProviders,
    handleVisionProviderChange,
    fetchVisionProvider,
  }
}

export default useModelSettings
