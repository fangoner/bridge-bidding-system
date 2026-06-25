import { useState, useCallback, useEffect } from 'react'
import { setFallbackModel, healthCheck, reloadJF } from '../services/api'
import { useGame } from '../context/GameContext'

const FALLBACK_MODEL_KEY = 'bridge_fallback_model'
const PLAY_MODEL_KEY = 'bridge_play_model'
const DD_SAMPLE_COUNT_KEY = 'bridge_dd_sample_count'

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

  // 初始同步备用模型（API 状态检查由调用方在合适的时机触发）
  useEffect(() => {
    syncFallbackModel()
  }, [syncFallbackModel])

  return {
    ddSampleCount,
    handleDDSampleCountChange,
    handleFallbackModelChange,
    handlePlayModelChange,
    checkApiStatus,
    handleReloadJF,
    syncFallbackModel,
    parseModelValue,
  }
}

export default useModelSettings
