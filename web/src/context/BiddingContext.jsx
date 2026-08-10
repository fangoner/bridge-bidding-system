/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useMemo, useState } from 'react'
import useBiddingState from '../hooks/useBiddingState'

// Bidding 域：叫牌序列/历史/分析相关状态
export const BiddingContext = createContext(null)

export function useBidding() {
  const ctx = useContext(BiddingContext)
  if (!ctx) {
    throw new Error('useBidding 必须在 <BiddingProvider> 内部使用')
  }
  return ctx
}

export function BiddingProvider({ children }) {
  // ── 叫牌核心状态（复用现有 hook）──
  const biddingState = useBiddingState()

  // ── 叫牌回退历史 ──
  const [biddingHistory, setBiddingHistory] = useState([])
  const [historyIndex, setHistoryIndex] = useState(-1)

  // ── 叫牌编辑/对话框 ──
  const [showEditBiddingDialog, setShowEditBiddingDialog] = useState(false)

  // ── 输出格式 / 定约分析 ──
  const [showMoreFormats, setShowMoreFormats] = useState(false)
  const [outputFormats, setOutputFormats] = useState(null)
  const [outputFormatsLoading, setOutputFormatsLoading] = useState(false)
  const [analyzeLoading, setAnalyzeLoading] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState(null)

  // ── 双明手分析 ──
  const [showDoubleDummy, setShowDoubleDummy] = useState(false)
  const [doubleDummyResult, setDoubleDummyResult] = useState(null)
  const [doubleDummyLoading, setDoubleDummyLoading] = useState(false)

  const value = useMemo(
    () => ({
      ...biddingState,
      biddingHistory, setBiddingHistory,
      historyIndex, setHistoryIndex,
      showEditBiddingDialog, setShowEditBiddingDialog,
      showMoreFormats, setShowMoreFormats,
      outputFormats, setOutputFormats,
      outputFormatsLoading, setOutputFormatsLoading,
      analyzeLoading, setAnalyzeLoading,
      analyzeResult, setAnalyzeResult,
      showDoubleDummy, setShowDoubleDummy,
      doubleDummyResult, setDoubleDummyResult,
      doubleDummyLoading, setDoubleDummyLoading,
    }),
    [
      biddingState, biddingHistory, historyIndex,
      showEditBiddingDialog,
      showMoreFormats, outputFormats, outputFormatsLoading,
      analyzeLoading, analyzeResult,
      showDoubleDummy, doubleDummyResult, doubleDummyLoading,
    ],
  )

  return <BiddingContext.Provider value={value}>{children}</BiddingContext.Provider>
}
