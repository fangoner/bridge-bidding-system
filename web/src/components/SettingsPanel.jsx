import { Box, Typography, Paper, FormControl, InputLabel, Select, MenuItem, Button, Divider, Switch, FormControlLabel } from '@mui/material'

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
  dealSystem,
  setDealSystem,
  dealMode,
  setDealMode,
  loading,
  setCustomDealOpen,
  setImageDealOpen,
  handleScreenshotDeal,
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
            <FormControl sx={{ minWidth: 140 }} size="small">
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
                />
              }
              label="深度思考"
              sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.875rem', whiteSpace: 'nowrap' } }}
            />
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

            <Button 
              variant="outlined" 
              size="small" 
              onClick={() => setCustomDealOpen(true)} 
              disabled={loading} 
              sx={{ fontSize: '0.875rem', textTransform: 'none', borderColor: 'rgba(0, 0, 0, 0.23)', height: '40px', px: 1.5 }}
            >
              自定义
            </Button>
            <Button 
              variant="outlined" 
              size="small" 
              onClick={() => setImageDealOpen(true)} 
              disabled={loading} 
              sx={{ fontSize: '0.875rem', textTransform: 'none', borderColor: 'rgba(0, 0, 0, 0.23)', height: '40px', px: 1.5 }}
            >
              图片
            </Button>
            <Button 
              variant="outlined" 
              size="small" 
              onClick={handleScreenshotDeal} 
              disabled={loading} 
              sx={{ fontSize: '0.875rem', textTransform: 'none', borderColor: 'rgba(0, 0, 0, 0.23)', height: '40px', px: 1.5 }}
            >
              截屏
            </Button>
          </Box>
        </Box>
      </Box>
    </Paper>
  )
}

export default SettingsPanel
