import { Box, Typography, Paper, ToggleButton, ToggleButtonGroup, FormControlLabel, Checkbox, Button, IconButton, Tooltip, useTheme } from '@mui/material'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import CardTable from './CardTable'
import BiddingTable from './BiddingTable'
import { hasAnyHuman, getHumanPositions, getPartnerPosition } from '../utils/position'
import { PANEL_LAYOUT } from '../styles/constants'
import { useGame } from '../context/GameContext'
import { useBidding } from '../context/BiddingContext'
import { usePlay } from '../context/PlayContext'

// 重构后：state 从 Game/Bidding/Play Context 获取，仅保留业务回调与派生值作为 props
function CardTablePanel({
  isMobile,
  // 派生值（App 端计算后传入）
  declarer,
  // 业务回调
  onAnalyzeContract,
  onToggleDoubleDummy,
  onDealerChange,
  onPositionRoleChange,
  onClearAllHands,
  onSimulatedReset,
  onEditHands,
  onEditBidding,
  onPlayCardClick,
  onSetPlayHand,
  onImageDeal,
  onScreenshotDeal,
  onCustomDeal,
  onDeal,
  onHandCardClick,
  onManualPlay,
  onStudyModeChange,
  addBid,
  startBidding,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  // ── 从 Context 获取 state（替代原 70 个 props）──
  const {
    hands, setHands,
    loading, aiThinking,
    gameMode, dealer,
    showPartnerHand, setShowPartnerHand,
    showOpponentHands, setShowOpponentHands,
    positionRoles,
    readonlyMode, mode,
    studyMode,
    imageOpeningLead,
    dealMode,
  } = useGame()

  const {
    biddingSequence, currentBidder,
    isBiddingComplete,
    outputFormats, outputFormatsLoading,
    analyzeLoading,
    currentBiddingPosition,
    showDoubleDummy, doubleDummyResult, doubleDummyLoading,
    biddingTotalTime,
    biddingStarted, stopBidding,
    aiBiddingHistory,
  } = useBidding()

  const {
    playState, showPlayPanel,
    lastCompletedTrick, isPlayPaused,
    playInitiated,
    showPlayedCards, setShowPlayedCards,
    playCenterView, setPlayCenterView,
    showDDHints, toggleDDHints,
    ddHints,
    reviewCursor,
  } = usePlay()

  // 复盘游标对应的墩（派生）
  const reviewTrick = reviewCursor != null && playState?.tricks ? playState.tricks[reviewCursor] : null

  // 检测是否四家手牌齐全（模拟实战牌不全时隐藏小房子/DD相关功能）
  const allHandsComplete = ['南','北','东','西'].every(p => {
    const h = hands?.[p]
    return h && (h.spades || h.hearts || h.diamonds || h.clubs)
  })
  return (
    <Paper elevation={3} sx={{
      p: 1,
      bgcolor: isDark ? 'rgba(30, 41, 59, 0.9)' : (isMobile ? '#f5f5f5' : '#e8e8e8'),
      display: 'flex',
      flexDirection: 'column',
      flex: isMobile ? undefined : '1 1 0%',
      minWidth: isMobile ? undefined : PANEL_LAYOUT.minWidth,
      maxWidth: isMobile ? undefined : PANEL_LAYOUT.maxWidth,
      width: isMobile ? '100%' : undefined,
      height: isMobile ? 'auto' : `${PANEL_LAYOUT.height}px`,
      overflow: 'hidden'
    }}>
      <Box sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        mb: 0.5,
        flexShrink: 0,
        minHeight: 40,
        flexWrap: isMobile ? 'wrap' : 'nowrap',
        gap: isMobile ? 0.5 : 0,
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="h6" sx={{ fontWeight: 600, fontSize: '1rem', color: isDark ? '#e2e8f0' : undefined }}>
            {showPlayPanel ? '打牌阶段' : '当前牌局'}
          </Typography>
          {!showPlayPanel && (
            <ToggleButtonGroup
              value={showDoubleDummy ? 'result' : 'table'}
              exclusive
              onChange={(e, newValue) => {
                if (newValue !== null) {
                  onToggleDoubleDummy(newValue === 'result')
                }
              }}
              size="small"
              sx={{ height: 24 }}
              disabled={!isBiddingComplete()}
            >
              <ToggleButton value="table" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 50 }}>
                叫牌过程
              </ToggleButton>
              {allHandsComplete && (
                <ToggleButton value="result" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 50 }}>
                  小房子
                </ToggleButton>
              )}
            </ToggleButtonGroup>
          )}
          {showPlayPanel && (
            <ToggleButtonGroup
              value={playCenterView || 'play'}
              exclusive
              onChange={(e, newValue) => {
                if (newValue !== null) {
                  setPlayCenterView(newValue)
                  onToggleDoubleDummy(newValue === 'result')
                }
              }}
              size="small"
              sx={{ height: 24 }}
            >
              <ToggleButton value="play" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 40 }}>
                出牌状态
              </ToggleButton>
              <ToggleButton value="bidding" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 40 }}>
                叫牌过程
              </ToggleButton>
              {allHandsComplete && (
                <ToggleButton value="result" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 40 }}>
                  小房子
                </ToggleButton>
              )}
            </ToggleButtonGroup>
          )}
          {showPlayPanel && toggleDDHints && ['南','北','东','西'].every(p => playState?.hands?.[p]?.length > 0) && (
            <Tooltip title={showDDHints ? '隐藏DD提示' : '显示DD提示'} arrow>
              <IconButton size="small" onClick={toggleDDHints} sx={{ p: 0.3 }}>
                {showDDHints ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          )}

        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {!showPlayPanel && hasAnyHuman(positionRoles) && getHumanPositions(positionRoles).length < 3 && (
            <>
              <Typography variant="body2" sx={{ fontSize: '0.75rem', fontWeight: 700, mr: 0 }}>
                {gameMode === 'pair' ? '双人练习' : '四人练习'}
              </Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={showPartnerHand}
                    onChange={(e) => setShowPartnerHand(e.target.checked)}
                    size="small"
                  />
                }
                label="队友手牌"
                sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={showOpponentHands}
                    onChange={(e) => setShowOpponentHands(e.target.checked)}
                    size="small"
                  />
                }
                label="对方手牌"
                sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
              />
            </>
          )}
          {/* 打牌checkbox：仅四家全有手牌时显示（正常发牌练习模式），模拟实战不显示 */}
          {showPlayPanel && hasAnyHuman(positionRoles) && ['南','北','东','西'].every(p => {
            const h = hands?.[p]; return h && (h.spades || h.hearts || h.diamonds || h.clubs)
          }) && (
            <>
              {positionRoles[declarer] === 'ai' ? (
                <>
                  <FormControlLabel
                    control={<Checkbox checked={showPartnerHand} onChange={(e) => setShowPartnerHand(e.target.checked)} size="small" />}
                    label="队友手牌"
                    sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
                  />
                  <FormControlLabel
                    control={<Checkbox checked={showOpponentHands} onChange={(e) => setShowOpponentHands(e.target.checked)} size="small" />}
                    label="对方手牌"
                    sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
                  />
                </>
              ) : (
                <FormControlLabel
                  control={<Checkbox checked={showOpponentHands} onChange={(e) => setShowOpponentHands(e.target.checked)} size="small" />}
                  label="对方手牌"
                  sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
                />
              )}
            </>
          )}
          {showPlayPanel && (
            <FormControlLabel
              control={<Checkbox checked={showPlayedCards} onChange={(e) => setShowPlayedCards(e.target.checked)} size="small" />}
              label="显示已出"
              sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
            />
          )}
          {showPlayPanel && (
            <FormControlLabel
              control={<Checkbox checked={studyMode} onChange={(e) => onStudyModeChange(e.target.checked)} size="small" />}
              label="研究模式"
              sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem', color: studyMode ? '#e65100' : undefined, fontWeight: studyMode ? 700 : undefined }, mr: 0, height: 24 }}
            />
          )}
          {!showPlayPanel && (
          <Box sx={{ display: 'flex', gap: 0.5, ml: 1, borderLeft: '1px solid', borderColor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)', pl: 1 }}>
            <Button
              variant="contained"
              size="small"
              onClick={() => onDeal(dealMode)}
              disabled={loading || aiThinking}
              sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, minWidth: 36, px: 0.5, py: 0 }}
            >
              发牌
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={onCustomDeal}
              disabled={loading}
              sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, minWidth: 36, px: 0.5 }}
            >
              手动
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={onImageDeal}
              disabled={loading}
              sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, minWidth: 36, px: 0.5 }}
            >
              图片
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={onScreenshotDeal}
              disabled={loading}
              sx={{ fontSize: '0.75rem', textTransform: 'none', height: 24, minWidth: 36, px: 0.5 }}
            >
              截屏
            </Button>
          </Box>
          )}
        </Box>
      </Box>
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flex: isMobile ? 1 : '1 1 auto',
        minHeight: 0,
        overflow: 'hidden',
      }}>
        <CardTable
          hands={hands}
          currentBidder={currentBidder}
          dealer={dealer}
          gameMode={gameMode}
          showPartnerHand={showPartnerHand}
          showOpponentHands={showOpponentHands}
          getPartnerPosition={getPartnerPosition}
          renderBiddingTable={() => <BiddingTable biddingSequence={biddingSequence} dealer={dealer} />}
          checkBiddingComplete={isBiddingComplete}
          outputFormats={outputFormats}
          outputFormatsLoading={outputFormatsLoading}
          handleAnalyzeContract={onAnalyzeContract}
          analyzeLoading={analyzeLoading}
          currentBiddingPosition={currentBiddingPosition}
          showDoubleDummy={showDoubleDummy}
          doubleDummyResult={doubleDummyResult}
          doubleDummyLoading={doubleDummyLoading}
          biddingTotalTime={biddingTotalTime}
          positionRoles={positionRoles}
          onPositionRoleChange={onPositionRoleChange}
          onDealerChange={onDealerChange}
          onClearAllHands={onClearAllHands}
          onSimulatedReset={onSimulatedReset}
          onEditHands={onEditHands}
          onEditBidding={onEditBidding}
          setHands={setHands}
          biddingStarted={biddingStarted}
          stopBidding={stopBidding}
          declarer={declarer}
          playState={playState}
          showPlayPanel={showPlayPanel}
          lastCompletedTrick={lastCompletedTrick}
          isPlayPaused={isPlayPaused}
          playInitiated={playInitiated}
          aiLoading={aiThinking}
          showPlayedCards={showPlayedCards}
          playCenterView={playCenterView}
          aiBiddingHistory={aiBiddingHistory}
          onPlayCardClick={onPlayCardClick}
          onSetPlayHand={onSetPlayHand}
          readonlyMode={readonlyMode}
          mode={mode}
          imageOpeningLead={imageOpeningLead}
          addBid={addBid}
          isBiddingCompleteFn={isBiddingComplete}
          onHandCardClick={onHandCardClick}
          onManualPlay={onManualPlay}
          biddingSequence={biddingSequence}
          cardHints={ddHints}
          startBidding={startBidding}
          reviewCursor={reviewCursor}
          reviewTrick={reviewTrick}
        />
      </Box>
    </Paper>
  )
}

export default CardTablePanel
