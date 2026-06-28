import {
  Box, Typography, Paper, FormControl, InputLabel, Select, MenuItem,
  Divider, TextField, useTheme, ToggleButton, ToggleButtonGroup
} from '@mui/material'
import { parseModelValue } from '../hooks/useModelSettings'

// 4 个基础模型（不含 ::reasoning 后缀），思考模式通过 ToggleButton 控制
const BASE_MODELS = [
  { label: 'V4-Flash', value: 'deepseek-v4-flash' },
  { label: 'V4-Pro', value: 'deepseek-v4-pro' },
  { label: '豆包 Pro', value: 'doubao-seed-2.1-pro' },
  { label: '豆包 Turbo', value: 'doubao-seed-2.1-turbo' },
]

// ── 模型选择器 + 思考切换（模块级组件）──
function ModelSelector({ label, parsed, onModelChange, onReasoningChange, disabled, models }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'stretch', gap: 0 }}>
      <FormControl sx={{ minWidth: 140 }} size="small" disabled={disabled}>
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
        <ToggleButton value="chat">快答</ToggleButton>
        <ToggleButton value="reasoning">思考</ToggleButton>
      </ToggleButtonGroup>
    </Box>
  )
}

function SettingsPanel({
  showSettings,
  gameMode,
  setGameMode,
  fallbackModel,
  handleFallbackModelChange,
  playModel,
  handlePlayModelChange,
  playEngine,
  handlePlayEngineChange,
  ddSampleCount,
  handleDDSampleCountChange,
  ddParticles, ddParticlesRange,
  mctsParticles, mctsParticlesRange,
  alphaMuParticles, alphaMuParticlesRange,
  handleParticleChange,
  dealSystem,
  setDealSystem,
  dealMode,
  setDealMode,
  mode,
  availableModels,
}) {
  const theme = useTheme()

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
      <Box sx={{ display: 'flex', flexWrap: 'nowrap', gap: 1.5, alignItems: 'flex-start' }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0 }}>
          <Typography variant="h6" sx={{ fontSize: '0.85rem' }}>
            叫牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'nowrap', gap: 1, alignItems: 'center' }}>
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
                <MenuItem value="2D/2H/2S：自然阻击">2D/2H/2S：自然阻击</MenuItem>
                <MenuItem value="2D：多功能，2H/S：麦德伯格，2NT：双低花">多功能/麦德伯格</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Box>

        <Divider orientation="vertical" flexItem sx={{ borderColor: theme.palette.divider, flexShrink: 0 }} />

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0 }}>
          <Typography variant="h6" sx={{ fontSize: '0.85rem' }}>
            打牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'nowrap', gap: 1, alignItems: 'center' }}>
            <ModelSelector
              label="模型"
              parsed={playParsed}
              onModelChange={onPlayModelChange}
              onReasoningChange={onPlayReasoningChange}
              disabled={playEngine !== 'llm' && playEngine !== 'tiered'}
              models={visibleModels}
            />

            <FormControl size="small" sx={{ minWidth: 110 }}>
              <InputLabel>打牌引擎</InputLabel>
              <Select
                value={playEngine}
                onChange={(e) => handlePlayEngineChange(e.target.value)}
                label="打牌引擎"
              >
                <MenuItem value="llm">LLM 大模型</MenuItem>
                <MenuItem value="mcts">MCTS 搜索</MenuItem>
                <MenuItem value="dd">DD 蒙地卡罗</MenuItem>
                <MenuItem value="perfect" disabled={mode !== 'practice'} title={mode !== 'practice' ? '完美DD需要四家完整手牌，仅发牌练习模式可用' : ''}>完美DD (全知)</MenuItem>
                <MenuItem value="tiered">Tiered 分层</MenuItem>
                <MenuItem value="alphamu">αμ 搜索</MenuItem>
              </Select>
            </FormControl>
            {playEngine === 'dd' && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary' }}>粒子</Typography>
                <input type="range" min={ddParticlesRange.min} max={ddParticlesRange.max}
                  value={ddParticles} onChange={(e) => handleParticleChange('dd', Number(e.target.value))}
                  style={{ width: 72, height: 16 }} />
                <Typography variant="caption" sx={{ fontSize: '0.65rem', fontWeight: 600, minWidth: 24 }}>{ddParticles}</Typography>
              </Box>
            )}
            {playEngine === 'tiered' && (
              <>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary' }}>中盘</Typography>
                  <input type="range" min={ddParticlesRange.min} max={ddParticlesRange.max}
                    value={ddParticles} onChange={(e) => handleParticleChange('dd', Number(e.target.value))}
                    style={{ width: 60, height: 16 }} />
                  <Typography variant="caption" sx={{ fontSize: '0.65rem', fontWeight: 600, minWidth: 24 }}>{ddParticles}</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary' }}>残局</Typography>
                  <input type="range" min={alphaMuParticlesRange.min} max={alphaMuParticlesRange.max}
                    value={alphaMuParticles} onChange={(e) => handleParticleChange('alphaMu', Number(e.target.value))}
                    style={{ width: 60, height: 16 }} />
                  <Typography variant="caption" sx={{ fontSize: '0.65rem', fontWeight: 600, minWidth: 24 }}>{alphaMuParticles}</Typography>
                </Box>
              </>
            )}
            {playEngine === 'alphamu' && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary' }}>粒子</Typography>
                <input type="range" min={alphaMuParticlesRange.min} max={alphaMuParticlesRange.max}
                  value={alphaMuParticles} onChange={(e) => handleParticleChange('alphaMu', Number(e.target.value))}
                  style={{ width: 72, height: 16 }} />
                <Typography variant="caption" sx={{ fontSize: '0.65rem', fontWeight: 600, minWidth: 24 }}>{alphaMuParticles}</Typography>
              </Box>
            )}
            {playEngine === 'mcts' && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary' }}>粒子</Typography>
                <input type="range" min={mctsParticlesRange.min} max={mctsParticlesRange.max}
                  value={mctsParticles} onChange={(e) => handleParticleChange('mcts', Number(e.target.value))}
                  style={{ width: 72, height: 16 }} />
                <Typography variant="caption" sx={{ fontSize: '0.65rem', fontWeight: 600, minWidth: 24 }}>{mctsParticles}</Typography>
              </Box>
            )}
          </Box>
        </Box>

        <Divider orientation="vertical" flexItem sx={{ borderColor: theme.palette.divider, flexShrink: 0 }} />

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0 }}>
          <Typography variant="h6" sx={{ fontSize: '0.85rem' }}>
            发牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'nowrap', gap: 1, alignItems: 'center' }}>
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
