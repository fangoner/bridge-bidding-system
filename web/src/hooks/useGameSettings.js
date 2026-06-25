import { useState, useCallback } from 'react'
import { setFallbackModel } from '../services/api'
import { getPartnerPosition } from '../utils/position'

const COLOR_SCHEME_KEY = 'bridge_color_scheme_v2'
const FALLBACK_MODEL_KEY = 'bridge_fallback_model'
const PLAY_MODEL_KEY = 'bridge_play_model'
const BIDDING_REASONING_KEY = 'bridge_bidding_reasoning'
const PLAY_REASONING_KEY = 'bridge_play_reasoning'

function useGameSettings(colorSchemes, defaultScheme) {
  const [gameMode, setGameMode] = useState('four')
  const [dealer, setDealer] = useState('南')
  const [positionRoles, setPositionRoles] = useState({
    '南': 'ai',
    '北': 'ai',
    '东': 'ai',
    '西': 'ai'
  })
  const [showPartnerHand, setShowPartnerHand] = useState(false)

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
      return saved || 'deepseek-v4-flash'
    } catch {
      return 'deepseek-v4-flash'
    }
  })

  const [playModel, setPlayModelState] = useState(() => {
    try {
      const saved = localStorage.getItem(PLAY_MODEL_KEY)
      return saved || 'deepseek-v4-flash'
    } catch {
      return 'deepseek-v4-flash'
    }
  })

  const [biddingReasoning, setBiddingReasoningState] = useState(() => {
    try {
      return localStorage.getItem(BIDDING_REASONING_KEY) === 'true'
    } catch {
      return false
    }
  })

  const [playReasoning, setPlayReasoningState] = useState(() => {
    try {
      return localStorage.getItem(PLAY_REASONING_KEY) === 'true'
    } catch {
      return false
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

  const handlePlayModelChange = useCallback(async (event) => {
    const newModel = event.target.value
    setPlayModelState(newModel)
    localStorage.setItem(PLAY_MODEL_KEY, newModel)
  }, [])

  const handleBiddingReasoningChange = useCallback(async (event) => {
    const on = event.target.checked
    setBiddingReasoningState(on)
    localStorage.setItem(BIDDING_REASONING_KEY, on)
  }, [])

  const handlePlayReasoningChange = useCallback(async (event) => {
    const on = event.target.checked
    setPlayReasoningState(on)
    localStorage.setItem(PLAY_REASONING_KEY, on)
  }, [])

  const handlePositionRoleChange = useCallback((position, role) => {
    setPositionRoles(prev => ({ ...prev, [position]: role }))
  }, [])

  return {
    gameMode,
    setGameMode,
    dealer,
    setDealer,
    positionRoles,
    setPositionRoles,
    showPartnerHand,
    setShowPartnerHand,

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
    playModel,
    biddingReasoning,
    playReasoning,
    handleColorSchemeChange,
    syncFallbackModel,
    handleFallbackModelChange,
    handlePlayModelChange,
    handleBiddingReasoningChange,
    handlePlayReasoningChange,
    getPartnerPosition,
    handlePositionRoleChange,
  }
}

export default useGameSettings
