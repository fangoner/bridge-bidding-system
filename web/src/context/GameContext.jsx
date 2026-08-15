/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState } from 'react'

// Game 域：牌局/手牌/发牌/设置相关状态
export const GameContext = createContext(null)

const FALLBACK_MODEL_KEY = 'bridge_fallback_model'
const PLAY_MODEL_KEY = 'bridge_play_model'
const HUMAN_BID_INTERPRET_KEY = 'bridge_human_bid_interpret'

export function useGame() {
  const ctx = useContext(GameContext)
  if (!ctx) {
    throw new Error('useGame 必须在 <GameProvider> 内部使用')
  }
  return ctx
}

export function GameProvider({ children }) {
  // ── 基础牌局状态 ──
  const [hands, setHands] = useState({
    '南': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
    '北': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
    '东': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
    '西': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
  })
  const [loading, setLoading] = useState(false)
  const [aiThinking, setAiThinking] = useState(false)
  const [aiProgress, setAiProgress] = useState(null) // 任务化轮询的当前阶段文案（叫牌/打牌共用）
  const [error, setError] = useState(null)
  const [warning, setWarning] = useState(null)

  // ── 游戏设置 ──
  const [gameMode, setGameMode] = useState('four') // 'four' 或 'pair'
  const [dealer, setDealer] = useState('南') // 发牌人位置
  const [vulnerability, setVulnerability] = useState('NV') // 局况: 'NV'双无/'NS'南北有局/'EW'东西有局/'All'双有局
  const [practiceDirection, setPracticeDirection] = useState('NS') // 双人模式练习方向
  const [positionRoles, setPositionRoles] = useState({
    '南': 'ai', '北': 'ai', '东': 'ai', '西': 'ai',
  })
  const [showPartnerHand, setShowPartnerHand] = useState(false)
  const [showOpponentHands, setShowOpponentHands] = useState(false)
  const [showAIBiddingOutput, setShowAIBiddingOutput] = useState(true)
  const [useFallback, setUseFallback] = useState(false)
  const [dealMode, setDealMode] = useState('free') // free/game/slam
  const [showSettings, setShowSettings] = useState(false)
  const [dealSystem, setDealSystem] = useState('2D/2H/2S：自然阻击')
  // 人类叫牌时是否调用AI解释该叫品含义（关闭可显著加快叫牌速度）
  const [humanBidInterpret, setHumanBidInterpret] = useState(() => {
    try {
      const v = localStorage.getItem(HUMAN_BID_INTERPRET_KEY)
      return v === null ? true : v === 'true'
    } catch {
      return true
    }
  })

  // ── 模型配置（localStorage 持久化）──
  const [fallbackModel, setFallbackModelState] = useState(() => {
    try {
      return localStorage.getItem(FALLBACK_MODEL_KEY) || 'deepseek-v4-flash'
    } catch {
      return 'deepseek-v4-flash'
    }
  })
  const [playModel, setPlayModelState] = useState(() => {
    try {
      return localStorage.getItem(PLAY_MODEL_KEY) || 'deepseek-v4-flash'
    } catch {
      return 'deepseek-v4-flash'
    }
  })

  // ── 牌局杂项 ──
  const [apiStatus, setApiStatus] = useState(null)
  const [currentRecordId, setCurrentRecordId] = useState(null)
  const [showDraftBanner, setShowDraftBanner] = useState(false)
  const [customDealOpen, setCustomDealOpen] = useState(false)
  const [imageDealOpen, setImageDealOpen] = useState(false)
  const [imagePath, setImagePath] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [imageOpeningLead, setImageOpeningLead] = useState(null)
  const [mode, setMode] = useState('practice') // 'practice' | 'simulated'
  const [readonlyMode, setReadonlyMode] = useState(false)

  // 人类叫牌AI解释开关持久化
  useEffect(() => {
    try { localStorage.setItem(HUMAN_BID_INTERPRET_KEY, String(humanBidInterpret)) } catch {/* empty */}
  }, [humanBidInterpret])

  const value = useMemo(
    () => ({
      hands, setHands,
      loading, setLoading,
      aiThinking, setAiThinking,
      aiProgress, setAiProgress,
      error, setError,
      warning, setWarning,
      gameMode, setGameMode,
      dealer, setDealer,
      vulnerability, setVulnerability,
      practiceDirection, setPracticeDirection,
      positionRoles, setPositionRoles,
      showPartnerHand, setShowPartnerHand,
      showOpponentHands, setShowOpponentHands,
      showAIBiddingOutput, setShowAIBiddingOutput,
      useFallback, setUseFallback,
      dealMode, setDealMode,
      showSettings, setShowSettings,
      dealSystem, setDealSystem,
      humanBidInterpret, setHumanBidInterpret,
      fallbackModel, setFallbackModelState,
      playModel, setPlayModelState,
      apiStatus, setApiStatus,
      currentRecordId, setCurrentRecordId,
      showDraftBanner, setShowDraftBanner,
      customDealOpen, setCustomDealOpen,
      imageDealOpen, setImageDealOpen,
      imagePath, setImagePath,
      imageFile, setImageFile,
      imageOpeningLead, setImageOpeningLead,
      mode, setMode,
      readonlyMode, setReadonlyMode,
    }),
    [
      hands, loading, aiThinking, aiProgress, error, warning,
      gameMode, dealer, vulnerability, practiceDirection, positionRoles,
      showPartnerHand, showOpponentHands, showAIBiddingOutput, useFallback,
      dealMode, showSettings, dealSystem,
      humanBidInterpret,
      fallbackModel, playModel,
      apiStatus, currentRecordId, showDraftBanner,
      customDealOpen, imageDealOpen, imagePath, imageFile,
      imageOpeningLead, mode, readonlyMode,
    ],
  )

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>
}
