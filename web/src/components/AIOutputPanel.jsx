import React from 'react';
import {
  Paper,
  Box,
  Typography,
  Alert,
  CircularProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormControlLabel,
  Checkbox,
  useTheme,
  alpha,
} from '@mui/material';

/**
 * AIOutputPanel component for displaying detailed AI bidding output
 */
function AIOutputPanel({
  aiBiddingHistory,
  simpleDisplayMode,
  setSimpleDisplayMode,
  selectedBiddingIndex,
  setSelectedBiddingIndex,
  currentBiddingPosition,
}) {
  const theme = useTheme();

  // ── Shared sub-styles (theme-aware) ──────────────────────────────────
  const preBlockSx = {
    mt: 0.5,
    p: 1,
    background: alpha(theme.palette.primary.main, 0.04),
    borderRadius: 1,
    fontSize: '0.85rem',
    lineHeight: 1.4,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    border: `1px solid ${theme.palette.divider}`,
    maxHeight: '150px',
    overflow: 'auto',
  };

  const recordCardSx = {
    p: 1.5,
    background: alpha(theme.palette.background.paper, 0.6),
    backdropFilter: 'blur(8px)',
    borderRadius: 1,
    borderLeft: `4px solid ${theme.palette.primary.main}`,
    boxShadow: theme.shadows[1],
  };

  const detailCardSx = {
    p: 2,
    background: alpha(theme.palette.background.paper, 0.6),
    backdropFilter: 'blur(8px)',
    borderRadius: 1,
    borderLeft: `4px solid ${theme.palette.primary.main}`,
    boxShadow: theme.shadows[1],
  };

  const bidColor = theme.palette.error.main;
  const mutedColor = theme.palette.text.secondary;

  // ── Empty state ──────────────────────────────────────────────────────
  if (aiBiddingHistory.length === 0) {
    return (
      <Paper elevation={0} sx={{
        p: 2,
        display: 'flex',
        flexDirection: 'column',
        width: '600px',
        height: '700px',
        background: theme.palette.mode === 'dark'
          ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(30, 41, 59, 0.6) 100%)'
          : 'linear-gradient(135deg, rgba(255, 255, 255, 0.85) 0%, rgba(255, 255, 255, 0.7) 100%)',
        backdropFilter: 'blur(20px) saturate(180%)',
        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.8)'}`,
        borderRadius: 3,
      }}>
        <Typography variant="h6" gutterBottom>
          叫牌细节
        </Typography>
        <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            等待AI叫牌...
          </Typography>
        </Box>
      </Paper>
    );
  }

  return (
    <Paper elevation={0} sx={{
      p: 2,
      display: 'flex',
      flexDirection: 'column',
      width: '600px',
      height: '700px',
      background: theme.palette.mode === 'dark'
        ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(30, 41, 59, 0.6) 100%)'
        : 'linear-gradient(135deg, rgba(255, 255, 255, 0.85) 0%, rgba(255, 255, 255, 0.7) 100%)',
      backdropFilter: 'blur(20px) saturate(180%)',
      WebkitBackdropFilter: 'blur(20px) saturate(180%)',
      border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.8)'}`,
      borderRadius: 3,
    }}>
      {/* ── Header ─────────────────────────────────────────────────── */}
      <Box sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        mb: 2,
        flexWrap: 'wrap',
        gap: 1,
        flexShrink: 0,
      }}>
        <Typography variant="h6">
          叫牌细节
        </Typography>
        <FormControlLabel
          control={
            <Checkbox
              checked={simpleDisplayMode}
              onChange={(e) => setSimpleDisplayMode(e.target.checked)}
            />
          }
          label="简单显示"
          sx={{ ml: 1 }}
        />
      </Box>

      {/* ── Record selector ─────────────────────────────────────────── */}
      {aiBiddingHistory.length > 0 && !simpleDisplayMode && (
        <FormControl size="small" sx={{ mb: 2, minWidth: 200, flexShrink: 0 }}>
          <InputLabel>选择叫牌记录</InputLabel>
          <Select
            value={selectedBiddingIndex}
            label="选择叫牌记录"
            onChange={(e) => setSelectedBiddingIndex(e.target.value)}
          >
            <MenuItem value={-1}>
              最新 ({aiBiddingHistory[aiBiddingHistory.length - 1]?.position}家 - {aiBiddingHistory[aiBiddingHistory.length - 1]?.result.bid})
            </MenuItem>
            {aiBiddingHistory.slice().reverse().slice(1).map((record, idx) => (
              <MenuItem key={idx} value={aiBiddingHistory.length - 2 - idx}>
                {record.position}家 - {record.result.bid}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )}

      {/* ── Progress ────────────────────────────────────────────────── */}
      {currentBiddingPosition && (
        <Alert severity="info" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">
            {currentBiddingPosition}家正在叫牌...
          </Typography>
        </Alert>
      )}

      {/* ── Content ─────────────────────────────────────────────────── */}
      <Box sx={{
        flex: 1,
        overflow: 'auto',
        p: 1,
        background: alpha(theme.palette.background.default, 0.5),
        borderRadius: 1,
        border: `1px solid ${theme.palette.divider}`,
        minHeight: 0,
      }}>
        {simpleDisplayMode ? (
          aiBiddingHistory.map((record, index) => (
            <Box key={index} sx={{ mb: 1, ...recordCardSx }}>
              <Typography variant="body2">
                <strong>{record.position}家</strong> →{' '}
                <span style={{ color: bidColor, fontWeight: 'bold' }}>{record.result.bid}</span>
                {record.result.meaning && (
                  <span style={{ color: mutedColor }}> ({record.result.meaning})</span>
                )}
              </Typography>
            </Box>
          ))
        ) : (
          (() => {
            const record = selectedBiddingIndex === -1
              ? aiBiddingHistory[aiBiddingHistory.length - 1]
              : aiBiddingHistory[selectedBiddingIndex];
            if (!record) return null;
            const fullOutput = record.result.full_output || {};
            return (
              <Box sx={detailCardSx}>
                <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 'bold', color: theme.palette.primary.main }}>
                  {record.timestamp} - {record.position}家
                </Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  <strong>手牌:</strong> {record.hand?.display || '未知'}
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
                    <Box component="pre" sx={preBlockSx}>
                      {fullOutput["手牌分析"]}
                    </Box>
                  </Typography>
                )}
                {fullOutput["叫牌历史"] && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>叫牌历史:</strong>
                    <Box component="pre" sx={preBlockSx}>
                      {fullOutput["叫牌历史"]}
                    </Box>
                  </Typography>
                )}
                {fullOutput["自己和队友配合花色张数合计"] && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>配合花色张数合计:</strong>
                    <Box component="pre" sx={preBlockSx}>
                      {fullOutput["自己和队友配合花色张数合计"]}
                    </Box>
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
                    <strong>是否进局或试探满贯:</strong> {fullOutput["是否进局或试探满贯"]}
                  </Typography>
                )}
                {fullOutput["止张分析"] && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>止张分析:</strong>
                    <Box component="pre" sx={preBlockSx}>
                      {fullOutput["止张分析"]}
                    </Box>
                  </Typography>
                )}
                {fullOutput["扣叫控制"] && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>扣叫控制:</strong>
                    <Box component="pre" sx={preBlockSx}>
                      {fullOutput["扣叫控制"]}
                    </Box>
                  </Typography>
                )}
                {fullOutput["自己和队友关键张合计"] && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>关键张合计:</strong>
                    <Box component="pre" sx={preBlockSx}>
                      {fullOutput["自己和队友关键张合计"]}
                    </Box>
                  </Typography>
                )}

                <Typography variant="body2" sx={{ mt: 1 }}>
                  <strong>选定叫品:</strong>{' '}
                  <span style={{ fontWeight: 'bold', color: bidColor }}>{record.result.bid}</span>
                </Typography>
                {record.result.meaning && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>叫品含义:</strong> {record.result.meaning}
                  </Typography>
                )}
                {record.result.selection_process && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>叫品筛选过程:</strong>
                    <Box component="pre" sx={{ ...preBlockSx, maxHeight: '200px' }}>
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
            );
          })()
        )}
      </Box>
    </Paper>
  );
}

export default AIOutputPanel;
