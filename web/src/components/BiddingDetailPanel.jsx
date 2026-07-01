import { useMemo, useState, useEffect, useRef } from 'react'
import { Box, Typography, Paper, FormControlLabel, Checkbox, Select, MenuItem, CircularProgress, Alert, Button, ToggleButton, ToggleButtonGroup, useTheme } from '@mui/material'
import { PANEL_LAYOUT } from '../styles/constants'
import { isHumanPosition } from '../utils/position'

function BiddingDetailPanel({
  isMobile,
  positionRoles,
  currentBidder,
  simpleDisplayMode,
  setSimpleDisplayMode,
  aiBiddingHistory,
  selectedBiddingIndex,
  setSelectedBiddingIndex,
  hands,
  gameMode,
  bidSuggestion,
  suggestionLoading,
  stopBidding,
  outputFormats,
  isBiddingCompleteFn,
  height = '640px',
  onStartPlay,
  playLoading,
  // 叫牌按钮相关
  biddingStarted,
  onStartBidding,
  onResetBidding,
  onToggleStopBidding,
  showUndo,
  canUndo,
  onUndo,
  onSave,
  canSave,
  aiThinking,
  readonlyMode = false,
  fallbackModel,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const bgWhite = isDark ? 'rgba(30, 41, 59, 0.7)' : 'white'
  const bgCode = isDark ? 'rgba(255,255,255,0.05)' : '#f8f9fa'
  const bgPanel = isDark ? 'rgba(255,255,255,0.04)' : '#fafafa'
  const borderCode = isDark ? '1px solid rgba(255,255,255,0.1)' : '1px solid #e9ecef'
  const borderPanel = isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #e0e0e0'
  const borderLine = isDark ? '1px solid rgba(255,255,255,0.08)' : '1px solid #ddd'
  const colorMuted = isDark ? '#94a3b8' : '#666'
  const [detailTab, setDetailTab] = useState('jf')

  // 人类回合自动切换到 JF 标签
  useEffect(() => {
    if (isHumanPosition(positionRoles, currentBidder)) {
      setDetailTab('jf')
    }
  }, [positionRoles, currentBidder])

  // LLM返回新结果时自动切换到细节面板
  const prevHistoryLen = useRef(aiBiddingHistory.length)
  useEffect(() => {
    if (aiBiddingHistory.length > prevHistoryLen.current) {
      setDetailTab('details')
    }
    prevHistoryLen.current = aiBiddingHistory.length
  }, [aiBiddingHistory.length])

  const historySelectOptions = useMemo(() => {
    if (aiBiddingHistory.length === 0) return []
    return aiBiddingHistory.slice().reverse().slice(1).map((record, idx) => ({
      value: aiBiddingHistory.length - 2 - idx,
      label: `${record.position}家 ${record.result.bid}`,
    }))
  }, [aiBiddingHistory])

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
          {positionRoles?.[record.position] === 'ai' && fallbackModel && (
            <Typography component="span" variant="caption" sx={{
              ml: 1, px: 0.8, py: 0.2, borderRadius: 1,
              bgcolor: 'action.hover', color: 'text.secondary',
              fontSize: '0.65rem', fontWeight: 500, verticalAlign: 'middle',
            }}>
              {fallbackModel}
            </Typography>
          )}
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          <strong>手牌:</strong> {record.hand?.display || '未知'}
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          <strong>叫牌序列:</strong> {record.biddingSequence || '空（开叫位置）'}
        </Typography>
        
        {/* 动态渲染 fullOutput 所有字段（跳过下方已单独显示的） */}
        {Object.keys(fullOutput).length > 0 ? (
          Object.entries(fullOutput).filter(([key]) => ![
            '选定叫品', '叫品含义', '叫品筛选过程',
            '完整叫牌序列', '当前叫牌序列', '自己pass次数',
          ].includes(key)).map(([key, value]) => {
            if (value == null || value === '') return null
            const isLongText = typeof value === 'string' && value.length > 60
            const isObject = typeof value === 'object'
            return (
              <Typography key={key} variant="body2" component="div" sx={{ mt: 1 }}>
                <strong>{key}:</strong>
                {isObject ? (
                  <Box component="pre" sx={{
                    mt: 0.5, p: 1, background: bgCode, borderRadius: 1,
                    fontSize: '0.7rem', lineHeight: 1.4,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    border: borderCode, maxHeight: '200px', overflow: 'auto'
                  }}>
                    {JSON.stringify(value, null, 2)}
                  </Box>
                ) : isLongText ? (
                  <Box component="pre" sx={{
                    mt: 0.5, p: 1, background: bgCode, borderRadius: 1,
                    fontSize: '0.7rem', lineHeight: 1.4,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    border: borderCode, maxHeight: '200px', overflow: 'auto'
                  }}>
                    {value}
                  </Box>
                ) : (
                  <span> {value}</span>
                )}
              </Typography>
            )
          })
        ) : positionRoles?.[record.position] === 'ai' ? (
          <Typography variant="body2" sx={{ mt: 1, color: colorMuted }}>
            （LLM 已处理，无额外结构化输出）
          </Typography>
        ) : (
          <Typography variant="body2" sx={{ mt: 1, color: colorMuted, fontStyle: 'italic' }}>
            无结构化字段（该叫品未调用 LLM 或匹配自 JF 约定）
          </Typography>
        )}

        {/* record.result 顶层字段 */}
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
              fontSize: '0.75rem', lineHeight: 1.4,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              border: borderCode, maxHeight: '200px', overflow: 'auto'
            }}>
              {record.result.selection_process}
            </Box>
          </Typography>
        )}
        {/* fullOutput 以外的 result 字段（兜底显示原始 JSON） */}
        {Object.keys(fullOutput).length === 0 && (
          <Box component="pre" sx={{
            mt: 1, p: 1, background: bgCode, borderRadius: 1,
            fontSize: '0.65rem', lineHeight: 1.3,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            border: borderCode, maxHeight: '300px', overflow: 'auto'
          }}>
            {JSON.stringify(record.result, null, 2)}
          </Box>
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
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      minHeight: 0,
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
    <Paper elevation={0} sx={{
      m: 0,
      p: isMobile ? 0.5 : 1,
      background: isDark
        ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(30, 41, 59, 0.6) 100%)'
        : 'linear-gradient(135deg, rgba(255, 255, 255, 0.85) 0%, rgba(255, 255, 255, 0.7) 100%)',
      backdropFilter: 'blur(20px) saturate(180%)',
      WebkitBackdropFilter: 'blur(20px) saturate(180%)',
      border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.8)'}`,
      boxShadow: isDark
        ? '0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)'
        : '0 8px 32px rgba(79, 70, 229, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.9)',
      borderRadius: 3,
      display: 'flex',
      flexDirection: 'column',
      width: isMobile ? '100%' : '640px',
      height: '640px',
      minHeight: '640px',
      flexShrink: 0,
      minHeight: isMobile ? '400px' : undefined,
      overflow: isMobile ? undefined : 'hidden',
      boxSizing: 'border-box'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5, flexShrink: 0, height: 44, flexWrap: 'wrap', gap: 0.5, overflow: 'hidden' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, fontSize: '1rem' }}>
            叫牌细节
          </Typography>
          <ToggleButtonGroup
            value={detailTab}
            exclusive
            onChange={(e, v) => { if (v !== null) setDetailTab(v) }}
            size="small"
            sx={{ height: 24 }}
          >
            <ToggleButton value="jf" sx={{ px: 1, py: 0, fontSize: '0.7rem', minWidth: 36 }}>JF</ToggleButton>
            <ToggleButton value="details" sx={{ px: 1, py: 0, fontSize: '0.7rem', minWidth: 36 }}>细节</ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <Box sx={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 0.5 }}>
          <FormControlLabel
            control={<Checkbox checked={simpleDisplayMode} onChange={(e) => setSimpleDisplayMode(e.target.checked)} size="small" />}
            label="简单"
            sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, height: 24 }}
          />
          <Select
            size="small"
            value={selectedBiddingIndex}
            onChange={(e) => setSelectedBiddingIndex(e.target.value)}
            disabled={simpleDisplayMode || aiBiddingHistory.length === 0}
            sx={{ fontSize: '0.75rem', height: 24, minWidth: 80, '& .MuiSelect-select': { py: 0 } }}
          >
              <MenuItem value={-1}>最新</MenuItem>
              {historySelectOptions.map((opt) => (
                <MenuItem key={opt.value} value={opt.value}>
                  {opt.label}
                </MenuItem>
              ))}
            </Select>
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          <Button variant="outlined" size="small" onClick={!biddingStarted ? onStartBidding : onResetBidding} disabled={!hands || aiThinking || readonlyMode} sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, px: 0.5, py: 0, minWidth: 36 }}>
            {!biddingStarted ? '开始' : '重新叫牌'}
          </Button>
          {biddingStarted && !isBiddingCompleteFn() && (
            <Button variant={stopBidding ? "contained" : "outlined"} color={stopBidding ? "success" : "warning"} size="small" onClick={onToggleStopBidding} disabled={(stopBidding && aiThinking) || readonlyMode} sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, px: 0.5, py: 0, minWidth: 36 }}>
              {stopBidding ? '继续' : '暂停'}
            </Button>
          )}
          {showUndo && (
            <Button variant="outlined" color="secondary" size="small" onClick={onUndo} disabled={!canUndo || readonlyMode} sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, px: 0.5, py: 0, minWidth: 36 }}>
              撤销
            </Button>
          )}
          <Button variant="outlined" color="info" size="small" onClick={onSave} disabled={!canSave || readonlyMode} sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, px: 0.5, py: 0, minWidth: 36 }}>
            保存
          </Button>
          {gameMode !== 'pair' && onStartPlay && (
            <Button variant="contained" color="primary" size="small" onClick={onStartPlay} disabled={playLoading} sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, px: 0.5, py: 0, minWidth: 36 }}>
              {playLoading ? <CircularProgress size={16} /> : '切换到打牌'}
            </Button>
          )}
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflow: 'hidden', p: 1, background: isDark ? 'radial-gradient(ellipse at center, #1a2f22 0%, #0d1f15 50%, #06120d 100%)' : 'radial-gradient(ellipse at center, #3d7a58 0%, #25563b 40%, #1a3d28 100%)', borderRadius: 2, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        {detailTab === 'jf' ? (
          <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, p: 1 }}>
            {renderJFPanel()}
          </Box>
        ) : (
          <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, p: 1 }}>
            {renderBiddingDetails()}
            {renderOutputFormats()}
          </Box>
        )}
      </Box>
    </Paper>
  )
}

export default BiddingDetailPanel
