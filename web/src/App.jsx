import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Container,
  Typography,
  Button,
  Box,
  Paper,
  Alert,
  CircularProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormControlLabel,
  Checkbox,
  Switch,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Divider,
  Badge,
  ToggleButtonGroup,
  ToggleButton,
  Tooltip,
  useTheme,
  useMediaQuery
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import HistoryIcon from '@mui/icons-material/History'
import { dealCards, healthCheck, aiBid, analyzeBidding, humanBid, getOutputFormats, analyzeContract, reloadJF, customDeal, imageDeal, triggerScreenshot, readClipboardDeal, doubleDummyAnalysis, getFallbackModel, setFallbackModel, getAIProvider, setAIProvider, playInit, playCard, aiPlay, getPlayState, updatePlayPlayerRoles } from './services/api'
import HandDisplay from './components/HandDisplay'
import ControlButtons from './components/ControlButtons'
import BiddingDetailPanel from './components/BiddingDetailPanel'
import CardTablePanel from './components/CardTablePanel'
import SettingsPanel from './components/SettingsPanel'
import PlayPanel from './components/PlayPanel'
import PlayDetailPanel from './components/PlayDetailPanel'
import { colorSchemes, defaultScheme } from './theme/colorSchemes'
import './App.css'

const BIDDING_RECORDS_KEY = 'bridge_bidding_records'
const COLOR_SCHEME_KEY = 'bridge_color_scheme'
const FALLBACK_MODEL_KEY = 'bridge_fallback_model'

function App() {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))
  
  const isLoadingRecordRef = useRef(false) // 用于标记是否正在加载历史记录（不触发保存）
  const [hands, setHands] = useState({
    '南': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
    '北': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
    '东': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
    '西': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 }
  })
  const [loading, setLoading] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [suggestionLoading, setSuggestionLoading] = useState(false)
  const [error, setError] = useState(null)
  const [apiStatus, setApiStatus] = useState(null)
  const [biddingSequence, setBiddingSequence] = useState([])
  const [currentBidder, setCurrentBidder] = useState('南')
  const [bidSuggestion, setBidSuggestion] = useState(null)
  const [aiBiddingHistory, setAiBiddingHistory] = useState([]) // AI叫牌历史记录
  const [currentBiddingPosition, setCurrentBiddingPosition] = useState(null) // 当前正在叫牌的位置
  const [selectedBiddingIndex, setSelectedBiddingIndex] = useState(-1) // 选择的叫牌记录索引，-1表示最新
  const [simpleDisplayMode, setSimpleDisplayMode] = useState(false) // 简单显示模式
  const [showBiddingControls, setShowBiddingControls] = useState(false) // 右侧面板显示叫牌控制+JF片段
  const [dealSystem, setDealSystem] = useState('2D/2H/2S：自然阻击') // 阻击叫牌体系
  
  // 叫牌回退历史
  const [biddingHistory, setBiddingHistory] = useState([]) // 历史快照列表
  const [historyIndex, setHistoryIndex] = useState(-1) // 当前历史位置
  
  // 配色方案
  const [colorSchemeKey, setColorSchemeKey] = useState(() => {
    try {
      const saved = localStorage.getItem(COLOR_SCHEME_KEY)
      return saved && colorSchemes[saved] ? saved : defaultScheme
    } catch {
      return defaultScheme
    }
  })
  const currentColorScheme = colorSchemes[colorSchemeKey]
  
  const handleColorSchemeChange = (event) => {
    const newScheme = event.target.value
    setColorSchemeKey(newScheme)
    localStorage.setItem(COLOR_SCHEME_KEY, newScheme)
  }
  
  // 游戏设置
  const [gameMode, setGameMode] = useState('four') // 'four' 或 'pair'
  const [dealer, setDealer] = useState('南') // 发牌人位置
  const [humanPosition, setHumanPosition] = useState(null) // 人类玩家位置（兼容旧逻辑）
  const [positionRoles, setPositionRoles] = useState({
    '南': 'ai',
    '北': 'ai',
    '东': 'ai',
    '西': 'ai'
  }) // 每个位置的角色：'human' 或 'ai'
  const [showPartnerHand, setShowPartnerHand] = useState(false) // 显示队友手牌
  const [showAIHands, setShowAIHands] = useState(false) // 显示AI手牌
  const [showOpponentHands, setShowOpponentHands] = useState(false) // 显示对方手牌
  const [biddingStarted, setBiddingStarted] = useState(false) // 叫牌是否已开始
  const [showAIBiddingOutput, setShowAIBiddingOutput] = useState(true) // 显示AI叫牌完整输出
  const [isNewDeal, setIsNewDeal] = useState(true) // 是否是新发牌
  const [stopBidding, setStopBidding] = useState(false) // 是否停止叫牌
  const [passedAIPositions, setPassedAIPositions] = useState(new Set()) // 因搭档相继pass而需要自动pass的AI位置
  const [biddingStartTime, setBiddingStartTime] = useState(null) // 叫牌开始时间
  const [biddingTotalTime, setBiddingTotalTime] = useState(null) // 叫牌总时间（秒）
  const [customBidMeaning, setCustomBidMeaning] = useState('') // 用户自定义叫牌含义
  const [useFallback, setUseFallback] = useState(false) // 是否使用备用提示词
  const [dealMode, setDealMode] = useState('free') // 发牌模式：free/game/slam
  const [showSettings, setShowSettings] = useState(false) // 显示设置面板
  const [fallbackModel, setFallbackModelState] = useState(() => {
    // 从 localStorage 读取保存的备用模型配置，默认使用 deepseek-chat
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
  
  // 更多输出格式
  const [showMoreFormats, setShowMoreFormats] = useState(false) // 显示更多格式
  const [outputFormats, setOutputFormats] = useState(null) // 输出格式数据
  const [outputFormatsLoading, setOutputFormatsLoading] = useState(false) // 加载中
  const [analyzeLoading, setAnalyzeLoading] = useState(false) // 检验定约加载中
  const [analyzeResult, setAnalyzeResult] = useState(null) // 检验定约结果
  
  // 叫牌记录管理
  const [biddingRecords, setBiddingRecords] = useState([]) // 历史叫牌记录列表
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false) // 历史记录对话框
  const [editNoteDialogOpen, setEditNoteDialogOpen] = useState(false) // 编辑注释对话框
  const [editingRecordId, setEditingRecordId] = useState(null) // 正在编辑的记录ID
  const [editingNote, setEditingNote] = useState('') // 编辑中的注释
  const [selectedRecordIds, setSelectedRecordIds] = useState(new Set()) // 多选的记录ID
  const [customDealOpen, setCustomDealOpen] = useState(false) // 自定义牌局对话框
  const [imageDealOpen, setImageDealOpen] = useState(false) // 图片牌局对话框
  const [customDealText, setCustomDealText] = useState('') // 自定义牌局文本
  const [imagePath, setImagePath] = useState('') // 图片路径
  const [imageFile, setImageFile] = useState(null) // 图片文件对象
  
  // 双明手分析
  const [showDoubleDummy, setShowDoubleDummy] = useState(false) // 显示双明手结果
  const [doubleDummyResult, setDoubleDummyResult] = useState(null) // 双明手分析结果
  const [doubleDummyLoading, setDoubleDummyLoading] = useState(false) // 加载中

  // 打牌相关状态
  const [playState, setPlayState] = useState(null) // 打牌状态
  const [playLoading, setPlayLoading] = useState(false) // 打牌加载中
  const [playAiLoading, setPlayAiLoading] = useState(false) // AI出牌加载中
  const [showPlayPanel, setShowPlayPanel] = useState(false) // 显示打牌面板
  const [showPlayedCards, setShowPlayedCards] = useState(false) // 打牌时显示已出的牌
  const [isPlayPaused, setIsPlayPaused] = useState(false) // 打牌暂停状态
  const [lastCompletedTrick, setLastCompletedTrick] = useState(null) // 暂停时保存的上一墩
  const [aiPlayHistory, setAiPlayHistory] = useState([]) // AI打牌历史记录
  const [selectedPlayCard, setSelectedPlayCard] = useState(null) // 选中的出牌
  const prevTricksCountRef = useRef(0) // 用于检测一墩完成

  // 检查API状态
  useEffect(() => {
    checkApiStatus()
    loadBiddingRecords()
    syncFallbackModel()
    syncAIProvider()
  }, [])

  // 同步备用模型到后端
  const syncFallbackModel = async () => {
    try {
      await setFallbackModel(fallbackModel)
    } catch (err) {
      console.error('同步备用模型失败:', err)
    }
  }

  // 同步AI提供商到后端
  const syncAIProvider = async () => {
    try {
      await setAIProvider(aiProvider)
    } catch (err) {
      console.error('同步AI提供商失败:', err)
    }
  }

  // 处理备用模型变更
  const handleFallbackModelChange = async (event) => {
    const newModel = event.target.value
    setFallbackModelState(newModel)
    localStorage.setItem(FALLBACK_MODEL_KEY, newModel)
    try {
      await setFallbackModel(newModel)
    } catch (err) {
      console.error('设置备用模型失败:', err)
    }
  }

  // 处理AI提供商变更
  const handleAIProviderChange = async (event) => {
    const newProvider = event.target.value
    setAIProviderState(newProvider)
    localStorage.setItem('ai_provider', newProvider)
    try {
      await setAIProvider(newProvider)
    } catch (err) {
      console.error('设置AI提供商失败:', err)
    }
  }

  const checkApiStatus = async () => {
    try {
      const status = await healthCheck()
      setApiStatus(status)
    } catch (err) {
      setApiStatus({ error: 'API服务未启动' })
    }
  }

  const handleReloadJF = async () => {
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
  }

  // 加载历史叫牌记录
  const loadBiddingRecords = () => {
    try {
      const records = localStorage.getItem(BIDDING_RECORDS_KEY)
      if (records) {
        setBiddingRecords(JSON.parse(records))
      }
    } catch (err) {
      console.error('加载历史记录失败:', err)
    }
  }

  // 保存叫牌记录
  const saveBiddingRecord = (record) => {
    try {
      const newRecords = [record, ...biddingRecords].slice(0, 100) // 最多保存100条
      setBiddingRecords(newRecords)
      localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(newRecords))
    } catch (err) {
      console.error('保存记录失败:', err)
    }
  }

  // 删除叫牌记录
  const deleteBiddingRecord = (id) => {
    try {
      const newRecords = biddingRecords.filter(r => r.id !== id)
      setBiddingRecords(newRecords)
      localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(newRecords))
    } catch (err) {
      console.error('删除记录失败:', err)
    }
  }

  // 批量删除叫牌记录
  const deleteBiddingRecords = (ids) => {
    try {
      const idsSet = new Set(ids)
      const newRecords = biddingRecords.filter(r => !idsSet.has(r.id))
      setBiddingRecords(newRecords)
      localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(newRecords))
      setSelectedRecordIds(new Set())
    } catch (err) {
      console.error('批量删除记录失败:', err)
    }
  }

  // 更新记录注释
  const updateRecordNote = (id, note) => {
    try {
      const newRecords = biddingRecords.map(r => 
        r.id === id ? { ...r, note } : r
      )
      setBiddingRecords(newRecords)
      localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(newRecords))
    } catch (err) {
      console.error('更新注释失败:', err)
    }
  }

  // 导出记录为JSON文件
  const exportRecords = () => {
    try {
      const recordsToExport = selectedRecordIds.size > 0 
        ? biddingRecords.filter(r => selectedRecordIds.has(r.id))
        : biddingRecords
      
      if (recordsToExport.length === 0) {
        setError('没有可导出的记录')
        return
      }

      const exportData = {
        version: '1.0',
        exportDate: new Date().toISOString(),
        records: recordsToExport
      }
      const dataStr = JSON.stringify(exportData, null, 2)
      const blob = new Blob([dataStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `bridge_bidding_records_${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('导出记录失败:', err)
      setError('导出记录失败')
    }
  }

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedRecordIds.size === biddingRecords.length) {
      setSelectedRecordIds(new Set())
    } else {
      setSelectedRecordIds(new Set(biddingRecords.map(r => r.id)))
    }
  }

  // 切换单个记录选择
  const toggleRecordSelection = (id) => {
    const newSelected = new Set(selectedRecordIds)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedRecordIds(newSelected)
  }

  // 导入记录从JSON文件
  const importRecords = (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const importData = JSON.parse(e.target.result)
        if (!importData.records || !Array.isArray(importData.records)) {
          setError('无效的记录文件格式')
          return
        }

        const importedRecords = importData.records
        const existingIds = new Set(biddingRecords.map(r => r.id))
        const newRecords = importedRecords.filter(r => !existingIds.has(r.id))
        const mergedRecords = [...newRecords, ...biddingRecords].slice(0, 100)

        setBiddingRecords(mergedRecords)
        localStorage.setItem(BIDDING_RECORDS_KEY, JSON.stringify(mergedRecords))
        setError(null)
      } catch (err) {
        console.error('导入记录失败:', err)
        setError('导入记录失败: 文件格式错误')
      }
    }
    reader.readAsText(file)
    event.target.value = ''
  }

  // 加载历史记录到牌桌
  const loadRecordToTable = (record) => {
    isLoadingRecordRef.current = true
    setHands(record.hands)
    setBiddingSequence(record.biddingSequence)
    setDealer(record.dealer)
    // 恢复叫牌设置
    if (record.gameMode) {
      setGameMode(record.gameMode)
    }
    if (record.humanPosition) {
      setHumanPosition(record.humanPosition)
    }
    setAiBiddingHistory(record.aiBiddingHistory || [])
    if (record.dealSystem) {
      setDealSystem(record.dealSystem)
    }
    setBiddingStarted(true)
    setHistoryDialogOpen(false)
    setOutputFormats(null) // 重置输出格式
    setIsNewDeal(false) // 标记为历史记录加载，显示"重新叫牌"
    setShowDoubleDummy(false) // 切换到显示叫牌过程
    setDoubleDummyResult(null) // 清除双明手结果
    setShowPlayPanel(false) // 确保显示叫牌面板
    // 重置打牌相关状态
    setPlayState(null)
    setAiPlayHistory([])
    setSelectedPlayCard(null)
    setIsPlayPaused(false)
    
    // 加载历史记录后获取更多输出格式
    if (record.hands && record.biddingSequence && record.biddingSequence.length > 0) {
      // 延迟调用，确保状态已更新
      setTimeout(() => {
        fetchOutputFormatsForRecord(record)
        isLoadingRecordRef.current = false
      }, 100)
    } else {
      isLoadingRecordRef.current = false
    }
  }
  
  // 为历史记录获取输出格式
  const fetchOutputFormatsForRecord = async (record) => {
    if (!record.hands || !record.biddingSequence || record.biddingSequence.length === 0) return
    
    setOutputFormatsLoading(true)
    try {
      const biddingStr = record.biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      console.log('[DEBUG] 加载历史记录获取输出格式, biddingStr:', biddingStr, 'dealer:', record.dealer)
      const result = await getOutputFormats(record.hands, biddingStr, record.dealer, gameMode, humanPosition)
      console.log('[DEBUG] 输出格式结果:', result)
      setOutputFormats(result)
    } catch (err) {
      console.error('获取输出格式失败:', err)
    } finally {
      setOutputFormatsLoading(false)
    }
  }

  // 叫牌回退功能
  const saveBiddingSnapshot = useCallback(() => {
    const snapshot = {
      biddingSequence: [...biddingSequence],
      currentBidder,
      aiBiddingHistory: [...aiBiddingHistory],
    }
    const newHistory = historyIndex >= 0 
      ? biddingHistory.slice(0, historyIndex + 1) 
      : biddingHistory
    setBiddingHistory([...newHistory, snapshot])
    setHistoryIndex(newHistory.length)
  }, [biddingSequence, currentBidder, aiBiddingHistory, biddingHistory, historyIndex])

  const undoBidding = useCallback(() => {
    if (historyIndex > 0) {
      const snapshot = biddingHistory[historyIndex - 1]
      setBiddingSequence(snapshot.biddingSequence)
      setCurrentBidder(snapshot.currentBidder)
      setAiBiddingHistory(snapshot.aiBiddingHistory)
      setHistoryIndex(historyIndex - 1)
      setBidSuggestion(null)
    }
  }, [biddingHistory, historyIndex])

  // 只有停止叫牌后才能撤销，且AI不在加载中（包括AI叫牌和获取叫品含义）
  const showUndo = stopBidding && historyIndex > 0
  const canUndo = !aiLoading && !currentBiddingPosition

  // 发牌
  const handleDeal = async (mode = 'free') => {
    setLoading(true)
    setError(null)
    try {
      const data = await dealCards(mode)
      setHands(data.hands)
      setBiddingSequence([])
      setBidSuggestion(null) // 重置叫牌建议
      setAiBiddingHistory([]) // 重置AI叫牌历史记录
      setCurrentBidder(dealer) // 从发牌人开始叫牌
      setBiddingStarted(false) // 重置叫牌开始状态
      setIsNewDeal(true) // 标记为新发牌
      setStopBidding(false) // 重置停止叫牌状态
      setPassedAIPositions(new Set()) // 重置已pass的AI位置
      setUseFallback(false) // 重置备用提示词状态
      setShowDoubleDummy(false) // 重置双明手显示状态
      setDoubleDummyResult(null) // 重置双明手结果
      // 重置回退历史
      setBiddingHistory([])
      setHistoryIndex(-1)
      // 重置打牌相关状态
      setShowPlayPanel(false)
      setPlayState(null)
      setAiPlayHistory([])
      setSelectedPlayCard(null)
      setIsPlayPaused(false)
    } catch (err) {
      setError('发牌失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }

  // 自定义牌局
  const handleCustomDeal = async (inputText) => {
    setLoading(true)
    setError(null)
    try {
      const data = await customDeal(inputText)
      if (data.success) {
        setHands(data.hands)
        setBiddingSequence([])
        setBidSuggestion(null)
        setAiBiddingHistory([])
        setCurrentBidder(dealer)
        setBiddingStarted(false)
        setIsNewDeal(true)
        setStopBidding(false)
        setPassedAIPositions(new Set())
        setUseFallback(false)
        setShowDoubleDummy(false)
        setDoubleDummyResult(null)
        setBiddingHistory([])
        setHistoryIndex(-1)
        // 重置打牌相关状态
        setShowPlayPanel(false)
        setPlayState(null)
        setAiPlayHistory([])
        setSelectedPlayCard(null)
        setIsPlayPaused(false)
      } else {
        setError(data.message || '牌局解析失败')
      }
    } catch (err) {
      setError('自定义牌局失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }

  // 从图片读取牌局
  const handleImageDeal = async (imageFile) => {
    setLoading(true)
    setError(null)
    try {
      const data = await imageDeal(imageFile)
      if (data.success) {
        setHands(data.hands)
        setBiddingSequence([])
        setBidSuggestion(null)
        setAiBiddingHistory([])
        setCurrentBidder(dealer)
        setBiddingStarted(false)
        setIsNewDeal(true)
        setStopBidding(false)
        setPassedAIPositions(new Set())
        setUseFallback(false)
        setShowDoubleDummy(false)
        setDoubleDummyResult(null)
        setBiddingHistory([])
        setHistoryIndex(-1)
        // 重置打牌相关状态
        setShowPlayPanel(false)
        setPlayState(null)
        setAiPlayHistory([])
        setSelectedPlayCard(null)
        setIsPlayPaused(false)
      } else {
        setError(data.message || '图片识别失败')
      }
    } catch (err) {
      setError('图片识别失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }

  // 截屏读取牌局 - 点击触发截图，等待后自动读取剪贴板识别
  const handleScreenshotDeal = async () => {
    if (loading) return

    setShowSettings(false)
    setLoading(true)
    setError('截屏已触发，请在5秒内完成截图...')
    try {
      const result = await triggerScreenshot()
      if (!result.success) {
        setError(result.message || '触发截屏失败')
        setLoading(false)
        return
      }

      setError('正在识别...')
      await new Promise(resolve => setTimeout(resolve, 5000))

      const data = await readClipboardDeal()
      if (data.success) {
        setHands(data.hands)
        setBiddingSequence([])
        setBidSuggestion(null)
        setAiBiddingHistory([])
        setCurrentBidder(dealer)
        setBiddingStarted(false)
        setIsNewDeal(true)
        setStopBidding(false)
        setPassedAIPositions(new Set())
        setUseFallback(false)
        setShowDoubleDummy(false)
        setDoubleDummyResult(null)
        setBiddingHistory([])
        setHistoryIndex(-1)
        setError(null)
        // 重置打牌相关状态
        setShowPlayPanel(false)
        setPlayState(null)
        setAiPlayHistory([])
        setSelectedPlayCard(null)
        setIsPlayPaused(false)
      } else {
        setError(data.message || '识别失败，请确保已截取图片')
      }
    } catch (err) {
      setError('截屏识别失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }

  // 开始叫牌
  const startBidding = () => {
    if (hands) {
      // 检查AI位置是否都有手牌
      const aiPositions = Object.entries(positionRoles)
        .filter(([, role]) => role === 'ai')
        .map(([pos]) => pos)
      
      for (const pos of aiPositions) {
        const hand = hands[pos]
        if (!hand || (!hand.spades && !hand.hearts && !hand.diamonds && !hand.clubs)) {
          setError(`${pos}家(AI)没有手牌，请先输入手牌`)
          return
        }
      }
      
      // 重置叫牌序列
      setBiddingSequence([])
      setCurrentBidder(dealer) // 从发牌人开始叫牌
      setBiddingStarted(true) // 标记叫牌已开始
      setIsNewDeal(false) // 标记为非新发牌
      setAiBiddingHistory([]) // 清理上次叫牌输出
      setStopBidding(false) // 重置停止叫牌状态
      setPassedAIPositions(new Set()) // 重置已pass的AI位置
      setBiddingStartTime(Date.now()) // 记录开始时间
      setBiddingTotalTime(null) // 重置总时间
      setError(null) // 清除错误
      // 重置回退历史并保存初始快照
      const initialSnapshot = {
        biddingSequence: [],
        currentBidder: dealer,
        aiBiddingHistory: [],
      }
      setBiddingHistory([initialSnapshot])
      setHistoryIndex(0)
    }
  }

  // 重新叫牌（保持当前牌局）
  const resetBidding = () => {
    setBiddingSequence([])
    setCurrentBidder(dealer)
    setBiddingStarted(false)
    setAiBiddingHistory([])
    setStopBidding(false)
    setPassedAIPositions(new Set())
    setIsNewDeal(false)
    setBiddingStartTime(null)
    setBiddingTotalTime(null)
    setBiddingHistory([])
    setHistoryIndex(-1)
  }

  // 清除所有手牌（重新开始一局）
  const clearAllHands = () => {
    setHands({
      '南': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '北': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '东': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 },
      '西': { spades: '', hearts: '', diamonds: '', clubs: '', hcp: 0 }
    })
    setBiddingSequence([])
    setBidSuggestion(null)
    setAiBiddingHistory([])
    setCurrentBidder(dealer)
    setBiddingStarted(false)
    setIsNewDeal(true)
    setStopBidding(false)
    setPassedAIPositions(new Set())
    setOutputFormats(null)
    setShowDoubleDummy(false)
    setDoubleDummyResult(null)
    setBiddingHistory([])
    setHistoryIndex(-1)
    // 重置打牌相关状态
    setShowPlayPanel(false)
    setPlayState(null)
    setAiPlayHistory([])
    setSelectedPlayCard(null)
    setIsPlayPaused(false)
  }

  // 切换停止/继续叫牌
  const toggleStopBidding = () => {
    setStopBidding(!stopBidding)
  }

  // 添加叫牌
  const addBid = async (bid) => {
    const isCurrentHuman = positionRoles && positionRoles[currentBidder] === 'human'
    // 人类叫牌后，立即标记叫牌已开始（在currentBidder更新之前）
    if (isCurrentHuman && !biddingStarted) {
      setBiddingStarted(true)
    }
    
    // 人类叫牌时，保存叫牌记录
    if (isCurrentHuman) {
      // 用于显示的字符串
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-') + (biddingSequence.length > 0 ? '-' : '')
      
      // 如果用户输入了自定义叫牌含义，直接使用，不调用API
      if (customBidMeaning.trim()) {
        setAiBiddingHistory(prev => [...prev, {
          position: currentBidder,
          hand: hands[currentBidder],
          biddingSequence: biddingStr,
          result: { bid: bid, meaning: customBidMeaning.trim() },
          timestamp: new Date().toLocaleTimeString()
        }])
        setCustomBidMeaning('') // 清空输入框
      } else {
        // 没有自定义含义，调用API获取（传递数组，后端处理格式）
        setCurrentBiddingPosition(currentBidder)
        try {
          const result = await humanBid(biddingSequence, currentBidder, bid, dealSystem)
          
          setAiBiddingHistory(prev => [...prev, {
            position: currentBidder,
            hand: hands[currentBidder],
            biddingSequence: biddingStr,
            result: { 
              bid: result.bid, 
              meaning: result.meaning,
              full_output: result.full_output
            },
            timestamp: new Date().toLocaleTimeString()
          }])
        } catch (err) {
          console.error('获取叫品含义失败:', err)
          setAiBiddingHistory(prev => [...prev, {
            position: currentBidder,
            hand: hands[currentBidder],
            biddingSequence: biddingStr,
            result: { 
              bid: bid, 
              meaning: '获取叫品含义失败',
              full_output: {}
            },
            timestamp: new Date().toLocaleTimeString()
          }])
        } finally {
          setCurrentBiddingPosition(null)
        }
      }
    }
    
    const newBid = {
      position: currentBidder,
      bid: bid
    }
    const newSequence = [...biddingSequence, newBid]
    
    // 计算下一个叫牌者
    const positions = ['南', '西', '北', '东']
    const currentIndex = positions.indexOf(currentBidder)
    const nextIndex = (currentIndex + 1) % 4
    const nextBidder = positions[nextIndex]

    // 根据游戏模式判断是否需要为对方阵营添加自动pass
    if (gameMode === 'pair') {
      // 双人模式：南北 vs 东西
      // 判断下一个叫牌者是否属于对方阵营
      const humanPair = ['南', '北'].includes(humanPosition) ? ['南', '北'] : ['东', '西']
      const isHumanTeam = humanPair.includes(currentBidder)
      const isNextHumanTeam = humanPair.includes(nextBidder)
      
      if (isHumanTeam !== isNextHumanTeam) {
        // 下一个是对方阵营，自动pass
        const passBid = {
          position: nextBidder,
          bid: 'pass'
        }
        newSequence.push(passBid)
        
        // 继续计算下一个
        const nextNextIndex = (nextIndex + 1) % 4
        const nextNextBidder = positions[nextNextIndex]
        
        setBiddingSequence(newSequence)
        setCurrentBidder(nextNextBidder)
        
        // 保存叫牌快照（双人模式自动pass）
        const snapshotPair = {
          biddingSequence: newSequence,
          currentBidder: nextNextBidder,
          aiBiddingHistory: [...aiBiddingHistory],
        }
        const newHistoryPair = historyIndex >= 0 
          ? biddingHistory.slice(0, historyIndex + 1) 
          : biddingHistory
        setBiddingHistory([...newHistoryPair, snapshotPair])
        setHistoryIndex(newHistoryPair.length)
        
        return
      }
    }

    setBiddingSequence(newSequence)
    setCurrentBidder(nextBidder)
    
    // 保存叫牌快照
    const snapshot = {
      biddingSequence: newSequence,
      currentBidder: nextBidder,
      aiBiddingHistory: [...aiBiddingHistory],
    }
    const newHistory = historyIndex >= 0 
      ? biddingHistory.slice(0, historyIndex + 1) 
      : biddingHistory
    setBiddingHistory([...newHistory, snapshot])
    setHistoryIndex(newHistory.length)
    
    // 四人模式：检查搭档两人是否相继pass（中间只有对方的一次叫牌或pass）
    // 前提：必须已有实质性叫牌（第一个实质性叫牌之前的pass不算）
    if (gameMode === 'four' && bid === 'pass') {
      // 检查是否已有实质性叫牌
      const hasRealBid = biddingSequence.some(b => b.bid !== 'pass')
      if (!hasRealBid) {
        return
      }
      
      // 搭档关系
      const partnerships = { '南': '北', '北': '南', '东': '西', '西': '东' }
      
      // 找到当前叫牌者的搭档
      const partner = partnerships[currentBidder]
      
      // 在叫牌序列中找搭档最近一次pass的位置
      let partnerPassIndex = -1
      for (let i = newSequence.length - 2; i >= 0; i--) {
        if (newSequence[i].position === partner && newSequence[i].bid === 'pass') {
          partnerPassIndex = i
          break
        }
      }
      
      // 如果搭档pass过，检查中间是否只有对方的叫牌
      if (partnerPassIndex !== -1) {
        // 从搭档pass到当前pass，中间应该只有一次叫牌（对方的）
        const bidsBetween = newSequence.slice(partnerPassIndex + 1, -1)
        if (bidsBetween.length === 1) {
          const middleBid = bidsBetween[0]
          // 检查中间的叫牌是否来自对方
          if (partnerships[middleBid.position] !== partner) {
            // 相继pass成立，标记需要自动pass的AI位置
            const currentIsAI = positionRoles[currentBidder] === 'ai'
            const partnerIsAI = positionRoles[partner] === 'ai'
            
            const positionsToMark = []
            if (currentIsAI) {
              positionsToMark.push(currentBidder)
            }
            if (partnerIsAI) {
              positionsToMark.push(partner)
            }
            
            if (positionsToMark.length > 0) {
              console.log(`搭档${currentBidder}和${partner}相继pass，AI位置${positionsToMark.join('、')}后续自动pass`)
              setPassedAIPositions(prev => {
                const newSet = new Set(prev)
                positionsToMark.forEach(pos => newSet.add(pos))
                return newSet
              })
            }
          }
        }
      }
    }
  }

  // 检查AI位置是否需要自动pass
  const shouldAIAutoPass = (position) => {
    return passedAIPositions.has(position)
  }

  // 调用AI叫牌
  const callAIBid = async () => {
    if (!hands || !currentBidder || isBiddingComplete()) return
    
    // 检查是否停止叫牌
    if (stopBidding) return
    
    // 检查是否是人类玩家的回合
    const isHumanTurn = positionRoles && positionRoles[currentBidder] === 'human'
    if (isHumanTurn) return
    
    // 检查AI位置是否需要自动pass
    if (gameMode === 'four' && shouldAIAutoPass(currentBidder)) {
      console.log(`${currentBidder}家因搭档相继pass，自动pass`)
      setAiBiddingHistory(prev => [...prev, {
        position: currentBidder,
        hand: hands[currentBidder],
        biddingSequence: biddingSequence.map(b => `(${b.position})${b.bid}`).join('-'),
        result: { bid: 'pass', meaning: '搭档已相继pass，不再参与叫牌' },
        timestamp: new Date().toLocaleTimeString()
      }])
      addBid('pass')
      return
    }
    
    setCurrentBiddingPosition(currentBidder)
    setAiLoading(true)
    try {
      // 用于显示的字符串
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-') + (biddingSequence.length > 0 ? '-' : '')
      
      // 构建累积的叫牌历史（与终端版格式一致）
      const bidHistory = aiBiddingHistory.map(record => 
        `\n(${record.position})${record.result.meaning}`
      ).join('')
      
      // 获取当前叫牌者的手牌
      const currentHand = hands[currentBidder]
      
      console.log(`AI叫牌: ${currentBidder}家, 手牌:`, currentHand, '叫牌序列:', biddingStr, '叫牌历史:', bidHistory)
      
      // 传递数组，后端处理格式
      const result = await aiBid(currentHand, biddingSequence, currentBidder, dealSystem, bidHistory, useFallback, fallbackModel, aiProvider)
      
      // 更新useFallback状态
      if (result.use_fallback !== undefined) {
        setUseFallback(result.use_fallback)
      }
      
      console.log(`AI叫牌结果: ${currentBidder}家, 叫品:`, result.bid, '含义:', result.meaning)
      
      // 保存AI叫牌历史记录
      setAiBiddingHistory(prev => [...prev, {
        position: currentBidder,
        hand: currentHand,
        biddingSequence: biddingStr,
        result: result,
        timestamp: new Date().toLocaleTimeString()
      }])
      
      // 添加AI叫牌
      addBid(result.bid)
    } catch (err) {
      console.error('AI叫牌失败:', err)
      // 出错时默认pass
      addBid('pass')
    } finally {
      setAiLoading(false)
      setCurrentBiddingPosition(null)
    }
  }

  // 获取JF约定片段
  const getJFSuggestion = async () => {
    if (!hands || !currentBidder || isBiddingComplete()) return
    
    setSuggestionLoading(true)
    try {
      // 构建叫牌序列字符串
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      
      // 调用分析API获取JF约定片段
      const result = await analyzeBidding(biddingStr, currentBidder, dealSystem)
      
      setBidSuggestion({
        keyword: result.keyword,
        content: result.content
      })
    } catch (err) {
      console.error('获取JF约定片段失败:', err)
      setBidSuggestion(null)
    } finally {
      setSuggestionLoading(false)
    }
  }

  // 当currentBidder变化时，检查是否需要调用AI叫牌或获取JF约定片段
  useEffect(() => {
    if (!hands || aiLoading) return
    
    // 叫牌已结束，不再处理
    if (isBiddingComplete()) return
    
    // 检查是否需要等待人类叫牌
    const isHumanTurn = positionRoles && positionRoles[currentBidder] === 'human'
    
    // 四人模式下，如果AI位置需要自动pass
    if (gameMode === 'four' && shouldAIAutoPass(currentBidder) && !isHumanTurn) {
      callAIBid()
      return
    }
    
    // 人类玩家回合时，获取JF约定片段并自动切换到叫牌控制面板
    if (isHumanTurn) {
      getJFSuggestion()
      setShowBiddingControls(true)
    }
    
    // AI叫牌逻辑
    if (!isHumanTurn && !stopBidding) {
      // AI回合
      const hasHumanPosition = positionRoles && Object.values(positionRoles).some(r => r === 'human')
      if (!hasHumanPosition) {
        // 观察模式：需要点击开始叫牌按钮
        if (biddingStarted) {
          callAIBid()
        }
      } else {
        // 有人类参与
        // 如果人类不是第一个叫牌，需要点击开始叫牌按钮
        // 如果人类是第一个叫牌，人类叫牌后biddingStarted会被设置为true
        if (biddingStarted) {
          callAIBid()
        }
      }
    }
  }, [currentBidder, positionRoles, hands, aiLoading, biddingSequence, biddingStarted, stopBidding, passedAIPositions])

  // 判断叫牌是否结束
  const isBiddingComplete = () => {
    if (biddingSequence.length < 4) return false

    // 检查最后四个是否都是pass
    const lastFour = biddingSequence.slice(-4)
    if (lastFour.length === 4 && lastFour.every(b => b.bid === 'pass')) {
      return true
    }

    // 检查是否有3个连续的pass在第一个实质性叫品之后
    let hasRealBid = false
    for (let i = 0; i < biddingSequence.length; i++) {
      if (biddingSequence[i].bid !== 'pass') {
        hasRealBid = true
      }
      if (hasRealBid && i >= 2) {
        const lastThree = biddingSequence.slice(i - 2, i + 1)
        if (lastThree.every(b => b.bid === 'pass')) {
          return true
        }
      }
    }

    return false
  }

  // 确定最终定约
  const getFinalContract = () => {
    if (!isBiddingComplete() || biddingSequence.length === 0) return null

    // 找到最后一个非pass的叫品
    const nonPassBids = biddingSequence.filter(b => b.bid !== 'pass')
    if (nonPassBids.length === 0) return null

    const lastBid = nonPassBids[nonPassBids.length - 1]
    const bid = lastBid.bid
    const position = lastBid.position

    // 解析叫品
    let level = 0
    let suit = ''
    let isDouble = false
    let isRedouble = false

    if (bid === 'X') {
      // 找到被加倍的叫品
      const targetBids = nonPassBids.slice(0, -1).filter(b => b.bid !== 'X' && b.bid !== 'XX')
      if (targetBids.length === 0) return null
      const targetBid = targetBids[targetBids.length - 1]
      level = parseInt(targetBid.bid[0])
      suit = targetBid.bid.substring(1)
      isDouble = true
    } else if (bid === 'XX') {
      // 找到被再加倍的叫品
      const targetBids = nonPassBids.slice(0, -1).filter(b => b.bid === 'X')
      if (targetBids.length === 0) return null
      const doubleBid = targetBids[targetBids.length - 1]
      const originalBids = nonPassBids.slice(0, nonPassBids.indexOf(doubleBid)).filter(b => b.bid !== 'X' && b.bid !== 'XX')
      if (originalBids.length === 0) return null
      const originalBid = originalBids[originalBids.length - 1]
      level = parseInt(originalBid.bid[0])
      suit = originalBid.bid.substring(1)
      isDouble = true
      isRedouble = true
    } else {
      // 普通叫品
      level = parseInt(bid[0])
      suit = bid.substring(1)
    }

    // 确定定约方（叫牌者所在的一方）
    const partnership = ['南', '北'].includes(position) ? '南北' : '东西'
    
    // 确定庄家：定约方中第一个叫出该花色的人
    const partnershipPositions = partnership === '南北' ? ['南', '北'] : ['东', '西']
    let declarer = position
    for (const bidItem of biddingSequence) {
      if (partnershipPositions.includes(bidItem.position) && bidItem.bid.includes(suit) && bidItem.bid !== 'pass' && bidItem.bid !== 'X' && bidItem.bid !== 'XX') {
        declarer = bidItem.position
        break
      }
    }

    return {
      level,
      suit,
      isDouble,
      isRedouble,
      declarer,
      partnership,
      bid: bid
    }
  }

  // 叫牌结束时自动保存记录
  useEffect(() => {
    if (isBiddingComplete() && biddingSequence.length > 0 && hands && !isLoadingRecordRef.current) {
      // 计算总时间
      if (biddingStartTime) {
        const totalTime = Math.round((Date.now() - biddingStartTime) / 1000)
        setBiddingTotalTime(totalTime)
      }
      
      const finalContract = getFinalContract()
      const record = {
        id: Date.now().toString(),
        timestamp: new Date().toLocaleString(),
        hands: hands,
        biddingSequence: biddingSequence,
        aiBiddingHistory: aiBiddingHistory,
        dealer: dealer,
        gameMode: gameMode,
        humanPosition: humanPosition,
        finalContract: finalContract,
        dealSystem: dealSystem,
        note: ''
      }
      saveBiddingRecord(record)
      
      // 获取更多输出格式
      fetchOutputFormats()
    }
  }, [biddingSequence, hands, dealer])
  
  // 获取更多输出格式
  const fetchOutputFormats = async () => {
    if (!hands || biddingSequence.length === 0) return
    
    setOutputFormatsLoading(true)
    try {
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      console.log('[DEBUG] 获取输出格式, biddingStr:', biddingStr, 'dealer:', dealer, 'gameMode:', gameMode)
      const result = await getOutputFormats(hands, biddingStr, dealer, gameMode, positionRoles)
      console.log('[DEBUG] 输出格式结果:', result)
      setOutputFormats(result)
    } catch (err) {
      console.error('获取输出格式失败:', err)
    } finally {
      setOutputFormatsLoading(false)
    }
  }

  // 检验定约 - 调用Deep Finesse
  const handleAnalyzeContract = async () => {
    if (!outputFormats?.deep_finesse) return
    
    setAnalyzeLoading(true)
    setAnalyzeResult(null)
    try {
      const result = await analyzeContract(outputFormats.deep_finesse)
      setAnalyzeResult(result)
      if (!result.success) {
        alert(`检验定约失败: ${result.error}`)
      }
    } catch (err) {
      console.error('检验定约失败:', err)
      alert('检验定约失败，请检查Deep Finesse是否正确安装')
    } finally {
      setAnalyzeLoading(false)
    }
  }

  // 双明手分析
  const handleDoubleDummy = async () => {
    if (!hands) return
    
    setDoubleDummyLoading(true)
    try {
      const result = await doubleDummyAnalysis(hands)
      if (result.success) {
        setDoubleDummyResult(result.table_data)
      } else {
        alert(`双明手分析失败: ${result.error}`)
      }
    } catch (err) {
      console.error('双明手分析失败:', err)
      alert('双明手分析失败，请检查endplay是否正确安装')
    } finally {
      setDoubleDummyLoading(false)
    }
  }

  // 切换显示双明手结果
  const toggleDoubleDummy = (checked) => {
    setShowDoubleDummy(checked)
    if (checked && hands) {
      handleDoubleDummy()
    }
  }

  // ==================== 打牌相关函数 ====================

  // 开始打牌
  const handleStartPlay = async () => {
    const contract = getFinalContract()
    
    if (!contract) {
      setError('无法确定定约')
      return
    }
    
    setPlayLoading(true)
    setError(null)
    setIsPlayPaused(false) // 重置暂停状态
    prevTricksCountRef.current = 0 // 重置墩数计数器
    
    try {
      const result = await playInit(
        hands,
        `${contract.level}${contract.suit}`,
        contract.declarer,
        positionRoles,
        contract.isDouble,
        contract.isRedouble
      )
      
      if (result.success) {
        setPlayState(result.state)
        setShowPlayPanel(true)
      } else {
        setError(result.error || '初始化打牌失败')
      }
    } catch (err) {
      console.error('初始化打牌失败:', err)
      setError('初始化打牌失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setPlayLoading(false)
    }
  }

  // 出牌
  const handlePlayCard = async (position, card) => {
    setPlayLoading(true)
    setError(null)
    
    try {
      const result = await playCard(position, card)
      
      if (result.success) {
        console.log('[DEBUG handlePlayCard] result.state.current_trick:', result.state.current_trick)
        setPlayState(result.state)
        
        if (result.is_complete && result.result) {
          console.log('打牌结束:', result.result)
        }
      } else {
        setError(result.error || '出牌失败')
      }
    } catch (err) {
      console.error('出牌失败:', err)
      setError('出牌失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setPlayLoading(false)
    }
  }

  // AI出牌
  const handleAIPlay = async () => {
    setPlayAiLoading(true)
    setError(null)
    
    try {
      const result = await aiPlay()
      
      if (result.success) {
        const aiRecord = {
          position: playState?.current_player,
          card: result.card,
          reasoning: result.reasoning,
          risk: result.risk,
          full_output: result.full_output,
          timestamp: new Date().toLocaleTimeString(),
        }
        setAiPlayHistory(prev => [...prev, aiRecord])
        
        const stateResult = await getPlayState()
        if (stateResult.success) {
          console.log('[DEBUG handleAIPlay] FULL state:', JSON.stringify(stateResult.state, null, 2))
          console.log('[DEBUG handleAIPlay] current_trick:', JSON.stringify(stateResult.state?.current_trick, null, 2))
          setPlayState(stateResult.state)
        }
      } else {
        setError(result.error || 'AI出牌失败')
      }
    } catch (err) {
      console.error('AI出牌失败:', err)
      setError('AI出牌失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setPlayAiLoading(false)
    }
  }

  const handleResumePlay = () => {
    setIsPlayPaused(false)
    setLastCompletedTrick(null)
    setShowDoubleDummy(false)
  }

  // AI自动出牌
  useEffect(() => {
    if (!showPlayPanel || !playState || playAiLoading || playLoading || isPlayPaused) return
    
    const { is_human_turn, phase } = playState
    
    // 如果不是人类回合且游戏未结束，自动AI出牌
    if (!is_human_turn && phase !== 'complete') {
      const timer = setTimeout(() => {
        handleAIPlay()
      }, 500) // 延迟500ms让用户看到状态变化
      
      return () => clearTimeout(timer)
    }
  }, [playState?.is_human_turn, playState?.phase, showPlayPanel, playAiLoading, playLoading, isPlayPaused])

  // 检测一墩完成，自动暂停
  useEffect(() => {
    if (!showPlayPanel || !playState) return
    
    const currentTricksCount = playState.tricks?.length || 0
    const prevTricksCount = prevTricksCountRef.current
    
    // 如果墩数增加了，说明一墩完成，自动暂停
    if (currentTricksCount > prevTricksCount && playState.tricks && playState.tricks.length > 0) {
      const lastTrick = playState.tricks[playState.tricks.length - 1]
      setLastCompletedTrick(lastTrick)
      setIsPlayPaused(true)
    }
    
    prevTricksCountRef.current = currentTricksCount
  }, [playState?.tricks?.length, showPlayPanel])

  // 获取队友位置
  const getPartnerPosition = (pos) => {
    const partners = {
      '南': '北',
      '北': '南',
      '东': '西',
      '西': '东'
    }
    return partners[pos]
  }

  // 处理位置角色变化
  const handlePositionRoleChange = async (position, role) => {
    const newRoles = { ...positionRoles, [position]: role }
    
    setPositionRoles(prev => {
      const updatedRoles = { ...prev, [position]: role }
      // 更新 humanPosition 以保持兼容性
      const humanPositions = Object.entries(updatedRoles)
        .filter(([, r]) => r === 'human')
        .map(([pos]) => pos)
      if (humanPositions.length === 0) {
        setHumanPosition(null)
      } else if (humanPositions.length === 1) {
        setHumanPosition(humanPositions[0])
      } else {
        // 多个人类位置时，使用数组
        setHumanPosition(humanPositions)
      }
      return updatedRoles
    })
    
    // 如果在打牌阶段，同步更新后端的 player_roles
    if (showPlayPanel && playState) {
      try {
        const result = await updatePlayPlayerRoles(newRoles)
        console.log('[DEBUG] updatePlayPlayerRoles result:', result)
        if (result.success) {
          console.log('[DEBUG] new state is_human_turn:', result.state?.is_human_turn)
          console.log('[DEBUG] new state player_roles:', result.state?.player_roles)
          setPlayState(result.state)
        }
      } catch (err) {
        console.error('更新打牌角色失败:', err)
      }
    }
  }

  // 渲染叫牌表格
  const renderBiddingTable = () => {
    if (biddingSequence.length === 0) {
      return (
        <div className="bidding-empty">
          等待叫牌...<br />
          <small>发牌人: {dealer}</small>
        </div>
      )
    }

    const positions = ['南', '西', '北', '东']
    const rows = []
    let currentRow = Array(4).fill(null)
    let currentRowInfo = Array(4).fill(null)

    biddingSequence.forEach((bid, bidIndex) => {
      const posIndex = positions.indexOf(bid.position)
      currentRow[posIndex] = bid.bid
      
      const isAI = positionRoles[bid.position] === 'ai'
      const aiRecord = aiBiddingHistory[bidIndex]
      
      currentRowInfo[posIndex] = {
        isAI,
        reason: aiRecord?.result?.meaning || null
      }

      if (posIndex === 3) {
        rows.push({ bids: [...currentRow], info: [...currentRowInfo] })
        currentRow = Array(4).fill(null)
        currentRowInfo = Array(4).fill(null)
      }
    })

    if (currentRow.some(cell => cell !== null)) {
      rows.push({ bids: [...currentRow], info: [...currentRowInfo] })
    }

    return (
      <div className="bidding-table">
        <div className="bidding-header">
          {positions.map(pos => (
            <span key={pos} className={pos === dealer ? 'dealer' : ''}>
              {pos}{pos === dealer ? '*' : ''}
            </span>
          ))}
        </div>
        {rows.map((row, rowIndex) => (
          <div key={rowIndex} className="bidding-row">
            {positions.map((pos, colIndex) => {
              const bid = row.bids[colIndex]
              const info = row.info[colIndex]
              if (!bid) {
                return <span key={colIndex} className="bidding-cell"></span>
              }
              
              const displayText = bid === 'pass' ? 'P' : bid
              
              if (info?.isAI) {
                const cell = (
                  <span 
                    key={colIndex} 
                    className="bidding-cell has-bid ai-bid" 
                    style={{ backgroundColor: '#e0e0e0', cursor: info?.reason ? 'pointer' : 'default' }}
                  >
                    {displayText}
                  </span>
                )
                
                if (info?.reason) {
                  return (
                    <Tooltip key={colIndex} title={info.reason} arrow placement="top">
                      {cell}
                    </Tooltip>
                  )
                }
                return cell
              }
              
              return (
                <span key={colIndex} className="bidding-cell has-bid" style={{ backgroundColor: '#fff' }}>
                  {displayText}
                </span>
              )
            })}
          </div>
        ))}
      </div>
    )
  }

  return (
    <Box sx={{ display: 'block', width: '100%', py: { xs: 2, md: 4 }, px: { xs: 1, md: 3 } }}>
      <Divider sx={{ mb: 2, borderColor: 'rgba(0, 0, 0, 0.3)', borderBottomWidth: 2 }} />

      {/* 标题 */}
      <Typography variant="h4" component="h1" align="center" sx={{ fontSize: { xs: '1.25rem', md: '1.75rem' }, mb: { xs: 2, md: 0 }, display: { xs: 'block', md: 'none' } }}>
        桥牌叫牌练习系统
      </Typography>

      {/* 标题 - 桌面版 */}
      <Box sx={{ mb: 2, display: { xs: 'none', md: 'flex' }, flexWrap: 'wrap', justifyContent: 'center', gap: 2, alignItems: 'center' }}>
        <Typography variant="h4" component="h1" sx={{ fontSize: '1.75rem', mr: 3, whiteSpace: 'nowrap' }}>
          桥牌叫牌练习系统
        </Typography>
      </Box>

      {/* 控制按钮 - 桌面版 */}
      <Box sx={{ mb: 2, display: { xs: 'none', md: 'flex' }, flexWrap: 'wrap', justifyContent: 'center', gap: 2, alignItems: 'center' }}>
        <ControlButtons
          size="large"
          showSettings={showSettings}
          setShowSettings={setShowSettings}
          loading={loading}
          handleDeal={handleDeal}
          dealMode={dealMode}
          hands={hands}
          biddingStarted={biddingStarted}
          isBiddingComplete={isBiddingComplete}
          stopBidding={stopBidding}
          toggleStopBidding={toggleStopBidding}
          isNewDeal={isNewDeal}
          startBidding={startBidding}
          biddingRecords={biddingRecords}
          setHistoryDialogOpen={setHistoryDialogOpen}
          checkApiStatus={checkApiStatus}
          apiStatus={apiStatus}
          handleReloadJF={handleReloadJF}
          showUndo={showUndo}
          canUndo={canUndo}
          onUndo={undoBidding}
          showPlayPanel={showPlayPanel}
        />
      </Box>

      {/* 控制按钮 - 手机版 */}
      <Box sx={{ mb: 2, display: { xs: 'flex', md: 'none' }, flexWrap: 'wrap', justifyContent: 'center', gap: 1, alignItems: 'center' }}>
        <ControlButtons
          size="small"
          showSettings={showSettings}
          setShowSettings={setShowSettings}
          loading={loading}
          handleDeal={handleDeal}
          dealMode={dealMode}
          hands={hands}
          biddingStarted={biddingStarted}
          isBiddingComplete={isBiddingComplete}
          stopBidding={stopBidding}
          toggleStopBidding={toggleStopBidding}
          isNewDeal={isNewDeal}
          startBidding={startBidding}
          biddingRecords={biddingRecords}
          setHistoryDialogOpen={setHistoryDialogOpen}
          checkApiStatus={checkApiStatus}
          apiStatus={apiStatus}
          handleReloadJF={handleReloadJF}
          showUndo={showUndo}
          canUndo={canUndo}
          onUndo={undoBidding}
          showPlayPanel={showPlayPanel}
        />
      </Box>

      <Divider sx={{ my: 3, borderColor: 'rgba(0, 0, 0, 0.3)', borderBottomWidth: 2 }} />

      {/* 游戏设置 */}
      <SettingsPanel
        showSettings={showSettings}
        gameMode={gameMode}
        setGameMode={setGameMode}
        aiProvider={aiProvider}
        handleAIProviderChange={handleAIProviderChange}
        fallbackModel={fallbackModel}
        handleFallbackModelChange={handleFallbackModelChange}
        dealSystem={dealSystem}
        setDealSystem={setDealSystem}
        dealMode={dealMode}
        setDealMode={setDealMode}
        loading={loading}
        setCustomDealOpen={setCustomDealOpen}
        setImageDealOpen={setImageDealOpen}
        handleScreenshotDeal={handleScreenshotDeal}
      />

      {/* 错误提示 */}
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* 桌面版布局 */}
      {hands && (
        <Box sx={{ display: { xs: 'none', md: 'block' } }}>
          {/* 牌桌和右侧面板并排 */}
          <Box sx={{ display: 'flex', gap: 2, mb: 2, justifyContent: 'center' }}>
            <CardTablePanel
              isMobile={false}
              hands={hands}
              currentBidder={currentBidder}
              humanPosition={humanPosition}
              dealer={dealer}
              gameMode={gameMode}
              showPartnerHand={showPartnerHand}
              setShowPartnerHand={setShowPartnerHand}
              showAIHands={showAIHands}
              setShowAIHands={setShowAIHands}
              showOpponentHands={showOpponentHands}
              getPartnerPosition={getPartnerPosition}
              biddingSequence={biddingSequence}
              isBiddingComplete={isBiddingComplete}
              outputFormats={outputFormats}
              outputFormatsLoading={outputFormatsLoading}
              handleAnalyzeContract={handleAnalyzeContract}
              analyzeLoading={analyzeLoading}
              colorScheme={currentColorScheme}
              currentBiddingPosition={currentBiddingPosition}
              showDoubleDummy={showDoubleDummy}
              toggleDoubleDummy={toggleDoubleDummy}
              doubleDummyResult={doubleDummyResult}
              doubleDummyLoading={doubleDummyLoading}
              biddingTotalTime={biddingTotalTime}
              positionRoles={positionRoles}
              handlePositionRoleChange={handlePositionRoleChange}
              onDealerChange={(pos) => { 
                setDealer(pos); 
                setCurrentBidder(pos);
                setBiddingStarted(false);
                setStopBidding(false);
                setIsNewDeal(true);
                setBiddingSequence([]);
                setAiBiddingHistory([]);
                setPassedAIPositions(new Set());
                // 重置打牌相关状态
                setShowPlayPanel(false);
                setPlayState(null);
                setAiPlayHistory([]);
                setSelectedPlayCard(null);
                setIsPlayPaused(false);
              }}
              onClearAllHands={clearAllHands}
              setHands={setHands}
              biddingStarted={biddingStarted}
              stopBidding={stopBidding}
              startBidding={startBidding}
              playState={playState}
              showPlayPanel={showPlayPanel}
              declarer={isBiddingComplete() ? getFinalContract()?.declarer : null}
              lastCompletedTrick={lastCompletedTrick}
              isPlayPaused={isPlayPaused}
              aiLoading={playAiLoading}
              showPlayedCards={showPlayedCards}
              setShowPlayedCards={setShowPlayedCards}
            />
            
            {/* 右侧面板：叫牌细节或打牌面板 */}
            {showPlayPanel ? (
              <PlayDetailPanel
                isMobile={false}
                playState={playState}
                aiPlayHistory={aiPlayHistory}
                selectedCard={selectedPlayCard}
                onCardSelect={setSelectedPlayCard}
                onConfirmPlay={() => {
                  if (selectedPlayCard && playState?.current_player) {
                    handlePlayCard(playState.current_player, selectedPlayCard)
                    setSelectedPlayCard(null)
                  }
                }}
                loading={playLoading}
                aiLoading={playAiLoading}
                isPaused={isPlayPaused}
                onResume={handleResumePlay}
              />
            ) : (
              (humanPosition !== null || showAIBiddingOutput) && (
                <BiddingDetailPanel
                  isMobile={false}
                  humanPosition={humanPosition}
                  currentBidder={currentBidder}
                  isBiddingComplete={isBiddingComplete()}
                  showBiddingControls={showBiddingControls}
                  setShowBiddingControls={setShowBiddingControls}
                  simpleDisplayMode={simpleDisplayMode}
                  setSimpleDisplayMode={setSimpleDisplayMode}
                  aiBiddingHistory={aiBiddingHistory}
                  selectedBiddingIndex={selectedBiddingIndex}
                  setSelectedBiddingIndex={setSelectedBiddingIndex}
                  hands={hands}
                  gameMode={gameMode}
                  addBid={addBid}
                  getJFSuggestion={getJFSuggestion}
                  getFinalContract={getFinalContract}
                  bidSuggestion={bidSuggestion}
                  suggestionLoading={suggestionLoading}
                  stopBidding={stopBidding}
                  shouldAIAutoPass={shouldAIAutoPass}
                  customBidMeaning={customBidMeaning}
                  setCustomBidMeaning={setCustomBidMeaning}
                  outputFormats={outputFormats}
                  isBiddingCompleteFn={isBiddingComplete}
                  onStartPlay={handleStartPlay}
                  playLoading={playLoading}
                />
              )
            )}
          </Box>
        </Box>
      )}

      {/* 手机端布局 */}
      {hands && (
        <Box sx={{ display: { xs: 'block', md: 'none' } }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* 当前牌局面板 */}
            <CardTablePanel
              isMobile={true}
              hands={hands}
              currentBidder={currentBidder}
              humanPosition={humanPosition}
              dealer={dealer}
              gameMode={gameMode}
              showPartnerHand={showPartnerHand}
              setShowPartnerHand={setShowPartnerHand}
              showAIHands={showAIHands}
              setShowAIHands={setShowAIHands}
              showOpponentHands={showOpponentHands}
              getPartnerPosition={getPartnerPosition}
              biddingSequence={biddingSequence}
              isBiddingComplete={isBiddingComplete}
              outputFormats={outputFormats}
              outputFormatsLoading={outputFormatsLoading}
              handleAnalyzeContract={handleAnalyzeContract}
              analyzeLoading={analyzeLoading}
              colorScheme={currentColorScheme}
              currentBiddingPosition={currentBiddingPosition}
              showDoubleDummy={showDoubleDummy}
              toggleDoubleDummy={toggleDoubleDummy}
              doubleDummyResult={doubleDummyResult}
              doubleDummyLoading={doubleDummyLoading}
              biddingTotalTime={biddingTotalTime}
              positionRoles={positionRoles}
              handlePositionRoleChange={handlePositionRoleChange}
              onDealerChange={(pos) => { 
                setDealer(pos); 
                setCurrentBidder(pos);
                setBiddingStarted(false);
                setStopBidding(false);
                setIsNewDeal(true);
                setBiddingSequence([]);
                setAiBiddingHistory([]);
                setPassedAIPositions(new Set());
                // 重置打牌相关状态
                setShowPlayPanel(false);
                setPlayState(null);
                setAiPlayHistory([]);
                setSelectedPlayCard(null);
                setIsPlayPaused(false);
              }}
              onClearAllHands={clearAllHands}
              setHands={setHands}
              biddingStarted={biddingStarted}
              stopBidding={stopBidding}
              startBidding={startBidding}
              playState={playState}
              showPlayPanel={showPlayPanel}
              declarer={isBiddingComplete() ? getFinalContract()?.declarer : null}
              lastCompletedTrick={lastCompletedTrick}
              isPlayPaused={isPlayPaused}
              aiLoading={playAiLoading}
              showPlayedCards={showPlayedCards}
              setShowPlayedCards={setShowPlayedCards}
            />
            
            {/* 叫牌细节面板或打牌面板 */}
            {showPlayPanel ? (
              <PlayDetailPanel
                isMobile={true}
                playState={playState}
                aiPlayHistory={aiPlayHistory}
                selectedCard={selectedPlayCard}
                onCardSelect={setSelectedPlayCard}
                onConfirmPlay={() => {
                  if (selectedPlayCard && playState?.current_player) {
                    handlePlayCard(playState.current_player, selectedPlayCard)
                    setSelectedPlayCard(null)
                  }
                }}
                loading={playLoading}
                aiLoading={playAiLoading}
                isPaused={isPlayPaused}
                onResume={handleResumePlay}
                height="auto"
              />
            ) : (
              (humanPosition !== null || showAIBiddingOutput) && (
                <BiddingDetailPanel
                  isMobile={true}
                  humanPosition={humanPosition}
                  currentBidder={currentBidder}
                  isBiddingComplete={isBiddingComplete()}
                  showBiddingControls={showBiddingControls}
                  setShowBiddingControls={setShowBiddingControls}
                  simpleDisplayMode={simpleDisplayMode}
                  setSimpleDisplayMode={setSimpleDisplayMode}
                  aiBiddingHistory={aiBiddingHistory}
                  selectedBiddingIndex={selectedBiddingIndex}
                  setSelectedBiddingIndex={setSelectedBiddingIndex}
                  hands={hands}
                  gameMode={gameMode}
                  addBid={addBid}
                  getJFSuggestion={getJFSuggestion}
                  getFinalContract={getFinalContract}
                  bidSuggestion={bidSuggestion}
                  suggestionLoading={suggestionLoading}
                  stopBidding={stopBidding}
                  shouldAIAutoPass={shouldAIAutoPass}
                  customBidMeaning={customBidMeaning}
                  setCustomBidMeaning={setCustomBidMeaning}
                  outputFormats={outputFormats}
                  isBiddingCompleteFn={isBiddingComplete}
                  onStartPlay={handleStartPlay}
                  playLoading={playLoading}
                />
              )
            )}
          </Box>
        </Box>
      )}

      {/* 使用说明 */}
      {!hands && (
        <Paper elevation={1} sx={{ p: 3, mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            使用说明
          </Typography>
          <Typography variant="body1" component="div">
            <strong>开始练习：</strong><br />
            1. 点击"设置"选择叫牌模式（四人/双人）、发牌人位置和人类玩家位置<br />
            2. 点击"发牌"生成新牌局，或使用自定义牌局/图片识别功能<br />
            3. 人类回合时右侧面板显示叫牌按钮，AI回合自动叫牌<br />
            <br />
            <strong>界面说明：</strong><br />
            • 当前牌局：可切换显示小房子/叫牌结果，勾选显示AI手牌或队友手牌<br />
            • 叫牌细节：人类叫牌时显示JF约定片段作为参考
          </Typography>
        </Paper>
      )}

      {/* 历史记录对话框 */}
      <Dialog open={historyDialogOpen} onClose={() => setHistoryDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            叫牌历史记录
            {biddingRecords.length > 0 && (
              <Button size="small" onClick={toggleSelectAll}>
                {selectedRecordIds.size === biddingRecords.length ? '取消全选' : '全选'}
              </Button>
            )}
          </Box>
        </DialogTitle>
        <DialogContent dividers>
          {biddingRecords.length === 0 ? (
            <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
              暂无历史记录
            </Typography>
          ) : (
            <List>
              {biddingRecords.map((record, index) => (
                <Box key={record.id}>
                  {index > 0 && <Divider />}
                  <ListItem 
                    alignItems="flex-start" 
                    sx={{ 
                      flexDirection: 'column',
                      bgcolor: selectedRecordIds.has(record.id) ? 'action.selected' : 'inherit',
                      borderRadius: 1
                    }}
                    onClick={() => toggleRecordSelection(record.id)}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', width: '100%' }}>
                      <Checkbox
                        checked={selectedRecordIds.has(record.id)}
                        size="small"
                        sx={{ mt: 0.5 }}
                        onClick={(e) => e.stopPropagation()}
                        onChange={() => toggleRecordSelection(record.id)}
                      />
                      <Box sx={{ flex: 1 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                          <Typography variant="subtitle2">
                            {record.timestamp}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            发牌人: {record.dealer}家
                          </Typography>
                        </Box>
                        <Box sx={{ mt: 1 }}>
                          <Typography variant="body2">
                            <strong>定约:</strong> {record.finalContract ? `${record.finalContract.level}${record.finalContract.suit} (${record.finalContract.partnership} - ${record.finalContract.declarer}家)` : '全部Pass'}
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.5 }}>
                            <strong>叫牌序列:</strong> {record.biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')}
                          </Typography>
                          {record.note && (
                            <Typography variant="body2" sx={{ mt: 0.5, color: '#666' }}>
                              <strong>注释:</strong> {record.note}
                            </Typography>
                          )}
                        </Box>
                      </Box>
                    </Box>
                  </ListItem>
                </Box>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
          <Button 
            size="small" 
            disabled={selectedRecordIds.size !== 1}
            onClick={() => {
              const record = biddingRecords.find(r => selectedRecordIds.has(r.id))
              if (record) loadRecordToTable(record)
            }}
          >
            加载
          </Button>
          <Button 
            size="small" 
            disabled={selectedRecordIds.size !== 1}
            onClick={() => {
              const record = biddingRecords.find(r => selectedRecordIds.has(r.id))
              if (record) {
                setEditingRecordId(record.id)
                setEditingNote(record.note || '')
                setEditNoteDialogOpen(true)
              }
            }}
          >
            编辑注释
          </Button>
          <Button 
            size="small" 
            color="error"
            disabled={selectedRecordIds.size === 0}
            onClick={() => {
              const selectedRecords = biddingRecords.filter(r => selectedRecordIds.has(r.id))
              const hasNotes = selectedRecords.some(r => r.note && r.note.trim() !== '')
              if (hasNotes) {
                const noteCount = selectedRecords.filter(r => r.note && r.note.trim() !== '').length
                if (!window.confirm(`选中的记录中有 ${noteCount} 条包含注释，确定要删除吗？`)) {
                  return
                }
              }
              deleteBiddingRecords(Array.from(selectedRecordIds))
            }}
          >
            删除{selectedRecordIds.size > 0 && ` (${selectedRecordIds.size})`}
          </Button>
          <Box sx={{ flex: 1 }} />
          <Button component="label" size="small">
            导入
            <input type="file" accept=".json" hidden onChange={importRecords} />
          </Button>
          <Button onClick={exportRecords} disabled={biddingRecords.length === 0} size="small">
            导出{selectedRecordIds.size > 0 && ` (${selectedRecordIds.size})`}
          </Button>
          <Button onClick={() => {
            setHistoryDialogOpen(false)
            setSelectedRecordIds(new Set())
          }}>关闭</Button>
        </DialogActions>
      </Dialog>

      {/* 编辑注释对话框 */}
      <Dialog open={editNoteDialogOpen} onClose={() => setEditNoteDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>编辑注释</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="注释内容"
            fullWidth
            multiline
            rows={4}
            value={editingNote}
            onChange={(e) => setEditingNote(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditNoteDialogOpen(false)}>取消</Button>
          <Button onClick={() => {
            updateRecordNote(editingRecordId, editingNote)
            setEditNoteDialogOpen(false)
          }} variant="contained">
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 自定义牌局对话框 */}
      <Dialog open={customDealOpen} onClose={() => setCustomDealOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>输入自定义牌局</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            支持两种格式：<br />
            格式1 - 标准格式（按南西北东顺序，每行一家）：<br />
            K85 AT863 Q42 63<br />
            J73 72 8763 T954<br />
            QT94 5 KJT AQJ72<br />
            A62 KQJ94 A95 K8<br />
            <br />
            格式2 - Deep Finesse格式
          </Alert>
          <TextField
            multiline
            rows={8}
            fullWidth
            value={customDealText}
            onChange={(e) => setCustomDealText(e.target.value)}
            placeholder="请输入牌局..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCustomDealOpen(false)}>取消</Button>
          <Button onClick={async () => {
            if (customDealText.trim()) {
              await handleCustomDeal(customDealText)
              setCustomDealOpen(false)
              setCustomDealText('')
            }
          }} variant="contained" disabled={!customDealText.trim() || loading}>
            {loading ? <CircularProgress size={20} /> : '确定'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 图片牌局对话框 */}
      <Dialog open={imageDealOpen} onClose={() => setImageDealOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>从图片读取牌局</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            支持 jpg/png/gif/webp 格式的图片
          </Alert>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <TextField
              fullWidth
              value={imagePath}
              placeholder="请选择图片文件..."
              InputProps={{ readOnly: true }}
            />
            <Button
              variant="outlined"
              component="label"
              sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}
            >
              浏览...
              <input
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) {
                    setImagePath(file.name)
                    setImageFile(file)
                  }
                }}
              />
            </Button>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setImageDealOpen(false)
            setImagePath('')
            setImageFile(null)
          }}>取消</Button>
          <Button onClick={async () => {
            if (imageFile) {
              await handleImageDeal(imageFile)
              setImageDealOpen(false)
              setImagePath('')
              setImageFile(null)
            }
          }} variant="contained" disabled={!imageFile || loading}>
            {loading ? <CircularProgress size={20} /> : '确定'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}


export default App
