import { useState, useCallback } from 'react'
import { getFallbackModel, setFallbackModel, getAIProvider, setAIProvider } from '../services/api'

const COLOR_SCHEME_KEY = 'bridge_color_scheme'
const FALLBACK_MODEL_KEY = 'bridge_fallback_model'

function useGameSettings(colorSchemes, defaultScheme) {
  const [gameMode, setGameMode] = useState('four')
  const [dealer, setDealer] = useState('南')
  const [humanPosition, setHumanPosition] = useState(null)
  const [positionRoles, setPositionRoles] = useState({
    '南': 'ai',
    '北': 'ai',
    '东': 'ai',
    '西': 'ai'
  })
  const [showPartnerHand, setShowPartnerHand] = useState(false)
  const [showAIHands, setShowAIHands] = useState(false)
  const [showOpponentHands, setShowOpponentHands] = useState(false)
  const [showAIBiddingOutput, setShowAIBiddingOutput] = useState(true)
  const [useFallback, setUseFallback] = useState(false)
  const [dealMode, setDealMode] = useState('free')
  const [showSettings, setShowSettings] = useState(false)
  const [dealSystem, setDealSystem] = useState('2D/2H/2S：自然阻击')
  
  const [colorSchemeKey, setColorSchemeKey] = useState(() => {
    try {
      const saved = localStorage.getItem(COLOR_SCHEME_KEY)
      return saved && colorSchemes[saved] ? saved : defaultScheme
    } catch {
      return defaultScheme
    }
  })
  const currentColorScheme = colorSchemes[colorSchemeKey]
  
  const [fallbackModel, setFallbackModelState] = useState(() => {
    try {
      const saved = localStorage.getItem(FALLBACK_MODEL_KEY)
      return saved || 'deepseek-chat'
    } catch {
      return 'deepseek-chat'
    }
  })
  
  const [aiProvider, setAIProviderState] = useState(() => {
    try {
      const saved = localStorage.getItem('ai_provider')
      return saved || 'deepseek'
    } catch {
      return 'deepseek'
    }
  })

  const handleColorSchemeChange = useCallback((event) => {
    const newScheme = event.target.value
    setColorSchemeKey(newScheme)
    localStorage.setItem(COLOR_SCHEME_KEY, newScheme)
  }, [])

  const syncFallbackModel = useCallback(async () => {
    try {
      await setFallbackModel(fallbackModel)
    } catch (err) {
      console.error('同步备用模型失败:', err)
    }
  }, [fallbackModel])

  const syncAIProvider = useCallback(async () => {
    try {
      await setAIProvider(aiProvider)
    } catch (err) {
      console.error('同步AI提供商失败:', err)
    }
  }, [aiProvider])

  const handleFallbackModelChange = useCallback(async (event) => {
    const newModel = event.target.value
    setFallbackModelState(newModel)
    localStorage.setItem(FALLBACK_MODEL_KEY, newModel)
    try {
      await setFallbackModel(newModel)
    } catch (err) {
      console.error('设置备用模型失败:', err)
    }
  }, [])

  const handleAIProviderChange = useCallback(async (event) => {
    const newProvider = event.target.value
    setAIProviderState(newProvider)
    localStorage.setItem('ai_provider', newProvider)
    try {
      await setAIProvider(newProvider)
    } catch (err) {
      console.error('设置AI提供商失败:', err)
    }
  }, [])

  const getPartnerPosition = useCallback((position) => {
    const partners = {
      '南': '北',
      '北': '南',
      '东': '西',
      '西': '东'
    }
    return partners[position]
  }, [])

  const handlePositionRoleChange = useCallback((position, role) => {
    setPositionRoles(prev => {
      const newRoles = { ...prev, [position]: role }
      
      const humanPositions = Object.entries(newRoles)
        .filter(([_, r]) => r === 'human')
        .map(([p, _]) => p)
      
      if (humanPositions.length === 0) {
        setHumanPosition(null)
      } else if (humanPositions.length === 1) {
        setHumanPosition(humanPositions[0])
      } else {
        setHumanPosition(humanPositions)
      }
      
      return newRoles
    })
  }, [])

  return {
    gameMode,
    setGameMode,
    dealer,
    setDealer,
    humanPosition,
    setHumanPosition,
    positionRoles,
    setPositionRoles,
    showPartnerHand,
    setShowPartnerHand,
    showAIHands,
    setShowAIHands,
    showOpponentHands,
    setShowOpponentHands,
    showAIBiddingOutput,
    setShowAIBiddingOutput,
    useFallback,
    setUseFallback,
    dealMode,
    setDealMode,
    showSettings,
    setShowSettings,
    dealSystem,
    setDealSystem,
    colorSchemeKey,
    setColorSchemeKey,
    currentColorScheme,
    fallbackModel,
    setFallbackModelState,
    aiProvider,
    setAIProviderState,
    handleColorSchemeChange,
    syncFallbackModel,
    syncAIProvider,
    handleFallbackModelChange,
    handleAIProviderChange,
    getPartnerPosition,
    handlePositionRoleChange,
  }
}

export default useGameSettings
