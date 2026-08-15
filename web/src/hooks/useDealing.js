import { useCallback, useRef, useState } from 'react'
import { dealCards, customDeal, imageDeal, triggerScreenshot, readClipboardDeal, readSingleHandClipboard, uploadSingleHandImage } from '../services/api'
import { setPlayHand as apiSetPlayHand } from '../services/api'
import { BRIDGE_POSITIONS } from '../utils/position'
import { useGame } from '../context/GameContext'
import { useBidding } from '../context/BiddingContext'
import { usePlay } from '../context/PlayContext'

// ── 浏览器直读剪贴板图片（v1.62）──
// 用户截图后剪贴板有图，前端（运行在用户桌面会话里的浏览器）直接读取，
// 绕开"后端读剪贴板"——后端若由沙箱托管，读不到用户桌面的剪贴板（window station 隔离）。
// 返回 File 或 null；剪贴板权限被拒时抛 PERMISSION_DENIED。
const readClipboardImageFromBrowser = async () => {
  try {
    if (!navigator.clipboard?.read) return null
    const items = await navigator.clipboard.read()
    for (const item of items) {
      const imgType = (item.types || []).find(t => t.startsWith('image/'))
      if (!imgType) continue
      const blob = await item.getType(imgType)
      return new File([blob], `clipboard_${Date.now()}.png`, { type: imgType })
    }
    return null
  } catch (err) {
    if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
      throw new Error('PERMISSION_DENIED')
    }
    return null
  }
}

// 图片内容指纹：用于区分"触发截屏前已存在的旧图"与"用户刚截的新图"
const contentKey = async (file) => {
  try {
    const buf = await file.arrayBuffer()
    const arr = new Uint8Array(buf)
    let hash = 0
    for (let i = 0; i < arr.length; i++) hash = (hash * 31 + arr[i]) >>> 0
    return `${hash}:${arr.length}`
  } catch {
    return `${file.size}:${file.name}`
  }
}

// 解析后端返回的叫牌序列字符串为 biddingSequence 数组
// 格式: "(北)pass-(东)pass-(南)1NT-(西)pass-..."
export function parseBiddingSequenceStr(biddingStr) {
  if (!biddingStr) return []
  // 用正则按 "-(位置)" 切分，保留每个叫品单元，避免 "-" 作为 pass 被误切
  // 格式: "(南)1S-(西)pass-(北)-..." 中 "-" 也可能表示 pass
  const items = biddingStr.split(/-(?=\()/).filter(s => s.trim())
  // 花色符号→字母的规范化（统一显示为字母格式）
  const suitSymbolToLetter = { '♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C' }
  const result = []
  let endedByMarker = false
  items.forEach(item => {
    if (endedByMarker) return // "=" 之后的所有叫品一律丢弃（叫牌已结束）
    const match = item.trim().match(/^\(([^)]+)\)(.*)$/)
    if (match) {
      let bid = (match[2] || '').trim()
      // 检测并去除 "=" 叫牌结束标记
      const hasEndMarker = bid.includes('=')
      // 去除 "=" 后再去除首尾的 "-"、"/" 等符号（处理 "pass-"、"pass--"、"-p" 等情况）
      bid = bid.replace(/=/g, '').trim().replace(/^[-/]+|[-/]+$/g, '').trim()
      if (bid === '不叫' || bid === 'Pass' || bid === 'PASS' || bid === 'P' || bid === 'p' || bid === '-' || bid === '/' || bid === '' || bid.toLowerCase() === 'pass') bid = 'pass'
      if (bid === '加倍' || bid === 'Double' || bid === 'D' || bid === 'd') bid = 'X'
      if (bid === '再加倍' || bid === 'Redouble' || bid === 'RD' || bid === 'rd') bid = 'XX'
      // 若原叫品只是"="或符号（去除后为空），按pass处理
      if (hasEndMarker && bid === '') bid = 'pass'
      // 花色符号转字母（如 1♠ → 1S）
      bid = bid.replace(/[♠♥♦♣]/g, sym => suitSymbolToLetter[sym] || sym)
      result.push({ position: match[1], bid })
      if (hasEndMarker) endedByMarker = true
    }
  })

  // 补齐或裁剪结束叫牌的pass：最后一个实质性叫品后必须恰好3个pass
  if (result.length > 0) {
    let lastSubstantiveIdx = -1
    for (let i = result.length - 1; i >= 0; i--) {
      if (result[i].bid !== 'pass') {
        lastSubstantiveIdx = i
        break
      }
    }
    if (lastSubstantiveIdx >= 0) {
      const trailingPasses = result.length - 1 - lastSubstantiveIdx
      if (trailingPasses > 3) {
        result.splice(lastSubstantiveIdx + 4)
      } else if (trailingPasses < 3) {
        const needed = 3 - trailingPasses
        const lastPos = result[result.length - 1].position
        const lastIdx = BRIDGE_POSITIONS.indexOf(lastPos)
        for (let i = 1; i <= needed; i++) {
          result.push({ position: BRIDGE_POSITIONS[(lastIdx + i) % 4], bid: 'pass' })
        }
      }
    }
  }
  return result
}

// 发牌流程 hook：封装发牌/自定义牌局/图片识别/截屏识别/清除手牌
// clearBiddingDraft 由调用方传入（依赖 BIDDING_DRAFT_KEY 等本地逻辑）
export function useDealing({ clearBiddingDraft }) {
  const {
    setHands,
    loading, setLoading,
    setError,
    setWarning,
    dealer, setDealer,
    setVulnerability,
    setPositionRoles,
    setShowPartnerHand,
    setShowOpponentHands,
    setCurrentRecordId,
    setUseFallback,
    setReadonlyMode,
    setImageOpeningLead,
  } = useGame()

  const {
    setBiddingSequence,
    setBidSuggestion,
    setAiBiddingHistory,
    setCurrentBidder,
    setBiddingStarted,
    setStopBidding,
    setPassedAIPositions,
    setShowDoubleDummy,
    setDoubleDummyResult,
    setBiddingHistory,
    setHistoryIndex,
    setOutputFormats,
  } = useBidding()

  const {
    setShowPlayPanel,
    setPlayState,
    setAiPlayHistory,
    setIsPlayPaused,
    setLoadedPlayRecord,
    setLastCompletedTrick,
    setPlayStarted,
    setPlayInitiated,
    setDirectPlayContractInfo,
  } = usePlay()

  const screenshotCancelledRef = useRef(false)
  // P1-7：截屏/识别进度提示（info 样式渲染，与红色 error 区分；完成或取消后清空）
  const [screenshotStatus, setScreenshotStatusState] = useState(null)
  const setScreenshotStatus = useCallback((msg) => {
    setScreenshotStatusState(msg)
  }, [])

  // 公共：识别到完整定约时构造 directPlayContractInfo
  const buildDirectPlayInfo = (data) => {
    if (data.contract_level && data.contract_suit && data.contract_declarer) {
      return {
        level: data.contract_level,
        suit: data.contract_suit,
        declarer: data.contract_declarer,
        isDouble: data.contract_doubled || false,
        isRedouble: data.contract_redoubled || false,
        partnership: ['南', '北'].includes(data.contract_declarer) ? '南北' : '东西',
        bid: `${data.contract_level}${data.contract_suit}${data.contract_doubled ? 'X' : ''}${data.contract_redoubled ? 'X' : ''}`,
      }
    }
    return null
  }

  // 公共：发牌/识别后重置牌局状态
  const resetGameState = useCallback((opts = {}) => {
    const { directPlayInfo = null, imageOpeningLead = null } = opts
    setBiddingSequence([])
    setBidSuggestion(null)
    setAiBiddingHistory([])
    setCurrentBidder(dealer)
    setBiddingStarted(false)
    setStopBidding(false)
    setPassedAIPositions(new Set())
    setUseFallback(false)
    setShowDoubleDummy(false)
    setDoubleDummyResult(null)
    setPositionRoles({ '南': 'ai', '北': 'ai', '东': 'ai', '西': 'ai' })
    setBiddingHistory([])
    setHistoryIndex(-1)
    // 重置打牌相关状态
    setReadonlyMode(false)
    setShowPlayPanel(false)
    setPlayState(null)
    setAiPlayHistory([])
    setIsPlayPaused(false)
    setLoadedPlayRecord(null)
    setLastCompletedTrick(null)
    setDirectPlayContractInfo(directPlayInfo)
    setImageOpeningLead(imageOpeningLead)
  }, [
    dealer, setBiddingSequence, setBidSuggestion, setAiBiddingHistory,
    setCurrentBidder, setBiddingStarted, setStopBidding, setPassedAIPositions,
    setUseFallback, setShowDoubleDummy, setDoubleDummyResult, setPositionRoles,
    setBiddingHistory, setHistoryIndex, setReadonlyMode, setShowPlayPanel,
    setPlayState, setAiPlayHistory, setIsPlayPaused, setLoadedPlayRecord,
    setLastCompletedTrick, setDirectPlayContractInfo, setImageOpeningLead,
  ])

  // 1. 发牌
  const handleDeal = useCallback(async (mode = 'free') => {
    clearBiddingDraft()
    setCurrentRecordId(null)
    setLoading(true)
    setError(null)
    try {
      const data = await dealCards(mode)
      setHands(data.hands)
      resetGameState()
    } catch {
      setError('发牌失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [clearBiddingDraft, setCurrentRecordId, setLoading, setError, setHands, resetGameState])

  // 2. 自定义牌局
  const handleCustomDeal = useCallback(async (inputText) => {
    clearBiddingDraft()
    setCurrentRecordId(null)
    setLoading(true)
    setError(null)
    try {
      const data = await customDeal(inputText)
      if (data.success) {
        setHands(data.hands)
        resetGameState({ imageOpeningLead: data.opening_lead || null })
        return data.hands
      } else {
        setError(data.message || '牌局解析失败')
        return null
      }
    } catch {
      setError('自定义牌局失败，请检查API服务是否正常运行')
      return null
    } finally {
      setLoading(false)
    }
  }, [clearBiddingDraft, setCurrentRecordId, setLoading, setError, setHands, resetGameState])

  // 3. 图片识别牌局
  const handleImageDeal = useCallback(async (imageFile) => {
    clearBiddingDraft()
    setCurrentRecordId(null)
    setLoading(true)
    setError(null)
    setWarning(null)
    try {
      const data = await imageDeal(imageFile)
      if (data.success) {
        setHands(data.hands)
        if (data.message && data.message !== '牌局已加载') setWarning(data.message)
        if (data.dealer) setDealer(data.dealer)
        if (data.vulnerability) setVulnerability(data.vulnerability)
        // 先 reset 再 set，避免 resetGameState 内部清空 biddingSequence
        resetGameState({
          directPlayInfo: buildDirectPlayInfo(data),
          imageOpeningLead: data.opening_lead || null,
        })
        const parsedBidding = parseBiddingSequenceStr(data.bidding_sequence)
        setBiddingSequence(parsedBidding)
        // dealer 已被更新，需要重新设置 currentBidder
        if (data.dealer) setCurrentBidder(data.dealer)
      } else {
        setError(data.message || '图片识别失败')
      }
    } catch {
      setError('图片识别失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [clearBiddingDraft, setCurrentRecordId, setLoading, setError, setWarning,
      setHands, setDealer, setVulnerability, setBiddingSequence, setCurrentBidder, resetGameState])

  // 4. 截屏识别牌局
  const handleScreenshotDeal = useCallback(async ({ setShowSettings = null } = {}) => {
    if (loading) return
    if (setShowSettings) setShowSettings(false)
    setLoading(true)
    screenshotCancelledRef.current = false
    setError(null)
    setScreenshotStatus('请截图：按 Win+Shift+S 选择区域（或等系统截图工具弹出）。首次使用浏览器会询问"允许读取剪贴板"，请允许')
    setWarning(null)
    try {
      // 尝试触发系统截图工具（后端跑在用户桌面时有效；沙箱托管时弹不出，用户手动 Win+Shift+S 即可）
      triggerScreenshot().catch(() => {})
      // 手势内首次读取：触发浏览器剪贴板权限请求，并记录触发前已有的旧图（避免误识别旧内容）
      let prevKey = null
      try {
        const warmFile = await readClipboardImageFromBrowser()
        if (warmFile) prevKey = await contentKey(warmFile)
      } catch {
        // 权限被拒：提示并继续（后端兜底或用户允许后重试）
      }
      // 轮询读取剪贴板：优先浏览器直读（绕开沙箱后端剪贴板隔离），后端接口兜底
      let data = null
      let permissionDenied = false
      for (let i = 0; i < 10; i++) {
        await new Promise(resolve => setTimeout(resolve, 2000))
        if (screenshotCancelledRef.current) {
          setLoading(false)
          return
        }
        // 1) 浏览器直读剪贴板 → 上传识别（image-deal 接口不依赖后端剪贴板）
        try {
          const file = await readClipboardImageFromBrowser()
          if (file) {
            const key = await contentKey(file)
            if (key !== prevKey) {
              const resp = await imageDeal(file)
              if (resp.success) { data = resp; break }
            }
          }
        } catch (err) {
          if (err?.message === 'PERMISSION_DENIED') permissionDenied = true
        }
        // 2) 后端读剪贴板兜底（后端跑在用户桌面时有效）
        if (!data) {
          try {
            const resp = await readClipboardDeal()
            if (resp.success) { data = resp; break }
          } catch {
            // 剪贴板还没有图片，继续等待
          }
        }
        setScreenshotStatus(`等待截屏中... (${i + 1}/10)`)
      }
      if (!data) {
        setScreenshotStatus(null)
        setError(permissionDenied
          ? '浏览器未允许读取剪贴板：请在地址栏右侧点击剪贴板权限并选择"允许"，然后重新截图重试'
          : '截屏识别超时，请确保已完成截图（Win+Shift+S）并重试')
        setLoading(false)
        return
      }
      setHands(data.hands)
      if (data.message && data.message !== '识别成功') setWarning(data.message)
      if (data.dealer) setDealer(data.dealer)
      if (data.vulnerability) setVulnerability(data.vulnerability)
      // 先 reset 再 set，避免 resetGameState 内部清空 biddingSequence
      resetGameState({
        directPlayInfo: buildDirectPlayInfo(data),
        imageOpeningLead: data.opening_lead || null,
      })
      const parsedBidding = parseBiddingSequenceStr(data.bidding_sequence)
      setBiddingSequence(parsedBidding)
      if (data.dealer) setCurrentBidder(data.dealer)
      setScreenshotStatus(null)
    } catch {
      setScreenshotStatus(null)
      setError('截屏识别失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [loading, setLoading, setError, setWarning, setScreenshotStatus, setHands, setDealer, setVulnerability,
      setBiddingSequence, setCurrentBidder, resetGameState])

  // 4b. 单家手牌截屏识别
  const handleSingleHandScreenshot = useCallback(async (position, { setShowSettings = null } = {}) => {
    if (loading) return
    if (!position || !['南','西','北','东'].includes(position)) return
    if (setShowSettings) setShowSettings(false)
    setLoading(true)
    screenshotCancelledRef.current = false
    setError(null)
    setScreenshotStatus(`请截图 ${position} 家手牌：按 Win+Shift+S 选择区域（首次使用浏览器会询问剪贴板权限，请允许）`)
    setWarning(null)
    try {
      // 尝试触发系统截图工具（后端跑在用户桌面时有效；沙箱托管时弹不出，用户手动截图即可）
      triggerScreenshot().catch(() => {})
      // 手势内首次读取：触发权限请求并记录触发前旧图
      let prevKey = null
      try {
        const warmFile = await readClipboardImageFromBrowser()
        if (warmFile) prevKey = await contentKey(warmFile)
      } catch {
        // 权限被拒：继续（后端兜底或用户允许后重试）
      }
      // 轮询：优先浏览器直读 → 上传单家识别；后端接口兜底
      let data = null
      let permissionDenied = false
      for (let i = 0; i < 10; i++) {
        await new Promise(resolve => setTimeout(resolve, 2000))
        if (screenshotCancelledRef.current) {
          setLoading(false)
          return
        }
        try {
          const file = await readClipboardImageFromBrowser()
          if (file) {
            const key = await contentKey(file)
            if (key !== prevKey) {
              const resp = await uploadSingleHandImage(position, file)
              if (resp.success) { data = resp; break }
            }
          }
        } catch (err) {
          if (err?.message === 'PERMISSION_DENIED') permissionDenied = true
        }
        if (!data) {
          try {
            const resp = await readSingleHandClipboard(position)
            if (resp.success) { data = resp; break }
          } catch {
            // 剪贴板还没有图片，继续等待
          }
        }
        setScreenshotStatus(`等待 ${position} 家截屏中... (${i + 1}/10)`)
      }
      if (!data) {
        setScreenshotStatus(null)
        setError(permissionDenied
          ? `浏览器未允许读取剪贴板：请在地址栏右侧点击剪贴板权限并选择"允许"，然后重新截图 ${position} 家重试`
          : `${position} 家截屏识别超时，请确保已完成截图并重试`)
        setLoading(false)
        return
      }
      // 合并更新：只更新目标位置，保留其他三家
      setHands(prev => {
        const prevHand = prev?.[position] || { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 }
        return { ...(prev || {}), [position]: { ...prevHand, ...data.hand } }
      })
      // 同步更新打牌状态（如在打牌阶段），确保 showPlayHandInput 和 AI 自动出牌能正确识别
      try {
        const playResult = await apiSetPlayHand(position, data.hand)
        if (playResult.success && playResult.state) {
          setPlayState(playResult.state)
        }
      } catch {
        // 不在打牌阶段时 API 调用可能失败，忽略即可
      }
      if (data.message && data.message !== '识别成功') setWarning(`${position}家: ${data.message}`)
      setScreenshotStatus(null)
    } catch {
      setScreenshotStatus(null)
      setError(`${position} 家截屏识别失败，请检查API服务是否正常运行`)
    } finally {
      setLoading(false)
    }
  }, [loading, setLoading, setError, setWarning, setScreenshotStatus, setHands, setPlayState])

  // 4c. 单家手牌图片上传识别（移动端/相册路径）
  const handleSingleHandUpload = useCallback(async (position, imageFile) => {
    if (loading) return
    if (!position || !['南','西','北','东'].includes(position)) return
    setLoading(true)
    screenshotCancelledRef.current = false
    setError(null)
    setScreenshotStatus(`正在识别 ${position} 家手牌图片...`)
    setWarning(null)
    try {
      const data = await uploadSingleHandImage(position, imageFile)
      if (!data.success) {
        setError(data.message || '识别失败')
        setLoading(false)
        return
      }
      // 合并更新：只更新目标位置，保留其他三家
      setHands(prev => {
        const prevHand = prev?.[position] || { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 }
        return { ...(prev || {}), [position]: { ...prevHand, ...data.hand } }
      })
      // 同步更新打牌状态（如在打牌阶段），确保 showPlayHandInput 和 AI 自动出牌能正确识别
      try {
        const playResult = await apiSetPlayHand(position, data.hand)
        if (playResult.success && playResult.state) {
          setPlayState(playResult.state)
        }
      } catch {
        // 不在打牌阶段时 API 调用可能失败，忽略即可
      }
      if (data.message && data.message !== '识别成功') setWarning(`${position}家: ${data.message}`)
      setScreenshotStatus(null)
    } catch {
      setScreenshotStatus(null)
      setError(`${position} 家手牌识别失败，请检查API服务是否正常运行`)
    } finally {
      setLoading(false)
    }
  }, [loading, setLoading, setError, setWarning, setScreenshotStatus, setHands, setPlayState])

  // 5. 清除所有手牌
  const clearAllHands = useCallback(() => {
    clearBiddingDraft()
    setHands({
      '南': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '北': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '东': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '西': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
    })
    setCurrentBidder(dealer)
    setBiddingStarted(false)
    setStopBidding(false)
    setBiddingSequence([])
    setAiBiddingHistory([])
    setPassedAIPositions(new Set())
    setOutputFormats(null)
    setShowDoubleDummy(false)
    setDoubleDummyResult(null)
    setBiddingHistory([])
    setHistoryIndex(-1)
    setReadonlyMode(false)
    setShowPlayPanel(false)
    setPlayState(null)
    setAiPlayHistory([])
    setIsPlayPaused(false)
    setPlayStarted(false)
    setPlayInitiated(false)
    setLoadedPlayRecord(null)
    setShowPartnerHand(false)
    setShowOpponentHands(false)
    setDirectPlayContractInfo(null)
    setImageOpeningLead(null)
  }, [clearBiddingDraft, dealer, setHands, setCurrentBidder, setBiddingStarted,
      setStopBidding, setBiddingSequence, setAiBiddingHistory, setPassedAIPositions,
      setOutputFormats, setShowDoubleDummy, setDoubleDummyResult, setBiddingHistory,
      setHistoryIndex, setReadonlyMode, setShowPlayPanel, setPlayState, setAiPlayHistory,
      setIsPlayPaused, setPlayStarted, setPlayInitiated, setLoadedPlayRecord,
      setShowPartnerHand, setShowOpponentHands, setDirectPlayContractInfo, setImageOpeningLead])

  // 取消截屏（P1-7：同时清除进度提示）
  const cancelScreenshot = useCallback(() => {
    screenshotCancelledRef.current = true
    setScreenshotStatusState(null)
    setLoading(false)
  }, [setLoading])

  return {
    handleDeal,
    handleCustomDeal,
    handleImageDeal,
    handleScreenshotDeal,
    handleSingleHandScreenshot,
    handleSingleHandUpload,
    clearAllHands,
    cancelScreenshot,
    parseBiddingSequenceStr,
    screenshotCancelledRef,
    screenshotStatus,
  }
}

export default useDealing
