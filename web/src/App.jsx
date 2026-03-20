import { useState, useEffect, useRef } from 'react'
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
  Badge
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import HistoryIcon from '@mui/icons-material/History'
import { dealCards, healthCheck, aiBid, analyzeBidding, humanBid, getOutputFormats, analyzeContract, reloadJF, customDeal, imageDeal, screenshotDeal } from './services/api'
import HandDisplay from './components/HandDisplay'
import CardTable from './components/CardTable'
import BiddingControls from './components/BiddingControls'
import BiddingTable from './components/BiddingTable'
import AIOutputPanel from './components/AIOutputPanel'
import MobileDraggableContainer, { SortableItem } from './components/MobileDraggableContainer'
import './App.css'

const BIDDING_RECORDS_KEY = 'bridge_bidding_records'
const PANEL_ORDER_KEY = 'bridge_panel_order'
const DEFAULT_PANEL_ORDER = ['cardTable', 'biddingDetails', 'biddingControls', 'jfSuggestion']

function App() {
  const isLoadingRecordRef = useRef(false) // 用于标记是否正在加载历史记录（不触发保存）
  const [hands, setHands] = useState(null)
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
  
  // 面板顺序（手机端拖拽排序）
  const [panelOrder, setPanelOrder] = useState(() => {
    try {
      const saved = localStorage.getItem(PANEL_ORDER_KEY)
      return saved ? JSON.parse(saved) : DEFAULT_PANEL_ORDER
    } catch {
      return DEFAULT_PANEL_ORDER
    }
  })

  // 游戏设置
  const [gameMode, setGameMode] = useState('four') // 'four' 或 'pair'
  const [dealer, setDealer] = useState('南') // 发牌人位置
  const [humanPosition, setHumanPosition] = useState(null) // 人类玩家位置
  const [showPartnerHand, setShowPartnerHand] = useState(false) // 显示队友手牌
  const [showAIHands, setShowAIHands] = useState(false) // 显示AI手牌
  const [showOpponentHands, setShowOpponentHands] = useState(false) // 显示对方手牌
  const [biddingStarted, setBiddingStarted] = useState(false) // 叫牌是否已开始
  const [showAIBiddingOutput, setShowAIBiddingOutput] = useState(true) // 显示AI叫牌完整输出
  const [isNewDeal, setIsNewDeal] = useState(true) // 是否是新发牌
  const [stopBidding, setStopBidding] = useState(false) // 是否停止叫牌
  const [passedPartnership, setPassedPartnership] = useState(null) // 已连续pass的搭档（'南北' 或 '东西'）
  const [customBidMeaning, setCustomBidMeaning] = useState('') // 用户自定义叫牌含义
  const [useFallback, setUseFallback] = useState(false) // 是否使用备用提示词
  const [dealMode, setDealMode] = useState('free') // 发牌模式：free/game/slam
  const [showSettings, setShowSettings] = useState(false) // 显示设置面板
  
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
  const [customDealOpen, setCustomDealOpen] = useState(false) // 自定义牌局对话框
  const [imageDealOpen, setImageDealOpen] = useState(false) // 图片牌局对话框
  const [customDealText, setCustomDealText] = useState('') // 自定义牌局文本
  const [imagePath, setImagePath] = useState('') // 图片路径

  // 检查API状态
  useEffect(() => {
    checkApiStatus()
    loadBiddingRecords()
  }, [])

  // 保存面板顺序到localStorage
  useEffect(() => {
    localStorage.setItem(PANEL_ORDER_KEY, JSON.stringify(panelOrder))
  }, [panelOrder])

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
    setBiddingStarted(true)
    setHistoryDialogOpen(false)
    setOutputFormats(null) // 重置输出格式
    
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
      setPassedPartnership(null) // 重置已pass的搭档
      setUseFallback(false) // 重置备用提示词状态
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
        setPassedPartnership(null)
        setUseFallback(false)
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
  const handleImageDeal = async (imagePath) => {
    setLoading(true)
    setError(null)
    try {
      const data = await imageDeal(imagePath)
      if (data.success) {
        setHands(data.hands)
        setBiddingSequence([])
        setBidSuggestion(null)
        setAiBiddingHistory([])
        setCurrentBidder(dealer)
        setBiddingStarted(false)
        setIsNewDeal(true)
        setStopBidding(false)
        setPassedPartnership(null)
        setUseFallback(false)
      } else {
        setError(data.message || '图片识别失败')
      }
    } catch (err) {
      setError('图片识别失败，请检查API服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }

  // 从Edge浏览器截屏读取牌局
  const handleScreenshotDeal = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await screenshotDeal()
      if (data.success) {
        setHands(data.hands)
        setBiddingSequence([])
        setBidSuggestion(null)
        setAiBiddingHistory([])
        setCurrentBidder(dealer)
        setBiddingStarted(false)
        setIsNewDeal(true)
        setStopBidding(false)
        setPassedPartnership(null)
        setUseFallback(false)
      } else {
        setError(data.message || '截屏识别失败')
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
      // 重置叫牌序列
      setBiddingSequence([])
      setCurrentBidder(dealer) // 从发牌人开始叫牌
      setBiddingStarted(true) // 标记叫牌已开始
      setIsNewDeal(false) // 标记为非新发牌
      setAiBiddingHistory([]) // 清理上次叫牌输出
      setStopBidding(false) // 重置停止叫牌状态
      setPassedPartnership(null) // 重置已pass的搭档
    }
  }

  // 重新叫牌（保持当前牌局）
  const resetBidding = () => {
    setBiddingSequence([])
    setCurrentBidder(dealer)
    setBiddingStarted(false)
    setAiBiddingHistory([])
    setStopBidding(false)
    setPassedPartnership(null)
    setIsNewDeal(false)
  }

  // 切换停止/继续叫牌
  const toggleStopBidding = () => {
    setStopBidding(!stopBidding)
  }

  // 添加叫牌
  const addBid = async (bid) => {
    // 人类叫牌后，立即标记叫牌已开始（在currentBidder更新之前）
    if (humanPosition === currentBidder && !biddingStarted) {
      setBiddingStarted(true)
    }
    
    // 人类叫牌时，保存叫牌记录
    if (humanPosition === currentBidder) {
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      
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
        // 没有自定义含义，调用API获取
        setCurrentBiddingPosition(currentBidder)
        try {
          const result = await humanBid(biddingStr, currentBidder, bid)
          
          setAiBiddingHistory(prev => [...prev, {
            position: currentBidder,
            hand: hands[currentBidder],
            biddingSequence: biddingStr,
            result: { bid: result.bid, meaning: result.meaning },
            timestamp: new Date().toLocaleTimeString()
          }])
        } catch (err) {
          console.error('获取叫品含义失败:', err)
          setAiBiddingHistory(prev => [...prev, {
            position: currentBidder,
            hand: hands[currentBidder],
            biddingSequence: biddingStr,
            result: { bid: bid, meaning: '获取叫品含义失败' },
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
        return
      }
    }

    setBiddingSequence(newSequence)
    setCurrentBidder(nextBidder)
    
    // 四人模式：检查搭档两人是否相继pass（中间只有对方的一次叫牌或pass）
    // 前提：必须已有实质性叫牌（第一个实质性叫牌之前的pass不算）
    if (gameMode === 'four' && bid === 'pass' && !passedPartnership) {
      // 检查是否已有实质性叫牌
      const hasRealBid = biddingSequence.some(b => b.bid !== 'pass')
      if (!hasRealBid) {
        return
      }
      
      // 搭档关系
      const partnerships = { '南': '北', '北': '南', '东': '西', '西': '东' }
      const partnershipNames = { '南': '南北', '北': '南北', '东': '东西', '西': '东西' }
      
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
            console.log(`搭档${currentBidder}和${partner}相继pass，后续不再调用AI`)
            setPassedPartnership(partnershipNames[currentBidder])
          }
        }
      }
    }
  }

  // 检查位置是否属于已pass的搭档
  const isInPassedPartnership = (position) => {
    if (!passedPartnership) return false
    
    const partnershipPositions = {
      '南北': ['南', '北'],
      '东西': ['东', '西']
    }
    
    return partnershipPositions[passedPartnership]?.includes(position) || false
  }

  // 调用AI叫牌
  const callAIBid = async () => {
    if (!hands || !currentBidder || isBiddingComplete()) return
    
    // 检查是否停止叫牌
    if (stopBidding) return
    
    // 检查是否是人类玩家的回合
    if (humanPosition === currentBidder) return
    
    // 检查当前位置是否属于已pass的搭档，如果是则直接pass
    if (gameMode === 'four' && isInPassedPartnership(currentBidder)) {
      console.log(`${currentBidder}家和搭档都已pass，直接pass`)
      // 仍然需要添加到叫牌历史
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
      // 构建叫牌序列字符串
      const biddingStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-')
      
      // 构建累积的叫牌历史（与终端版格式一致）
      const bidHistory = aiBiddingHistory.map(record => 
        `\n(${record.position})${record.result.meaning}`
      ).join('')
      
      // 获取当前叫牌者的手牌
      const currentHand = hands[currentBidder]
      
      console.log(`AI叫牌: ${currentBidder}家, 手牌:`, currentHand, '叫牌序列:', biddingStr, '叫牌历史:', bidHistory)
      
      // 调用AI叫牌API
      const result = await aiBid(currentHand, biddingStr, currentBidder, '2D/2H/2S：自然阻击', bidHistory, useFallback)
      
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
      const result = await analyzeBidding(biddingStr, currentBidder)
      
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
    const isHumanTurn = humanPosition === currentBidder
    
    // 四人模式下，如果当前叫牌者属于已pass的搭档，自动pass
    if (gameMode === 'four' && isInPassedPartnership(currentBidder)) {
      if (isHumanTurn) {
        // 人类玩家属于已pass的搭档，自动添加pass
        console.log(`人类玩家${currentBidder}和搭档都已pass，自动pass`)
        setAiBiddingHistory(prev => [...prev, {
          position: currentBidder,
          hand: hands[currentBidder],
          biddingSequence: biddingSequence.map(b => `(${b.position})${b.bid}`).join('-'),
          result: { bid: 'pass', meaning: '搭档已相继pass，不再参与叫牌' },
          timestamp: new Date().toLocaleTimeString()
        }])
        addBid('pass')
      } else {
        // AI属于已pass的搭档
        callAIBid()
      }
      return
    }
    
    // 人类玩家回合时，获取JF约定片段
    if (isHumanTurn) {
      getJFSuggestion()
    }
    
    // AI叫牌逻辑
    if (!isHumanTurn && !stopBidding) {
      // AI回合
      if (humanPosition === null) {
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
  }, [currentBidder, humanPosition, hands, aiLoading, biddingSequence, biddingStarted, stopBidding, passedPartnership])

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
      const result = await getOutputFormats(hands, biddingStr, dealer, gameMode, humanPosition)
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

    biddingSequence.forEach((bid) => {
      const posIndex = positions.indexOf(bid.position)
      currentRow[posIndex] = bid.bid

      // 如果这一行满了（东家叫牌后），或者是最后一个叫品
      if (posIndex === 3) {
        rows.push([...currentRow])
        currentRow = Array(4).fill(null)
      }
    })

    // 添加未完成的最后一行
    if (currentRow.some(cell => cell !== null)) {
      rows.push([...currentRow])
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
            {positions.map((pos, colIndex) => (
              <span key={colIndex} className={`bidding-cell ${row[colIndex] ? 'has-bid' : ''}`}>
                {row[colIndex] === 'pass' ? 'P' : row[colIndex] || ''}
              </span>
            ))}
          </div>
        ))}
      </div>
    )
  }

  // 渲染牌桌
  const renderCardTable = () => {
    if (!hands) return null

    const north = hands['北']
    const south = hands['南']
    const east = hands['东']
    const west = hands['西']

    // 判断是否显示某个位置的手牌内容
    const shouldShowHandContent = (position) => {
      // 观察模式：显示所有手牌
      if (!humanPosition) {
        return true
      }

      // 人类玩家自己的牌总是显示
      if (position === humanPosition) {
        return true
      }

      // 四人模式
      if (gameMode === 'four') {
        // 其他玩家的牌根据showAIHands决定
        return showAIHands
      }

      // 双人模式
      if (gameMode === 'pair') {
        const partnerPosition = getPartnerPosition(humanPosition)
        
        // 队友的牌根据showPartnerHand决定
        if (position === partnerPosition) {
          return showPartnerHand
        }
        
        // 对方阵营的牌根据showOpponentHands决定
        return showOpponentHands
      }

      return true
    }

    return (
      <Box className="card-table-container">
        {/* 北家 */}
        <Box className="north-hand">
          <HandDisplay
            hand={north}
            position="北"
            isActive={currentBidder === '北'}
            isHuman={humanPosition === '北'}
            isDealer={dealer === '北'}
            isPartner={humanPosition && getPartnerPosition(humanPosition) === '北'}
            showContent={shouldShowHandContent('北')}
          />
        </Box>

        {/* 中间区域：西家 + 牌桌 + 东家 */}
        <Box className="middle-row">
          <Box className="west-hand">
            <HandDisplay
              hand={west}
              position="西"
              isActive={currentBidder === '西'}
              isHuman={humanPosition === '西'}
              isDealer={dealer === '西'}
              isPartner={humanPosition && getPartnerPosition(humanPosition) === '西'}
              showContent={shouldShowHandContent('西')}
            />
          </Box>

          <Box className="table-center">
            <div className="table-border">
              {renderBiddingTable()}
            </div>
          </Box>

          <Box className="east-hand">
            <HandDisplay
              hand={east}
              position="东"
              isActive={currentBidder === '东'}
              isHuman={humanPosition === '东'}
              isDealer={dealer === '东'}
              isPartner={humanPosition && getPartnerPosition(humanPosition) === '东'}
              showContent={shouldShowHandContent('东')}
            />
          </Box>
        </Box>

        {/* 南家 */}
        <Box className="south-hand">
          <HandDisplay
            hand={south}
            position="南"
            isActive={currentBidder === '南'}
            isHuman={humanPosition === '南'}
            isDealer={dealer === '南'}
            isPartner={humanPosition && getPartnerPosition(humanPosition) === '南'}
            showContent={shouldShowHandContent('南')}
          />
        </Box>
      </Box>
    )
  }

  return (
    <Box sx={{ display: 'block', width: '100%', py: { xs: 2, md: 4 }, px: { xs: 1, md: 3 } }}>
      <Typography variant="h4" component="h1" align="center" sx={{ fontSize: { xs: '1.5rem', md: '2rem' }, mb: 2 }}>
          桥牌叫牌练习系统
      </Typography>

      <Divider sx={{ mb: 3, borderColor: 'rgba(0, 0, 0, 0.3)', borderBottomWidth: 2 }} />

      {/* 控制按钮 */}
      <Box sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: { xs: 1, md: 2 }, alignItems: 'center' }}>
        <Button
          variant="outlined"
          size="large"
          onClick={() => setShowSettings(!showSettings)}
        >
          {showSettings ? '隐藏设置' : '显示设置'}
        </Button>

        <Button
          variant="contained"
          size="large"
          onClick={() => handleDeal(dealMode)}
          disabled={loading}
          startIcon={loading && <CircularProgress size={20} />}
        >
          {loading ? '发牌中...' : '发牌'}
        </Button>

        <Button
          variant="outlined"
          size="large"
          onClick={startBidding}
          disabled={!hands || (biddingStarted && !isBiddingComplete() && !stopBidding)}
        >
          {isNewDeal ? '开始叫牌' : '重新叫牌'}
        </Button>
        {biddingStarted && !isBiddingComplete() && (
          <Button
            variant={stopBidding ? "contained" : "outlined"}
            color={stopBidding ? "success" : "warning"}
            size="large"
            onClick={toggleStopBidding}
          >
            {stopBidding ? '继续叫牌' : '停止叫牌'}
          </Button>
        )}
        <Badge 
          badgeContent={biddingRecords.length} 
          color="primary"
          max={999}
          sx={{ '& .MuiBadge-badge': { fontSize: '0.7rem', height: '18px', minWidth: '18px' } }}
        >
          <Button
            variant="outlined"
            size="large"
            onClick={() => setHistoryDialogOpen(true)}
            startIcon={<HistoryIcon />}
          >
            历史记录
          </Button>
        </Badge>
        <Button
          variant="outlined"
          size="large"
          onClick={checkApiStatus}
          sx={apiStatus?.error ? { borderColor: 'error.main', color: 'error.main', '&:hover': { borderColor: 'error.dark' } } : {}}
        >
          检查API状态
        </Button>
        <Badge 
          badgeContent={apiStatus?.jf_segments_loaded || 0} 
          color="primary"
          max={999}
          sx={{ '& .MuiBadge-badge': { fontSize: '0.7rem', height: '18px', minWidth: '18px' } }}
        >
          <Button
            variant="outlined"
            size="large"
            onClick={handleReloadJF}
          >
            重新加载约定
          </Button>
        </Badge>
      </Box>

      <Divider sx={{ my: 3, borderColor: 'rgba(0, 0, 0, 0.3)', borderBottomWidth: 2 }} />

      {/* 游戏设置 */}
      {showSettings && (
      <Paper elevation={2} sx={{ p: { xs: 2, md: 3 }, mb: 3, width: '100%' }}>
        <Typography variant="h6" gutterBottom>
          叫牌设置
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, md: 3 }, alignItems: 'center', mb: 3 }}>
          <FormControl sx={{ minWidth: 120 }}>
            <InputLabel>叫牌模式</InputLabel>
            <Select
              value={gameMode}
              label="叫牌模式"
              onChange={(e) => setGameMode(e.target.value)}
              size="small"
            >
              <MenuItem value="four">四人叫牌</MenuItem>
              <MenuItem value="pair">双人叫牌</MenuItem>
            </Select>
          </FormControl>

          <FormControl sx={{ minWidth: 120 }}>
            <InputLabel>发牌人位置</InputLabel>
            <Select
              value={dealer}
              label="发牌人位置"
              onChange={(e) => {
                setDealer(e.target.value);
                setCurrentBidder(e.target.value);
              }}
              size="small"
            >
              <MenuItem value="南">南家</MenuItem>
              <MenuItem value="西">西家</MenuItem>
              <MenuItem value="北">北家</MenuItem>
              <MenuItem value="东">东家</MenuItem>
            </Select>
          </FormControl>

          <FormControl sx={{ minWidth: 150 }}>
            <InputLabel>人类玩家位置</InputLabel>
            <Select
              value={humanPosition === null ? 'observer' : humanPosition}
              label="人类玩家位置"
              onChange={(e) => {
                const value = e.target.value;
                setHumanPosition(value === 'observer' ? null : value);
              }}
              size="small"
            >
              <MenuItem value="observer">观察模式</MenuItem>
              <MenuItem value="南">南家</MenuItem>
              <MenuItem value="西">西家</MenuItem>
              <MenuItem value="北">北家</MenuItem>
              <MenuItem value="东">东家</MenuItem>
            </Select>
          </FormControl>

          {gameMode === 'pair' && humanPosition && (
            <FormControlLabel
              control={
                <Checkbox
                  checked={showPartnerHand}
                  onChange={(e) => setShowPartnerHand(e.target.checked)}
                  size="small"
                />
              }
              label="队友手牌"
            />
          )}

          {gameMode === 'four' && humanPosition && (
            <FormControlLabel
              control={
                <Checkbox
                  checked={showAIHands}
                  onChange={(e) => setShowAIHands(e.target.checked)}
                  size="small"
                />
              }
              label="AI手牌"
            />
          )}

          {gameMode === 'pair' && humanPosition && (
            <FormControlLabel
              control={
                <Checkbox
                  checked={showOpponentHands}
                  onChange={(e) => setShowOpponentHands(e.target.checked)}
                  size="small"
                />
              }
              label="对方手牌"
            />
          )}

          <FormControlLabel
            control={
              <Checkbox
                checked={showAIBiddingOutput}
                onChange={(e) => setShowAIBiddingOutput(e.target.checked)}
                size="small"
              />
            }
            label="AI叫牌完整输出"
          />
        </Box>

        <Divider sx={{ my: 2 }} />

        <Typography variant="h6" gutterBottom>
          发牌设置
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, md: 3 }, alignItems: 'center' }}>
          <FormControl sx={{ minWidth: 120 }}>
            <InputLabel>发牌模式</InputLabel>
            <Select
              value={dealMode}
              label="发牌模式"
              onChange={(e) => setDealMode(e.target.value)}
              size="small"
            >
              <MenuItem value="free">自由发牌</MenuItem>
              <MenuItem value="game">进局实力</MenuItem>
              <MenuItem value="slam">满贯实力</MenuItem>
            </Select>
          </FormControl>

          <Button
            variant="outlined"
            onClick={() => setCustomDealOpen(true)}
            disabled={loading}
          >
            输入自定义牌局
          </Button>

          <Button
            variant="outlined"
            onClick={() => setImageDealOpen(true)}
            disabled={loading}
          >
            从图片读取牌局
          </Button>

          <Button
            variant="outlined"
            onClick={handleScreenshotDeal}
            disabled={loading}
          >
            从Edge浏览器截屏
          </Button>
        </Box>
      </Paper>
      )}

      {/* 错误提示 */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* 桌面版布局 */}
      {hands && (
        <Box sx={{ display: { xs: 'none', md: 'block' } }}>
          {/* 牌桌和右侧面板并排 */}
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <Paper elevation={3} sx={{ 
              p: 1, 
              bgcolor: '#f5f5f5', 
              display: 'flex', 
              flexDirection: 'column', 
              flex: '0 0 auto',
              width: '700px',
              height: '750px'
            }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5, flexShrink: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Typography variant="h6">
                    当前牌局
                  </Typography>
                  <FormControlLabel
                    control={<Checkbox />}
                    label=""
                    sx={{ visibility: 'hidden', ml: 1 }}
                  />
                </Box>
                <FormControl size="small" sx={{ minWidth: 150, visibility: 'hidden' }}>
                  <InputLabel>占位</InputLabel>
                  <Select value="" label="占位">
                    <MenuItem value="">占位</MenuItem>
                  </Select>
                </FormControl>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1 }}>
                <CardTable
                  hands={hands}
                  currentBidder={currentBidder}
                  humanPosition={humanPosition}
                  dealer={dealer}
                  gameMode={gameMode}
                  showPartnerHand={showPartnerHand}
                  showAIHands={showAIHands}
                  showOpponentHands={showOpponentHands}
                  getPartnerPosition={getPartnerPosition}
                  renderBiddingTable={() => <BiddingTable biddingSequence={biddingSequence} dealer={dealer} />}
                />
              </Box>
            </Paper>
            
            {/* 右侧面板：根据showAIBiddingOutput显示不同内容 */}
            {showAIBiddingOutput ? (
              <Paper elevation={3} sx={{ 
                p: 1, 
                bgcolor: '#f5f5f5', 
                display: 'flex', 
                flexDirection: 'column', 
                flex: '1 1 auto',
                minWidth: 0,
                height: '750px'
              }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5, flexWrap: 'nowrap', gap: 1, flexShrink: 0 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <Typography variant="h6">
                      叫牌细节
                    </Typography>
                    <FormControlLabel
                      control={<Checkbox checked={simpleDisplayMode} onChange={(e) => setSimpleDisplayMode(e.target.checked)} />}
                      label="简单显示"
                      sx={{ ml: 1 }}
                    />
                  </Box>
                  {aiBiddingHistory.length > 0 && !simpleDisplayMode && (
                    <FormControl size="small" sx={{ minWidth: 150 }}>
                      <InputLabel>选择叫牌记录</InputLabel>
                      <Select
                        value={selectedBiddingIndex}
                        label="选择叫牌记录"
                        onChange={(e) => setSelectedBiddingIndex(e.target.value)}
                      >
                        <MenuItem value={-1}>最新 ({aiBiddingHistory[aiBiddingHistory.length - 1]?.position}家 - {aiBiddingHistory[aiBiddingHistory.length - 1]?.result.bid})</MenuItem>
                        {aiBiddingHistory.slice().reverse().slice(1).map((record, idx) => (
                          <MenuItem key={idx} value={aiBiddingHistory.length - 2 - idx}>
                            {record.position}家 - {record.result.bid}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  )}
                </Box>
                
                {currentBiddingPosition && (
                  <Alert severity="info" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }}>
                    <CircularProgress size={20} />
                    <Typography variant="body2">
                      {currentBiddingPosition}家正在叫牌...
                    </Typography>
                  </Alert>
                )}
                
                <Box sx={{ flex: 1, overflow: 'auto', p: 1, background: '#fafafa', borderRadius: 1, border: '1px solid #ddd', minHeight: 0 }}>
                {aiBiddingHistory.length === 0 ? (
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 4 }}>
                    等待AI叫牌...
                  </Typography>
                ) : simpleDisplayMode ? (
                  aiBiddingHistory.map((record, index) => (
                    <Box key={index} sx={{ mb: 1, p: 1.5, background: 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}>
                      <Typography variant="body2">
                        <strong>{record.position}家</strong> → <span style={{ color: '#d32f2f', fontWeight: 'bold' }}>{record.result.bid}</span>
                        {record.result.meaning && <span style={{ color: '#666' }}> ({record.result.meaning})</span>}
                      </Typography>
                    </Box>
                  ))
                ) : (
                  (() => {
                    const record = selectedBiddingIndex === -1 
                      ? aiBiddingHistory[aiBiddingHistory.length - 1] 
                      : aiBiddingHistory[selectedBiddingIndex]
                    if (!record) return null
                    const fullOutput = record.result.full_output || {}
                    return (
                      <Box sx={{ p: 2, background: 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                        <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 'bold', color: '#1976d2' }}>
                          {record.timestamp} - {record.position}家
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 1 }}>
                          <strong>手牌:</strong> {record.hand.display}
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 1 }}>
                          <strong>叫牌序列:</strong> {record.biddingSequence || '空（开叫位置）'}
                        </Typography>
                        
                        {fullOutput["自己pass次数"] && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            <strong>自己pass次数:</strong> {fullOutput["自己pass次数"]}
                          </Typography>
                        )}
                        {fullOutput["JF约定"] && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            <strong>JF约定:</strong> {fullOutput["JF约定"]}
                          </Typography>
                        )}
                        {fullOutput["叫牌位置"] && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            <strong>叫牌位置:</strong> {fullOutput["叫牌位置"]}
                          </Typography>
                        )}
                        {fullOutput["手牌分析"] && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            <strong>手牌分析:</strong>
                            <Box component="pre" sx={{ 
                              mt: 0.5, 
                              p: 1, 
                              background: '#f8f9fa', 
                              borderRadius: 1,
                              fontSize: '0.85rem',
                              lineHeight: 1.4,
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                              border: '1px solid #e9ecef',
                              maxHeight: '150px',
                              overflow: 'auto'
                            }}>
                              {fullOutput["手牌分析"]}
                            </Box>
                          </Typography>
                        )}
                        {fullOutput["叫牌历史"] && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            <strong>叫牌历史:</strong>
                            <Box component="pre" sx={{ 
                              mt: 0.5, 
                              p: 1, 
                              background: '#f8f9fa', 
                              borderRadius: 1,
                              fontSize: '0.85rem',
                              lineHeight: 1.4,
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                              border: '1px solid #e9ecef',
                              maxHeight: '150px',
                              overflow: 'auto'
                            }}>
                              {fullOutput["叫牌历史"]}
                            </Box>
                          </Typography>
                        )}
                        
                        <Typography variant="body2" sx={{ mt: 1 }}>
                          <strong>选定叫品:</strong> <span style={{ fontWeight: 'bold', color: '#d32f2f' }}>{record.result.bid}</span>
                        </Typography>
                        {record.result.meaning && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            <strong>叫品含义:</strong> {record.result.meaning}
                          </Typography>
                        )}
                        {record.result.selection_process && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            <strong>叫品筛选过程:</strong>
                            <Box component="pre" sx={{ 
                              mt: 1, 
                              p: 1, 
                              background: '#f8f9fa', 
                              borderRadius: 1,
                              fontSize: '0.85rem',
                              lineHeight: 1.4,
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                              border: '1px solid #e9ecef',
                              maxHeight: '200px',
                              overflow: 'auto'
                            }}>
                              {record.result.selection_process}
                            </Box>
                          </Typography>
                        )}
                        {fullOutput["完整叫牌序列"] && (
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            <strong>完整叫牌序列:</strong> {fullOutput["完整叫牌序列"]}
                          </Typography>
                        )}
                      </Box>
                    )
                  })()
                )}
                </Box>
              </Paper>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, flex: '1 1 auto', minWidth: 0, height: '750px' }}>
                <BiddingControls
                  hands={hands}
                  currentBidder={currentBidder}
                  humanPosition={humanPosition}
                  gameMode={gameMode}
                  checkBiddingComplete={isBiddingComplete}
                  addBid={addBid}
                  getJFSuggestion={getJFSuggestion}
                  getFinalContract={getFinalContract}
                  bidSuggestion={bidSuggestion}
                  suggestionLoading={suggestionLoading}
                  aiLoading={aiLoading}
                  stopBidding={stopBidding}
                  isInPassedPartnership={isInPassedPartnership}
                  customBidMeaning={customBidMeaning}
                  setCustomBidMeaning={setCustomBidMeaning}
                  outputFormats={outputFormats}
                  outputFormatsLoading={outputFormatsLoading}
                  handleAnalyzeContract={handleAnalyzeContract}
                  analyzeLoading={analyzeLoading}
                  isVerticalLayout={true}
                />
              </Box>
            )}
          </Box>
          
          {/* 叫牌控制（包含JF约定片段和更多格式面板）- 仅在显示叫牌细节时显示 */}
          {showAIBiddingOutput && (
            <Box sx={{ display: 'flex', gap: 2 }}>
              <BiddingControls
                hands={hands}
                currentBidder={currentBidder}
                humanPosition={humanPosition}
                gameMode={gameMode}
                checkBiddingComplete={isBiddingComplete}
                addBid={addBid}
                getJFSuggestion={getJFSuggestion}
                getFinalContract={getFinalContract}
                bidSuggestion={bidSuggestion}
                suggestionLoading={suggestionLoading}
                aiLoading={aiLoading}
                stopBidding={stopBidding}
                isInPassedPartnership={isInPassedPartnership}
                customBidMeaning={customBidMeaning}
                setCustomBidMeaning={setCustomBidMeaning}
                outputFormats={outputFormats}
                outputFormatsLoading={outputFormatsLoading}
                handleAnalyzeContract={handleAnalyzeContract}
                analyzeLoading={analyzeLoading}
              />
            </Box>
          )}
        </Box>
      )}

      {/* 手机端可拖拽面板容器 */}
      {hands && (
        <Box sx={{ display: { xs: 'block', md: 'none' } }}>
          <MobileDraggableContainer 
            panelOrder={panelOrder} 
            onReorder={setPanelOrder}
          >
            {panelOrder.map((panelId) => {
              if (panelId === 'cardTable') {
                return (
                  <SortableItem key={panelId} id={panelId}>
                    <Paper elevation={3} sx={{ 
                      p: 1, 
                      bgcolor: '#f5f5f5', 
                      display: 'flex', 
                      flexDirection: 'column', 
                      width: '100%',
                      minHeight: '400px'
                    }}>
                      <Typography variant="h6" gutterBottom align="center">
                        当前牌局
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1 }}>
                        <CardTable
                          hands={hands}
                          currentBidder={currentBidder}
                          humanPosition={humanPosition}
                          dealer={dealer}
                          gameMode={gameMode}
                          showPartnerHand={showPartnerHand}
                          showAIHands={showAIHands}
                          showOpponentHands={showOpponentHands}
                          getPartnerPosition={getPartnerPosition}
                          renderBiddingTable={() => <BiddingTable biddingSequence={biddingSequence} dealer={dealer} />}
                        />
                      </Box>
                    </Paper>
                  </SortableItem>
                )
              }
              if (panelId === 'biddingDetails' && showAIBiddingOutput) {
                return (
                  <SortableItem key={panelId} id={panelId}>
                    <Paper elevation={3} sx={{ 
                      p: 1, 
                      bgcolor: '#f5f5f5', 
                      display: 'flex', 
                      flexDirection: 'column', 
                      width: '100%',
                      height: '400px'
                    }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1, flexShrink: 0 }}>
                        <Typography variant="h6">
                          叫牌细节
                        </Typography>
                        <FormControlLabel
                          control={<Checkbox checked={simpleDisplayMode} onChange={(e) => setSimpleDisplayMode(e.target.checked)} />}
                          label="简单显示"
                          sx={{ ml: 1 }}
                        />
                      </Box>
                      
                      {aiBiddingHistory.length > 0 && !simpleDisplayMode && (
                        <FormControl size="small" sx={{ mb: 2, minWidth: 200, flexShrink: 0 }}>
                          <InputLabel>选择叫牌记录</InputLabel>
                          <Select
                            value={selectedBiddingIndex}
                            label="选择叫牌记录"
                            onChange={(e) => setSelectedBiddingIndex(e.target.value)}
                          >
                            <MenuItem value={-1}>最新 ({aiBiddingHistory[aiBiddingHistory.length - 1]?.position}家 - {aiBiddingHistory[aiBiddingHistory.length - 1]?.result.bid})</MenuItem>
                            {aiBiddingHistory.slice().reverse().slice(1).map((record, idx) => (
                              <MenuItem key={idx} value={aiBiddingHistory.length - 2 - idx}>
                                {record.position}家 - {record.result.bid}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      )}
                      
                      {currentBiddingPosition && (
                        <Alert severity="info" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }}>
                          <CircularProgress size={20} />
                          <Typography variant="body2">
                            {currentBiddingPosition}家正在叫牌...
                          </Typography>
                        </Alert>
                      )}
                      
                      <Box sx={{ flex: 1, overflow: 'auto', p: 1, background: '#fafafa', borderRadius: 1, border: '1px solid #ddd', minHeight: 0 }}>
                      {aiBiddingHistory.length === 0 ? (
                        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 4 }}>
                          等待AI叫牌...
                        </Typography>
                      ) : simpleDisplayMode ? (
                        aiBiddingHistory.map((record, index) => (
                          <Box key={index} sx={{ mb: 1, p: 1.5, background: 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}>
                            <Typography variant="body2">
                              <strong>{record.position}家</strong> → <span style={{ color: '#d32f2f', fontWeight: 'bold' }}>{record.result.bid}</span>
                              {record.result.meaning && <span style={{ color: '#666' }}> ({record.result.meaning})</span>}
                            </Typography>
                          </Box>
                        ))
                      ) : (
                        (() => {
                          const record = selectedBiddingIndex === -1 
                            ? aiBiddingHistory[aiBiddingHistory.length - 1] 
                            : aiBiddingHistory[selectedBiddingIndex]
                          if (!record) return null
                          const fullOutput = record.result.full_output || {}
                          return (
                            <Box sx={{ p: 2, background: 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                              <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 'bold', color: '#1976d2' }}>
                                {record.timestamp} - {record.position}家
                              </Typography>
                              <Typography variant="body2" sx={{ mt: 1 }}>
                                <strong>手牌:</strong> {record.hand.display}
                              </Typography>
                              <Typography variant="body2" sx={{ mt: 1 }}>
                                <strong>叫牌序列:</strong> {record.biddingSequence || '空（开叫位置）'}
                              </Typography>
                              
                              {fullOutput["自己pass次数"] && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>自己pass次数:</strong> {fullOutput["自己pass次数"]}
                                </Typography>
                              )}
                              {fullOutput["JF约定"] && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>JF约定:</strong> {fullOutput["JF约定"]}
                                </Typography>
                              )}
                              {fullOutput["叫牌位置"] && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>叫牌位置:</strong> {fullOutput["叫牌位置"]}
                                </Typography>
                              )}
                              {fullOutput["手牌分析"] && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>手牌分析:</strong>
                                  <Box component="pre" sx={{ 
                                    mt: 0.5, 
                                    p: 1, 
                                    background: '#f8f9fa', 
                                    borderRadius: 1,
                                    fontSize: '0.85rem',
                                    lineHeight: 1.4,
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    border: '1px solid #e9ecef',
                                    maxHeight: '150px',
                                    overflow: 'auto'
                                  }}>
                                    {fullOutput["手牌分析"]}
                                  </Box>
                                </Typography>
                              )}
                              {fullOutput["叫牌历史"] && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>叫牌历史:</strong>
                                  <Box component="pre" sx={{ 
                                    mt: 0.5, 
                                    p: 1, 
                                    background: '#f8f9fa', 
                                    borderRadius: 1,
                                    fontSize: '0.85rem',
                                    lineHeight: 1.4,
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    border: '1px solid #e9ecef',
                                    maxHeight: '150px',
                                    overflow: 'auto'
                                  }}>
                                    {fullOutput["叫牌历史"]}
                                  </Box>
                                </Typography>
                              )}
                              
                              <Typography variant="body2" sx={{ mt: 1 }}>
                                <strong>选定叫品:</strong> <span style={{ fontWeight: 'bold', color: '#d32f2f' }}>{record.result.bid}</span>
                              </Typography>
                              {record.result.meaning && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>叫品含义:</strong> {record.result.meaning}
                                </Typography>
                              )}
                              {record.result.selection_process && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>叫品筛选过程:</strong>
                                  <Box component="pre" sx={{ 
                                    mt: 1, 
                                    p: 1, 
                                    background: '#f8f9fa', 
                                    borderRadius: 1,
                                    fontSize: '0.85rem',
                                    lineHeight: 1.4,
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    border: '1px solid #e9ecef',
                                    maxHeight: '200px',
                                    overflow: 'auto'
                                  }}>
                                    {record.result.selection_process}
                                  </Box>
                                </Typography>
                              )}
                              {fullOutput["完整叫牌序列"] && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>完整叫牌序列:</strong> {fullOutput["完整叫牌序列"]}
                                </Typography>
                              )}
                            </Box>
                          )
                        })()
                      )}
                      </Box>
                    </Paper>
                  </SortableItem>
                )
              }
              if (panelId === 'biddingControls') {
                return (
                  <SortableItem key={panelId} id={panelId}>
                    <BiddingControls
                      hands={hands}
                      currentBidder={currentBidder}
                      humanPosition={humanPosition}
                      gameMode={gameMode}
                      checkBiddingComplete={isBiddingComplete}
                      addBid={addBid}
                      getJFSuggestion={getJFSuggestion}
                      getFinalContract={getFinalContract}
                      bidSuggestion={bidSuggestion}
                      suggestionLoading={suggestionLoading}
                      aiLoading={aiLoading}
                      stopBidding={stopBidding}
                      isInPassedPartnership={isInPassedPartnership}
                      customBidMeaning={customBidMeaning}
                      setCustomBidMeaning={setCustomBidMeaning}
                      outputFormats={outputFormats}
                      outputFormatsLoading={outputFormatsLoading}
                      handleAnalyzeContract={handleAnalyzeContract}
                      analyzeLoading={analyzeLoading}
                    />
                  </SortableItem>
                )
              }
              return null
            })}
          </MobileDraggableContainer>
        </Box>
      )}

      {/* 使用说明 */}
      {!hands && (
        <Paper elevation={1} sx={{ p: 3, mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            使用说明
          </Typography>
          <Typography variant="body1">
            1. 在游戏设置中选择叫牌模式、发牌人位置和人类玩家位置<br />
            2. 四人模式下可选择是否显示AI手牌<br />
            3. 双人模式下可选择是否显示队友手牌和对方手牌<br />
            4. 点击"发牌"按钮生成新的牌局<br />
            5. 在牌桌中心查看叫牌过程（带*的为发牌人）<br />
            6. 使用叫牌控制面板进行叫牌（人类玩家回合时可用）
          </Typography>
        </Paper>
      )}

      {/* 历史记录对话框 */}
      <Dialog open={historyDialogOpen} onClose={() => setHistoryDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>叫牌历史记录</DialogTitle>
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
                  <ListItem alignItems="flex-start" sx={{ flexDirection: 'column' }}>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                          <Typography variant="subtitle2">
                            {record.timestamp}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            发牌人: {record.dealer}家
                          </Typography>
                        </Box>
                      }
                      secondary={
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
                      }
                    />
                    <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                      <Button size="small" variant="outlined" onClick={() => loadRecordToTable(record)}>
                        加载
                      </Button>
                      <Button size="small" variant="outlined" onClick={() => {
                        setEditingRecordId(record.id)
                        setEditingNote(record.note || '')
                        setEditNoteDialogOpen(true)
                      }}>
                        编辑注释
                      </Button>
                      <Button size="small" variant="outlined" color="error" onClick={() => deleteBiddingRecord(record.id)}>
                        删除
                      </Button>
                    </Box>
                  </ListItem>
                </Box>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHistoryDialogOpen(false)}>关闭</Button>
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
          <TextField
            fullWidth
            value={imagePath}
            onChange={(e) => setImagePath(e.target.value)}
            placeholder="请输入图片文件路径..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImageDealOpen(false)}>取消</Button>
          <Button onClick={async () => {
            if (imagePath.trim()) {
              await handleImageDeal(imagePath)
              setImageDealOpen(false)
              setImagePath('')
            }
          }} variant="contained" disabled={!imagePath.trim() || loading}>
            {loading ? <CircularProgress size={20} /> : '确定'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}


export default App
