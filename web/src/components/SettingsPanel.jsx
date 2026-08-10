import { memo, useState } from 'react'
import {
  Box, Typography, Paper, FormControl, InputLabel, Select, MenuItem,
  Divider, TextField, useTheme, ToggleButton, ToggleButtonGroup
} from '@mui/material'
import { parseModelValue } from '../hooks/useModelSettings'

// 基础模型（不含 ::reasoning 后缀），思考模式通过 ToggleButton 控制
const BASE_MODELS = [
  { label: 'V4-Flash', value: 'deepseek-v4-flash' },
  { label: 'V4-Pro', value: 'deepseek-v4-pro' },
]

// ── 模型选择器 + 思考切换（模块级组件）──
function ModelSelector({ label, parsed, onModelChange, onReasoningChange, disabled, models }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'stretch', gap: 0 }}>
      <FormControl sx={{ minWidth: 100 }} size="small" disabled={disabled}>
        <InputLabel>{label}</InputLabel>
        <Select
          value={models.some(m => m.value === parsed.model) ? parsed.model : models[0]?.value || ''}
          label={label}
          onChange={onModelChange}
          sx={{
            borderTopRightRadius: 0,
            borderBottomRightRadius: 0,
            '& .MuiOutlinedInput-notchedOutline': { borderRight: 'none' },
          }}
        >
          {models.map(m => (
            <MenuItem key={m.value} value={m.value}>{m.label}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <ToggleButtonGroup
        value={parsed.reasoning ? 'reasoning' : 'chat'}
        exclusive
        onChange={onReasoningChange}
        size="small"
        disabled={disabled}
        sx={{
          '& .MuiToggleButton-root': {
            px: 1.2,
            fontSize: '0.7rem',
            textTransform: 'none',
            borderTopLeftRadius: 0,
            borderBottomLeftRadius: 0,
            minWidth: 42,
          },
        }}
      >
        <ToggleButton value="chat">快</ToggleButton>
        <ToggleButton value="reasoning">思</ToggleButton>
      </ToggleButtonGroup>
    </Box>
  )
}

// 可拖滑块：本地草稿值实时更新显示，拖动仅重渲染本组件，松手才提交给父级
const RangeSlider = memo(function RangeSlider({
  label, value, onCommit, min, max, step, width,
}) {
  const [draft, setDraft] = useState(value)
  const [dragging, setDragging] = useState(false)
  const [prevValue, setPrevValue] = useState(value)

  // 外部提交后的 value 变化回同步草稿；拖动期间不覆盖本地草稿
  if (value !== prevValue) {
    setPrevValue(value)
    if (!dragging.current) setDraft(value)
  }

  const commit = () => {
    setDragging(false)
    onCommit(draft)
  }

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary' }}>{label}</Typography>
      <input
        type="range" min={min} max={max} step={step} value={draft}
        onChange={(e) => { setDragging(true); setDraft(Number(e.target.value)) }}
        onMouseUp={commit} onTouchEnd={commit} onKeyUp={commit}
        style={{ width, height: 16 }}
      />
      <Typography variant="caption" sx={{ fontSize: '0.65rem', fontWeight: 600, minWidth: 24 }}>{draft}</Typography>
    </Box>
  )
})

function SettingsPanel({
  showSettings,
  isMobile = false,
  gameMode,
  setGameMode,
  fallbackModel,
  handleFallbackModelChange,
  playModel,
  handlePlayModelChange,
  playEngine,
  handlePlayEngineChange,
  useLlmReview,
  handleLlmReviewChange,
  ddSampleCount,
  handleDDSampleCountChange,
  ddParticlesRange,
  mctsParticles, mctsParticlesRange,
  alphaMuParticles, alphaMuParticlesRange,
  handleParticleChange,
  switchCards, switchCardsRange,
  handleSwitchCardsChange,
  dealSystem,
  setDealSystem,
  dealMode,
  setDealMode,
  mode,
  hands,
  availableModels,
  vulnerability,
  setVulnerability,
}) {
  const theme = useTheme()

  // 完美DD：发牌练习模式直接可用，其他模式有四家完整手牌也可用
  const allHandsComplete = hands && ['南','北','东','西'].every(p => {
    const h = hands[p]
    return h && ((h.spades || '') + (h.hearts || '') + (h.diamonds || '') + (h.clubs || '')).length > 0
  })

  // 解析当前模型为基础名 + 是否思考模式
  const biddingParsed = parseModelValue(fallbackModel)
  const playParsed = parseModelValue(playModel)

  // 根据后端返回的可用模型列表过滤
  const availableBases = availableModels?.length
    ? [...new Set(availableModels.map(m => m.replace('::reasoning', '')))]
    : null
  const visibleModels = availableBases
    ? BASE_MODELS.filter(m => availableBases.includes(m.value))
    : BASE_MODELS

  // 构造组合模型值 "base::reasoning" 或 "base"
  const makeCombined = (base, reasoning) => reasoning ? `${base}::reasoning` : base

  // 叫牌模型变更
  const onBiddingModelChange = (event) => {
    handleFallbackModelChange({ target: { value: makeCombined(event.target.value, biddingParsed.reasoning) } })
  }
  const onBiddingReasoningChange = (e, newMode) => {
    if (!newMode) return
    const reasoning = newMode === 'reasoning'
    const base = visibleModels.some(m => m.value === biddingParsed.model)
      ? biddingParsed.model : visibleModels[0]?.value || 'deepseek-v4-flash'
    handleFallbackModelChange({ target: { value: makeCombined(base, reasoning) } })
  }

  // 打牌模型变更
  const onPlayModelChange = (event) => {
    handlePlayModelChange({ target: { value: makeCombined(event.target.value, playParsed.reasoning) } })
  }
  const onPlayReasoningChange = (e, newMode) => {
    if (!newMode) return
    const reasoning = newMode === 'reasoning'
    const base = visibleModels.some(m => m.value === playParsed.model)
      ? playParsed.model : visibleModels[0]?.value || 'deepseek-v4-flash'
    handlePlayModelChange({ target: { value: makeCombined(base, reasoning) } })
  }

  if (!showSettings) return null

  return (
    <Paper elevation={2} sx={{ p: { xs: 2, md: 3 }, mb: 3, width: '100%' }}>
      <Box sx={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', flexWrap: 'nowrap', gap: isMobile ? 1.5 : 1.5, alignItems: 'flex-start' }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0 }}>
          <Typography variant="h6" sx={{ fontSize: '0.85rem' }}>
            叫牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: isMobile ? 'wrap' : 'nowrap', gap: 1, alignItems: 'center' }}>
            <FormControl sx={{ minWidth: 80 }} size="small">
              <InputLabel>模式</InputLabel>
              <Select value={gameMode} label="模式" onChange={(e) => setGameMode(e.target.value)}>
                <MenuItem value="four">四人</MenuItem>
                <MenuItem value="pair">双人</MenuItem>
              </Select>
            </FormControl>

            <ModelSelector
              label="模型"
              parsed={biddingParsed}
              onModelChange={onBiddingModelChange}
              onReasoningChange={onBiddingReasoningChange}
              models={visibleModels}
            />

            <FormControl sx={{ minWidth: 140 }} size="small">
              <InputLabel>阻击叫牌体系</InputLabel>
              <Select value={dealSystem} label="阻击叫牌体系" onChange={(e) => setDealSystem(e.target.value)}>
                <MenuItem value="自然阻击">自然阻击</MenuItem>
                <MenuItem value="2D：多功能，2H/S：麦德伯格，2NT：双低花">多功能/麦德伯格</MenuItem>
              </Select>
            </FormControl>

            <FormControl sx={{ minWidth: 100 }} size="small">
              <InputLabel>局况</InputLabel>
              <Select value={vulnerability} label="局况" onChange={(e) => setVulnerability(e.target.value)}>
                <MenuItem value="NV">双无局</MenuItem>
                <MenuItem value="NS">南北有局</MenuItem>
                <MenuItem value="EW">东西有局</MenuItem>
                <MenuItem value="All">双有局</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Box>

        <Divider orientation={isMobile ? 'horizontal' : 'vertical'} flexItem sx={{ borderColor: theme.palette.divider, flexShrink: 0, width: isMobile ? '100%' : undefined }} />

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0 }}>
          <Typography variant="h6" sx={{ fontSize: '0.85rem' }}>
            打牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: isMobile ? 'wrap' : 'nowrap', gap: 1, alignItems: 'center' }}>
            <ModelSelector
              label="模型"
              parsed={playParsed}
              onModelChange={onPlayModelChange}
              onReasoningChange={onPlayReasoningChange}
              disabled={playEngine !== 'llm' && playEngine !== 'dd_alphamu_llm'}
              models={visibleModels}
            />

            <FormControl size="small" sx={{ minWidth: 90 }}>
              <InputLabel>打牌引擎</InputLabel>
              <Select
                value={playEngine}
                onChange={(e) => handlePlayEngineChange(e.target.value)}
                label="打牌引擎"
              >
                <MenuItem value="dd_alphamu_llm">DD-αμ-LLM</MenuItem>
                <MenuItem value="llm">LLM</MenuItem>
                <MenuItem value="mcts">MCTS</MenuItem>
                <MenuItem value="dd">DD</MenuItem>
                <MenuItem value="perfect" disabled={mode !== 'practice' && !allHandsComplete} title={mode !== 'practice' && !allHandsComplete ? '完美DD需要四家完整手牌，暂不可用' : ''}>完美DD</MenuItem>
                <MenuItem value="alphamu">αμ</MenuItem>
              </Select>
            </FormControl>
            {playEngine === 'dd' && (
              <RangeSlider label="样本数" value={ddSampleCount}
                min={ddParticlesRange.min} max={ddParticlesRange.max} step={250} width={72}
                onCommit={handleDDSampleCountChange} />
            )}
            {playEngine === 'dd_alphamu_llm' && (
              <>
                <RangeSlider label="分界" value={switchCards}
                  min={switchCardsRange.min} max={switchCardsRange.max} step={1} width={60}
                  onCommit={handleSwitchCardsChange} />
                <ToggleButtonGroup
                  value={useLlmReview ? 'on' : 'off'}
                  exclusive
                  onChange={(_, v) => v && handleLlmReviewChange(v === 'on')}
                  size="small"
                  sx={{
                    '& .MuiToggleButton-root': { px: 1, py: 0.2, fontSize: '0.65rem', textTransform: 'none', minWidth: 40 },
                  }}
                >
                  <ToggleButton value="off">纯引擎</ToggleButton>
                  <ToggleButton value="on">LLM审查</ToggleButton>
                </ToggleButtonGroup>
              </>
            )}
            {playEngine === 'alphamu' && (
              <RangeSlider label="世界数" value={alphaMuParticles}
                min={alphaMuParticlesRange.min} max={alphaMuParticlesRange.max} step={5} width={72}
                onCommit={(v) => handleParticleChange('alphaMu', v)} />
            )}
            {playEngine === 'mcts' && (
              <RangeSlider label="样本数" value={mctsParticles}
                min={mctsParticlesRange.min} max={mctsParticlesRange.max} step={10} width={72}
                onCommit={(v) => handleParticleChange('mcts', v)} />
            )}
          </Box>
        </Box>

        <Divider orientation={isMobile ? 'horizontal' : 'vertical'} flexItem sx={{ borderColor: theme.palette.divider, flexShrink: 0, width: isMobile ? '100%' : undefined }} />

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0 }}>
          <Typography variant="h6" sx={{ fontSize: '0.85rem' }}>
            发牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: isMobile ? 'wrap' : 'nowrap', gap: 1, alignItems: 'center' }}>
            <FormControl sx={{ minWidth: 80 }} size="small">
              <InputLabel>发牌</InputLabel>
              <Select value={dealMode} label="发牌" onChange={(e) => setDealMode(e.target.value)}>
                <MenuItem value="free">自由</MenuItem>
                <MenuItem value="game">进局</MenuItem>
                <MenuItem value="slam">满贯</MenuItem>
              </Select>
            </FormControl>

          </Box>
        </Box>
      </Box>
    </Paper>
  )
}

export default SettingsPanel
