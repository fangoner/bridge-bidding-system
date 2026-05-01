import { Box, Typography, Paper, ToggleButton, ToggleButtonGroup, FormControlLabel, Checkbox, FormControl, InputLabel, Select, MenuItem, CircularProgress, Alert, Button, useTheme } from '@mui/material'
import BiddingControls from './BiddingControls'

function BiddingDetailPanel({
  isMobile,
  humanPosition,
  currentBidder,
  isBiddingComplete,
  showBiddingControls,
  setShowBiddingControls,
  simpleDisplayMode,
  setSimpleDisplayMode,
  aiBiddingHistory,
  selectedBiddingIndex,
  setSelectedBiddingIndex,
  hands,
  gameMode,
  addBid,
  getJFSuggestion,
  getFinalContract,
  bidSuggestion,
  suggestionLoading,
  stopBidding,
  shouldAIAutoPass,
  customBidMeaning,
  setCustomBidMeaning,
  outputFormats,
  isBiddingCompleteFn,
  height = '680px',
  onStartPlay,
  playLoading,
  // 叫牌按钮相关
  biddingStarted,
  isNewDeal,
  onStartBidding,
  onResetBidding,
  onToggleStopBidding,
  showUndo,
  canUndo,
  onUndo,
  onSave,
  canSave,
  aiThinking,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const bgWhite = isDark ? 'rgba(30, 41, 59, 0.7)' : 'white'
  const bgCode = isDark ? 'rgba(255,255,255,0.05)' : '#f8f9fa'
  const bgPanel = isDark ? 'rgba(255,255,255,0.04)' : '#fafafa'
  const bgWarn = isDark ? 'rgba(255, 243, 224, 0.12)' : '#fff3e0'
  const borderCode = isDark ? '1px solid rgba(255,255,255,0.1)' : '1px solid #e9ecef'
  const borderPanel = isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #e0e0e0'
  const borderLine = isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #ddd'
  const colorMuted = isDark ? '#94a3b8' : '#666'
  const isHumanTurn = humanPosition !== null && (
    Array.isArray(humanPosition) 
      ? humanPosition.includes(currentBidder) 
      : humanPosition === currentBidder
  )
  const canShowControls = humanPosition !== null && !isBiddingComplete
  const effectiveShowControls = isHumanTurn && !isBiddingComplete && showBiddingControls

  const renderButtons = () => (
    <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mb: 0.5, flexShrink: 0, flexWrap: 'wrap' }}>
      <Box sx={{ minWidth: isMobile ? 200 : 120 }}>
        <FormControl size="small" sx={{ minWidth: isMobile ? 200 : 120, '& .MuiInputBase-input': { fontSize: '0.875rem' }, '& .MuiInputLabel-root': { fontSize: '0.875rem' } }} disabled={simpleDisplayMode || aiBiddingHistory.length === 0}>
          <InputLabel>{isMobile ? '选择叫牌记录' : '记录'}</InputLabel>
          <Select
            value={selectedBiddingIndex}
            label={isMobile ? '选择叫牌记录' : '记录'}
            onChange={(e) => setSelectedBiddingIndex(e.target.value)}
            sx={{ fontSize: '0.875rem' }}
          >
            <MenuItem value={-1}>最新 ({aiBiddingHistory[aiBiddingHistory.length - 1]?.position}家 {aiBiddingHistory[aiBiddingHistory.length - 1]?.result.bid})</MenuItem>
            {aiBiddingHistory.slice().reverse().slice(1).map((record, idx) => (
              <MenuItem key={idx} value={aiBiddingHistory.length - 2 - idx}>
                {record.position}家 {record.result.bid}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>
      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', ml: 'auto', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        {(!biddingStarted || isBiddingCompleteFn()) && (
          <Button
            variant="outlined"
            size="small"
            onClick={isNewDeal ? onStartBidding : onResetBidding}
            disabled={!hands || aiThinking}
            sx={{ fontSize: '0.75rem', textTransform: 'none' }}
          >
            {isNewDeal ? '开始' : '重新叫牌'}
          </Button>
        )}
        {biddingStarted && !isBiddingCompleteFn() && (
          <Button
            variant={stopBidding ? "contained" : "outlined"}
            color={stopBidding ? "success" : "warning"}
            size="small"
            onClick={onToggleStopBidding}
            disabled={stopBidding && aiThinking}
            sx={{ fontSize: '0.75rem', textTransform: 'none' }}
          >
            {stopBidding ? '继续' : '暂停'}
          </Button>
        )}
        {showUndo && (
          <Button
            variant="outlined"
            color="secondary"
            size="small"
            onClick={onUndo}
            disabled={!canUndo}
            sx={{ fontSize: '0.75rem', textTransform: 'none' }}
          >
            撤销
          </Button>
        )}
        <Button
          variant="outlined"
          color="info"
          size="small"
          onClick={onSave}
          disabled={!canSave}
          sx={{ fontSize: '0.75rem', textTransform: 'none' }}
        >
          保存
        </Button>
        {isBiddingCompleteFn && isBiddingCompleteFn() && onStartPlay && (
          <Button
            variant="contained"
            color="primary"
            size="small"
            onClick={onStartPlay}
            disabled={playLoading}
            sx={{ fontSize: '0.75rem', textTransform: 'none' }}
          >
            {playLoading ? <CircularProgress size={16} /> : '切换到打牌'}
          </Button>
        )}
      </Box>
    </Box>
  )

  const renderBiddingDetails = () => {
    if (aiBiddingHistory.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 4 }}>
          等待AI叫牌...
        </Typography>
      )
    }

    if (simpleDisplayMode) {
      return aiBiddingHistory.map((record, index) => (
        <Box key={index} sx={{ mb: 1, p: 1.5, background: isDark ? 'rgba(30, 41, 59, 0.7)' : 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}>
          <Typography variant="body2">
            <strong>{record.position}家</strong> → <span style={{ color: '#d32f2f', fontWeight: 'bold' }}>{record.result.bid}</span>
            {record.result.meaning && <span style={{ color: isDark ? '#94a3b8' : '#666' }}> ({record.result.meaning})</span>}
          </Typography>
        </Box>
      ))
    }

    const record = selectedBiddingIndex === -1 
      ? aiBiddingHistory[aiBiddingHistory.length - 1] 
      : aiBiddingHistory[selectedBiddingIndex]
    
    if (!record) return null
    const fullOutput = record.result.full_output || {}

    return (
      <Box sx={{ p: 2, background: isDark ? 'rgba(30, 41, 59, 0.7)' : 'white', borderRadius: 1, borderLeft: '4px solid #2196f3', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
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
        {fullOutput["阻击叫体系"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>阻击叫体系:</strong> {fullOutput["阻击叫体系"]}
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
              mt: 0.5, p: 1, background: bgCode, borderRadius: 1,
              fontSize: '0.85rem', lineHeight: 1.4,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: borderCode, maxHeight: '150px', overflow: 'auto'
            }}>
              {fullOutput["手牌分析"]}
            </Box>
          </Typography>
        )}
        {fullOutput["叫牌历史"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>叫牌历史:</strong>
            <Box component="pre" sx={{ 
              mt: 0.5, p: 1, background: bgCode, borderRadius: 1,
              fontSize: '0.85rem', lineHeight: 1.4,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: borderCode, maxHeight: '150px', overflow: 'auto'
            }}>
              {fullOutput["叫牌历史"]}
            </Box>
          </Typography>
        )}
        {fullOutput["自己和队友配合花色张数合计"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>配合花色:</strong> {fullOutput["自己和队友配合花色张数合计"]}
          </Typography>
        )}
        {fullOutput["牌型点"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>牌型点:</strong> {fullOutput["牌型点"]}
          </Typography>
        )}
        {fullOutput["自己和队友点力合计"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>点力合计:</strong> {fullOutput["自己和队友点力合计"]}
          </Typography>
        )}
        {fullOutput["是否进局或试探满贯"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>定约目标:</strong> {fullOutput["是否进局或试探满贯"]}
          </Typography>
        )}
        {fullOutput["止张分析"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>止张分析:</strong> {fullOutput["止张分析"]}
          </Typography>
        )}
        {fullOutput["扣叫控制"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>扣叫控制:</strong>
            <Box component="pre" sx={{ 
              mt: 0.5, p: 1, background: bgCode, borderRadius: 1,
              fontSize: '0.85rem', lineHeight: 1.4,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: borderCode, maxHeight: '150px', overflow: 'auto'
            }}>
              {fullOutput["扣叫控制"]}
            </Box>
          </Typography>
        )}
        {fullOutput["自己和队友关键张合计"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>关键张合计:</strong> {fullOutput["自己和队友关键张合计"]}
          </Typography>
        )}
        {fullOutput["主提示词输出"] && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>主提示词输出:</strong>
            <Box component="pre" sx={{ 
              mt: 0.5, p: 1, background: bgWarn, borderRadius: 1,
              fontSize: '0.85rem', lineHeight: 1.4,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: isDark ? '1px solid rgba(255, 204, 128, 0.3)' : '1px solid #ffcc80'
            }}>
              选定叫品: {fullOutput["主提示词输出"]["选定叫品"]}
              {'\n'}叫品筛选过程: {fullOutput["主提示词输出"]["叫品筛选过程"]}
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
              mt: 1, p: 1, background: bgCode, borderRadius: 1,
              fontSize: '0.85rem', lineHeight: 1.4,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: borderCode, maxHeight: '200px', overflow: 'auto'
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
  }

  const renderOutputFormats = () => {
    if (!isBiddingCompleteFn || !isBiddingCompleteFn() || !outputFormats) return null

    return (
      <Box sx={{ mt: 2, p: 2, background: bgWhite, borderRadius: 1, border: borderPanel }}>
        <Typography variant="subtitle2" sx={{ mb: 1, color: '#1976d2', fontWeight: 'bold' }}>
          牌局格式
        </Typography>
        <Typography variant="body2" component="pre" sx={{
          whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0,
          fontFamily: 'monospace', fontSize: '0.75rem', p: 1,
          background: bgPanel, borderRadius: 1, border: borderPanel,
        }}>
          {outputFormats.compact}
        </Typography>
        <Typography variant="subtitle2" sx={{ mt: 2, mb: 1, color: '#1976d2', fontWeight: 'bold' }}>
          Deep Finesse格式
        </Typography>
        <Typography variant="body2" component="pre" sx={{
          whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0,
          fontFamily: 'monospace', fontSize: '0.75rem', p: 1,
          background: bgPanel, borderRadius: 1, border: borderPanel,
        }}>
          {outputFormats.deep_finesse}
        </Typography>
        
      </Box>
    )
  }

  const renderJFPanel = () => (
    <Paper elevation={2} sx={{
      p: 1.5,
      flex: '0 0 auto',
      height: isMobile ? '500px' : '400px',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <Typography variant="h6" gutterBottom sx={{ flexShrink: 0 }}>
        JF约定片段
      </Typography>
      <Box sx={{ flex: 1, overflow: 'auto', maxWidth: '100%', minWidth: 0, minHeight: 0 }}>
        {suggestionLoading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, justifyContent: 'center', height: '100%' }}>
            <CircularProgress size={20} />
            <Typography variant="body2">获取JF约定片段中...</Typography>
          </Box>
        ) : bidSuggestion ? (
          <Box>
            <Typography variant="subtitle2" gutterBottom sx={{ color: colorMuted }}>
              检索关键字: <strong style={{ color: '#1976d2' }}>{bidSuggestion.keyword}</strong>
            </Typography>
            {bidSuggestion.content ? (
              <Box sx={{ mt: 1, p: 1.5, background: bgPanel, borderRadius: 1, border: borderPanel, overflow: 'auto', maxWidth: '100%' }}>
                <Typography variant="body2" component="pre" sx={{
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  margin: 0, fontFamily: 'inherit', fontSize: '0.9rem', maxWidth: '100%',
                }}>
                  {bidSuggestion.content}
                </Typography>
              </Box>
            ) : (
              <Alert severity="info" sx={{ mt: 1 }}>JF尚未提供建议</Alert>
            )}
          </Box>
        ) : (
          <Alert severity="info" sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            JF尚未提供建议
          </Alert>
        )}
      </Box>
    </Paper>
  )

  return (
    <Paper elevation={3} sx={{ 
      p: isMobile ? 0.5 : 1, 
      bgcolor: isDark ? 'rgba(30, 41, 59, 0.9)' : (isMobile ? '#f5f5f5' : '#e8e8e8'), 
      display: 'flex', 
      flexDirection: 'column', 
      flex: isMobile ? undefined : '0 0 auto',
      width: isMobile ? '100%' : '600px',
      height: isMobile ? (effectiveShowControls ? 'auto' : '400px') : '640px',
      minHeight: isMobile && effectiveShowControls ? '800px' : undefined,
      overflow: isMobile ? undefined : 'hidden',
      boxSizing: 'border-box'
    }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5, flexShrink: 0, minHeight: 40, flexWrap: isMobile ? 'wrap' : 'nowrap', gap: isMobile ? 0.5 : 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant={isMobile ? "h6" : "subtitle1"} sx={{ fontWeight: 600, fontSize: isMobile ? undefined : '1rem', color: isDark ? '#e2e8f0' : undefined }}>
            叫牌细节
          </Typography>
          <ToggleButtonGroup
            value={effectiveShowControls ? 'controls' : 'details'}
            exclusive
            onChange={(e, newValue) => {
              if (newValue !== null) {
                setShowBiddingControls(newValue === 'controls')
              }
            }}
            size="small"
            sx={{ height: 24 }}
            disabled={!canShowControls}
          >
            <ToggleButton value="controls" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 40 }}>
              控制
            </ToggleButton>
            <ToggleButton value="details" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 40 }}>
              细节
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <FormControlLabel
          control={<Checkbox checked={simpleDisplayMode} onChange={(e) => setSimpleDisplayMode(e.target.checked)} size="small" />}
          label="简单"
          sx={{ ml: 'auto', '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, height: 24 }}
        />
      </Box>

      {effectiveShowControls ? (
        /* 叫牌控制 + JF片段 */
        <Box sx={{ flex: 1, overflow: 'hidden', p: 1, background: bgPanel, borderRadius: 2, border: borderLine, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 1 }}>
          {renderButtons()}
          <Box sx={{ flex: '0 0 auto' }}>
            <BiddingControls
              hands={hands}
              currentBidder={currentBidder}
              humanPosition={humanPosition}
              gameMode={gameMode}
              checkBiddingComplete={isBiddingCompleteFn}
              addBid={addBid}
              getJFSuggestion={getJFSuggestion}
              getFinalContract={getFinalContract}
              bidSuggestion={bidSuggestion}
              suggestionLoading={suggestionLoading}
              stopBidding={stopBidding}
              shouldAIAutoPass={shouldAIAutoPass}
              customBidMeaning={customBidMeaning}
              setCustomBidMeaning={setCustomBidMeaning}
              isVerticalLayout={true}
              hideJFPanel={true}
            />
          </Box>
          {renderJFPanel()}
        </Box>
      ) : (
        /* 叫牌细节 */
        <Box sx={{ flex: 1, overflow: 'hidden', p: 1, background: bgPanel, borderRadius: 2, border: borderLine, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          {renderButtons()}
          <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            {renderBiddingDetails()}
            {renderOutputFormats()}
          </Box>
        </Box>
      )}
    </Paper>
  )
}

export default BiddingDetailPanel
