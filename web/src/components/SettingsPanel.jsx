import { Box, Typography, Paper, FormControl, InputLabel, Select, MenuItem, Button, Divider, Switch, FormControlLabel, TextField } from '@mui/material'

function SettingsPanel({
  showSettings,
  gameMode,
  setGameMode,
  fallbackModel,
  handleFallbackModelChange,
  biddingReasoning,
  handleBiddingReasoningChange,
  playModel,
  handlePlayModelChange,
  playReasoning,
  handlePlayReasoningChange,
  playEngine,
  handlePlayEngineChange,
  ddSampleCount,
  handleDDSampleCountChange,
  dealSystem,
  setDealSystem,
  dealMode,
  setDealMode,
  loading,
}) {
  if (!showSettings) return null

  return (
    <Paper elevation={2} sx={{ p: { xs: 2, md: 3 }, mb: 3, width: '100%' }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'flex-start' }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Typography variant="h6">
            叫牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
            <FormControl sx={{ minWidth: 100 }} size="small">
              <InputLabel>模式</InputLabel>
              <Select value={gameMode} label="模式" onChange={(e) => setGameMode(e.target.value)}>
                <MenuItem value="four">四人</MenuItem>
                <MenuItem value="pair">双人</MenuItem>
              </Select>
            </FormControl>

            <FormControl sx={{ minWidth: 140 }} size="small">
              <InputLabel>模型</InputLabel>
              <Select value={fallbackModel} label="模型" onChange={handleFallbackModelChange}>
                <MenuItem value="deepseek-v4-flash">V4-Flash</MenuItem>
                <MenuItem value="deepseek-v4-pro">V4-Pro</MenuItem>
              </Select>
            </FormControl>

            <FormControlLabel
              control={
                <Switch
                  checked={biddingReasoning}
                  onChange={handleBiddingReasoningChange}
                />
              }
              label="深度思考"
              sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.875rem', whiteSpace: 'nowrap' } }}
            />

            <FormControl sx={{ minWidth: 180 }} size="small">
              <InputLabel>阻击叫牌体系</InputLabel>
              <Select value={dealSystem} label="阻击叫牌体系" onChange={(e) => setDealSystem(e.target.value)}>
                <MenuItem value="2D/2H/2S：自然阻击">2D/2H/2S：自然阻击</MenuItem>
                <MenuItem value="2D：多功能，2H/S：麦德伯格，2NT：双低花">多功能/麦德伯格</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Box>

        <Divider orientation="vertical" flexItem sx={{ borderColor: 'rgba(0, 0, 0, 0.2)' }} />

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Typography variant="h6">
            打牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
            <FormControl sx={{ minWidth: 140 }} size="small" disabled={playEngine !== 'llm' && playEngine !== 'tiered'}>
              <InputLabel>模型</InputLabel>
              <Select value={playModel} label="模型" onChange={handlePlayModelChange}>
                <MenuItem value="deepseek-v4-flash">V4-Flash</MenuItem>
                <MenuItem value="deepseek-v4-pro">V4-Pro</MenuItem>
              </Select>
            </FormControl>

            <FormControlLabel
              control={
                <Switch
                  checked={playReasoning}
                  onChange={handlePlayReasoningChange}
                  disabled={playEngine !== 'llm' && playEngine !== 'tiered'}
                />
              }
              label="深度思考"
              sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.875rem', whiteSpace: 'nowrap' } }}
            />

            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>打牌引擎</InputLabel>
              <Select
                value={playEngine}
                onChange={(e) => handlePlayEngineChange(e.target.value)}
                label="打牌引擎"
              >
                <MenuItem value="llm">LLM 大模型</MenuItem>
                <MenuItem value="mcts">MCTS 搜索</MenuItem>
                <MenuItem value="dd">DD 蒙地卡罗</MenuItem>
                <MenuItem value="hybrid">Hybrid 混合</MenuItem>
                <MenuItem value="tiered">Tiered 分层</MenuItem>
              </Select>
            </FormControl>
            {(playEngine === 'dd' || playEngine === 'hybrid' || playEngine === 'tiered') && (
              <TextField
                label="采样数"
                type="number"
                size="small"
                value={ddSampleCount}
                onChange={(e) => handleDDSampleCountChange(e.target.value)}
                InputProps={{ inputProps: { min: 1, max: 10000 } }}
                sx={{ minWidth: 80, maxWidth: 120 }}
              />
            )}
          </Box>
        </Box>

        <Divider orientation="vertical" flexItem sx={{ borderColor: 'rgba(0, 0, 0, 0.2)' }} />

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Typography variant="h6">
            发牌设置
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
            <FormControl sx={{ minWidth: 100 }} size="small">
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
