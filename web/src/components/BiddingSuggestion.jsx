import { useState } from 'react'
import {
  Box,
  Paper,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  IconButton,
  Collapse,
  Alert,
  CircularProgress,
  Grid,
  Divider,
  Card,
  CardContent
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import AddIcon from '@mui/icons-material/Add'
import CameraAltIcon from '@mui/icons-material/CameraAlt'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import { triggerScreenshot, readClipboardDeal, getBiddingSuggestion } from '../services/api'

const SUITS = ['♠', '♥', '♦', '♣']
const SUIT_NAMES = { '♠': 'spades', '♥': 'hearts', '♦': 'diamonds', '♣': 'clubs' }
const POSITIONS = ['南', '西', '北', '东']
const ALL_BIDS = [
  'pass', 'X', 'XX',
  '1C', '1D', '1H', '1S', '1NT',
  '2C', '2D', '2H', '2S', '2NT',
  '3C', '3D', '3H', '3S', '3NT',
  '4C', '4D', '4H', '4S', '4NT',
  '5C', '5D', '5H', '5S', '5NT',
  '6C', '6D', '6H', '6S', '6NT',
  '7C', '7D', '7H', '7S', '7NT'
]

function BiddingSuggestion() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  const [handInput, setHandInput] = useState('')
  const [handCards, setHandCards] = useState({ spades: '', hearts: '', diamonds: '', clubs: '' })
  const [inputMode, setInputMode] = useState('text')
  
  const [biddingSequence, setBiddingSequence] = useState([])
  const [currentBidder, setCurrentBidder] = useState('南')
  const [selectedBid, setSelectedBid] = useState('')
  
  const dealer = biddingSequence.length > 0 ? biddingSequence[0].position : '南'
  
  const [suggestion, setSuggestion] = useState(null)
  const [showFullAnalysis, setShowFullAnalysis] = useState(false)
  
  const parseTextHand = (text) => {
    const result = { spades: '', hearts: '', diamonds: '', clubs: '' }
    const parts = text.trim().split(/\s+/)
    
    for (const part of parts) {
      if (part.startsWith('♠') || part.toUpperCase().startsWith('S')) {
        result.spades = part.replace(/^[♠S]/i, '').toUpperCase()
      } else if (part.startsWith('♥') || part.toUpperCase().startsWith('H')) {
        result.hearts = part.replace(/^[♥H]/i, '').toUpperCase()
      } else if (part.startsWith('♦') || part.toUpperCase().startsWith('D')) {
        result.diamonds = part.replace(/^[♦D]/i, '').toUpperCase()
      } else if (part.startsWith('♣') || part.toUpperCase().startsWith('C')) {
        result.clubs = part.replace(/^[♣C]/i, '').toUpperCase()
      }
    }
    
    return result
  }
  
  const handleHandInputChange = (e) => {
    const text = e.target.value
    setHandInput(text)
    setHandCards(parseTextHand(text))
  }
  
  const handleCardChange = (suit, value) => {
    const newCards = { ...handCards, [suit]: value.toUpperCase() }
    setHandCards(newCards)
    const text = Object.entries(newCards)
      .filter(([_, v]) => v)
      .map(([k, v]) => {
        const suitSymbol = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }[k]
        return `${suitSymbol}${v}`
      })
      .join(' ')
    setHandInput(text)
  }
  
  const handleScreenshot = async () => {
    setLoading(true)
    setError(null)
    
    try {
      await triggerScreenshot()
      
      await new Promise(resolve => setTimeout(resolve, 5000))
      
      const result = await readClipboardDeal()
      
      if (result.success) {
        if (result.hands && result.hands['南']) {
          const southHand = result.hands['南']
          const text = `♠${southHand.spades} ♥${southHand.hearts} ♦${southHand.diamonds} ♣${southHand.clubs}`
          setHandInput(text)
          setHandCards({
            spades: southHand.spades,
            hearts: southHand.hearts,
            diamonds: southHand.diamonds,
            clubs: southHand.clubs
          })
        }
        
        if (result.bidding_sequence) {
          const seq = parseBiddingSequence(result.bidding_sequence)
          setBiddingSequence(seq)
          if (seq.length > 0) {
            const lastPos = seq[seq.length - 1].position
            const nextIdx = POSITIONS.indexOf(lastPos)
            setCurrentBidder(POSITIONS[(nextIdx + 1) % 4])
          }
        }
      } else {
        setError(result.message || '识别失败')
      }
    } catch (err) {
      setError('截屏识别失败: ' + err.message)
    } finally {
      setLoading(false)
    }
  }
  
  const parseBiddingSequence = (seqStr) => {
    const result = []
    const regex = /\(([^)]+)\)([^-(]+)/g
    let match
    
    while ((match = regex.exec(seqStr)) !== null) {
      result.push({
        position: match[1],
        bid: match[2].trim()
      })
    }
    
    return result
  }
  
  const addBid = () => {
    if (!selectedBid) return
    
    setBiddingSequence([...biddingSequence, { position: currentBidder, bid: selectedBid }])
    
    const nextIdx = POSITIONS.indexOf(currentBidder)
    setCurrentBidder(POSITIONS[(nextIdx + 1) % 4])
    setSelectedBid('')
  }
  
  const removeBid = (index) => {
    const newSeq = biddingSequence.filter((_, i) => i !== index)
    setBiddingSequence(newSeq)
    
    if (newSeq.length > 0) {
      const lastPos = newSeq[newSeq.length - 1].position
      const nextIdx = POSITIONS.indexOf(lastPos)
      setCurrentBidder(POSITIONS[(nextIdx + 1) % 4])
    } else {
      setCurrentBidder('南')
    }
  }
  
  const clearAll = () => {
    setHandInput('')
    setHandCards({ spades: '', hearts: '', diamonds: '', clubs: '' })
    setBiddingSequence([])
    setCurrentBidder('南')
    setSelectedBid('')
    setSuggestion(null)
    setError(null)
  }
  
  const getSuggestion = async () => {
    const totalCards = Object.values(handCards).reduce((sum, v) => sum + v.length, 0)
    if (totalCards !== 13) {
      setError('手牌必须正好13张')
      return
    }
    
    setLoading(true)
    setError(null)
    setSuggestion(null)
    
    try {
      const handStr = `♠${handCards.spades} ♥${handCards.hearts} ♦${handCards.diamonds} ♣${handCards.clubs}`
      const seqStr = biddingSequence.map(b => `(${b.position})${b.bid}`).join('-') + '-'
      
      const result = await getBiddingSuggestion(handStr, seqStr, currentBidder, dealer)
      
      if (result.bid) {
        setSuggestion(result)
      } else {
        setError(result.meaning || '获取建议失败')
      }
    } catch (err) {
      setError('获取建议失败: ' + err.message)
    } finally {
      setLoading(false)
    }
  }
  
  const formatBiddingSequence = () => {
    if (biddingSequence.length === 0) return '无'
    return biddingSequence.map(b => `(${b.position})${b.bid}`).join('-') + '-'
  }
  
  return (
    <Box sx={{ p: 2, maxWidth: 800, mx: 'auto' }}>
      <Paper sx={{ p: 3, mb: 2 }}>
        <Typography variant="h5" gutterBottom>
          叫牌建议
        </Typography>
        
        <Box sx={{ mb: 3 }}>
          <Button
            variant="contained"
            startIcon={loading ? <CircularProgress size={20} /> : <CameraAltIcon />}
            onClick={handleScreenshot}
            disabled={loading}
            sx={{ mr: 2 }}
          >
            截屏识别
          </Button>
          <Button variant="outlined" onClick={clearAll}>
            清空
          </Button>
        </Box>
        
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        
        <Divider sx={{ my: 2 }} />
        
        <Typography variant="h6" gutterBottom>
          手牌输入
        </Typography>
        
        <Box sx={{ mb: 2 }}>
          <Chip
            label="文本输入"
            color={inputMode === 'text' ? 'primary' : 'default'}
            onClick={() => setInputMode('text')}
            sx={{ mr: 1 }}
          />
          <Chip
            label="点选花色"
            color={inputMode === 'cards' ? 'primary' : 'default'}
            onClick={() => setInputMode('cards')}
          />
        </Box>
        
        {inputMode === 'text' ? (
          <TextField
            fullWidth
            label="手牌（如：♠AK65 ♥KQ2 ♦J874 ♣93）"
            value={handInput}
            onChange={handleHandInputChange}
            placeholder="♠AK65 ♥KQ2 ♦J874 ♣93"
            sx={{ mb: 2 }}
          />
        ) : (
          <Grid container spacing={2} sx={{ mb: 2 }}>
            {Object.entries(handCards).map(([suit, cards]) => {
              const suitSymbol = { spades: '♠', hearts: '♥', diamonds: '♦', clubs: '♣' }[suit]
              const suitColor = (suit === 'hearts' || suit === 'diamonds') ? '#d32f2f' : '#000'
              
              return (
                <Grid item xs={6} sm={3} key={suit}>
                  <TextField
                    fullWidth
                    label={`${suitSymbol} 花色`}
                    value={cards}
                    onChange={(e) => handleCardChange(suit, e.target.value)}
                    InputProps={{
                      style: { color: suitColor }
                    }}
                    InputLabelProps={{
                      style: { color: suitColor }
                    }}
                  />
                </Grid>
              )
            })}
          </Grid>
        )}
        
        <Typography variant="body2" color="text.secondary">
          当前手牌: {Object.values(handCards).reduce((sum, v) => sum + v.length, 0)} 张
          {Object.values(handCards).reduce((sum, v) => sum + v.length, 0) !== 13 && (
            <Typography component="span" color="error"> (需要13张)</Typography>
          )}
        </Typography>
        
        <Divider sx={{ my: 2 }} />
        
        <Typography variant="h6" gutterBottom>
          叫牌序列
        </Typography>
        
        <Box sx={{ mb: 2, p: 2, bgcolor: 'grey.100', borderRadius: 1 }}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            当前序列: {formatBiddingSequence()}
          </Typography>
          
          {biddingSequence.length > 0 && (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
              {biddingSequence.map((b, index) => (
                <Chip
                  key={index}
                  label={`${b.position}:${b.bid}`}
                  onDelete={() => removeBid(index)}
                  size="small"
                />
              ))}
            </Box>
          )}
          
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <FormControl size="small" sx={{ minWidth: 80 }}>
              <InputLabel>位置</InputLabel>
              <Select
                value={currentBidder}
                label="位置"
                onChange={(e) => setCurrentBidder(e.target.value)}
              >
                {POSITIONS.map(pos => (
                  <MenuItem key={pos} value={pos}>{pos}</MenuItem>
                ))}
              </Select>
            </FormControl>
            
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>叫品</InputLabel>
              <Select
                value={selectedBid}
                label="叫品"
                onChange={(e) => setSelectedBid(e.target.value)}
              >
                {ALL_BIDS.map(bid => (
                  <MenuItem key={bid} value={bid}>{bid}</MenuItem>
                ))}
              </Select>
            </FormControl>
            
            <IconButton onClick={addBid} disabled={!selectedBid} color="primary">
              <AddIcon />
            </IconButton>
          </Box>
        </Box>
        
        <Divider sx={{ my: 2 }} />
        
        <Button
          variant="contained"
          color="primary"
          fullWidth
          onClick={getSuggestion}
          disabled={loading || Object.values(handCards).reduce((sum, v) => sum + v.length, 0) !== 13}
        >
          {loading ? <CircularProgress size={24} /> : '获取叫牌建议'}
        </Button>
      </Paper>
      
      {suggestion && (
        <Paper sx={{ p: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6">
              建议叫品: <Chip label={suggestion.bid} color="primary" size="large" />
            </Typography>
            <Button
              size="small"
              endIcon={showFullAnalysis ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              onClick={() => setShowFullAnalysis(!showFullAnalysis)}
            >
              {showFullAnalysis ? '收起分析' : '展开分析'}
            </Button>
          </Box>
          
          {suggestion.meaning && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {suggestion.meaning}
            </Alert>
          )}
          
          <Collapse in={showFullAnalysis}>
            {suggestion.full_output && (
              <Card variant="outlined" sx={{ mt: 2 }}>
                <CardContent>
                  <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 'bold', color: '#1976d2' }}>
                    完整分析
                  </Typography>
                  
                  {suggestion.full_output["自己pass次数"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>自己pass次数:</strong> {suggestion.full_output["自己pass次数"]}
                    </Typography>
                  )}
                  {suggestion.full_output["当前叫牌序列"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>当前叫牌序列:</strong> {suggestion.full_output["当前叫牌序列"]}
                    </Typography>
                  )}
                  {suggestion.full_output["JF约定"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>JF约定:</strong> {suggestion.full_output["JF约定"]}
                    </Typography>
                  )}
                  {suggestion.full_output["叫牌位置"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>叫牌位置:</strong> {suggestion.full_output["叫牌位置"]}
                    </Typography>
                  )}
                  {suggestion.full_output["手牌分析"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>手牌分析:</strong>
                      <Box component="pre" sx={{
                        mt: 0.5, p: 1, background: '#f8f9fa', borderRadius: 1,
                        fontSize: '0.85rem', lineHeight: 1.4, whiteSpace: 'pre-wrap',
                        border: '1px solid #e9ecef', maxHeight: '150px', overflow: 'auto',
                      }}>
                        {suggestion.full_output["手牌分析"]}
                      </Box>
                    </Typography>
                  )}
                  {suggestion.full_output["叫牌历史"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>叫牌历史:</strong>
                      <Box component="pre" sx={{
                        mt: 0.5, p: 1, background: '#f8f9fa', borderRadius: 1,
                        fontSize: '0.85rem', lineHeight: 1.4, whiteSpace: 'pre-wrap',
                        border: '1px solid #e9ecef', maxHeight: '150px', overflow: 'auto',
                      }}>
                        {suggestion.full_output["叫牌历史"]}
                      </Box>
                    </Typography>
                  )}
                  {suggestion.full_output["自己和队友配合花色张数合计"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>自己和队友配合花色张数合计:</strong>
                      <Box component="pre" sx={{
                        mt: 0.5, p: 1, background: '#f8f9fa', borderRadius: 1,
                        fontSize: '0.85rem', lineHeight: 1.4, whiteSpace: 'pre-wrap',
                        border: '1px solid #e9ecef', maxHeight: '150px', overflow: 'auto',
                      }}>
                        {suggestion.full_output["自己和队友配合花色张数合计"]}
                      </Box>
                    </Typography>
                  )}
                  {suggestion.full_output["叫品筛选过程"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>叫品筛选过程:</strong>
                      <Box component="pre" sx={{
                        mt: 0.5, p: 1, background: '#f8f9fa', borderRadius: 1,
                        fontSize: '0.85rem', lineHeight: 1.4, whiteSpace: 'pre-wrap',
                        border: '1px solid #e9ecef', maxHeight: '200px', overflow: 'auto',
                      }}>
                        {suggestion.full_output["叫品筛选过程"]}
                      </Box>
                    </Typography>
                  )}
                  {suggestion.full_output["选定叫品"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>选定叫品:</strong> {suggestion.full_output["选定叫品"]}
                    </Typography>
                  )}
                  {suggestion.full_output["叫品含义"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>叫品含义:</strong> {suggestion.full_output["叫品含义"]}
                    </Typography>
                  )}
                  {suggestion.full_output["完整叫牌序列"] && (
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      <strong>完整叫牌序列:</strong> {suggestion.full_output["完整叫牌序列"]}
                    </Typography>
                  )}
                </CardContent>
              </Card>
            )}
          </Collapse>
        </Paper>
      )}
    </Box>
  )
}

export default BiddingSuggestion
