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
} from '@mui/material';

/**
 * AIOutputPanel component for displaying detailed AI bidding output
 *
 * @param {Object} props
 * @param {Array} props.aiBiddingHistory - Array of AI bidding history records
 * @param {boolean} props.simpleDisplayMode - Whether to use simple display mode
 * @param {Function} props.setSimpleDisplayMode - Function to set simple display mode
 * @param {number} props.selectedBiddingIndex - Selected bidding index
 * @param {Function} props.setSelectedBiddingIndex - Function to set selected bidding index
 * @param {string|null} props.currentBiddingPosition - Current bidding position (if AI is bidding)
 */
function AIOutputPanel({
  aiBiddingHistory,
  simpleDisplayMode,
  setSimpleDisplayMode,
  selectedBiddingIndex,
  setSelectedBiddingIndex,
  currentBiddingPosition,
}) {
  // If no AI bidding history, show placeholder
  if (aiBiddingHistory.length === 0) {
    return (
      <Paper elevation={3} sx={{
        p: 2,
        bgcolor: '#f5f5f5',
        display: 'flex',
        flexDirection: 'column',
        width: '600px',
        height: '700px',
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
    <Paper elevation={3} sx={{
      p: 2,
      bgcolor: '#f5f5f5',
      display: 'flex',
      flexDirection: 'column',
      width: '600px',
      height: '700px',
    }}>
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

      {/* Dropdown for selecting bidding record */}
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

      {/* Bidding progress indicator */}
      {currentBiddingPosition && (
        <Alert severity="info" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">
            {currentBiddingPosition}家正在叫牌...
          </Typography>
        </Alert>
      )}

      {/* Content area */}
      <Box sx={{
        flex: 1,
        overflow: 'auto',
        p: 1,
        background: '#fafafa',
        borderRadius: 1,
        border: '1px solid #ddd',
        minHeight: 0,
      }}>
        {simpleDisplayMode ? (
          // Simple display mode: show all records
          aiBiddingHistory.map((record, index) => (
            <Box
              key={index}
              sx={{
                mb: 1,
                p: 1.5,
                background: 'white',
                borderRadius: 1,
                borderLeft: '4px solid #2196f3',
                boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
              }}
            >
              <Typography variant="body2">
                <strong>{record.position}家</strong> → <span style={{ color: '#d32f2f', fontWeight: 'bold' }}>{record.result.bid}</span>
                {record.result.meaning && <span style={{ color: '#666' }}> ({record.result.meaning})</span>}
              </Typography>
            </Box>
          ))
        ) : (
          // Detailed display mode: show single selected record
          (() => {
            const record = selectedBiddingIndex === -1
              ? aiBiddingHistory[aiBiddingHistory.length - 1]
              : aiBiddingHistory[selectedBiddingIndex];
            if (!record) return null;
            const fullOutput = record.result.full_output || {};
            return (
              <Box sx={{
                p: 2,
                background: 'white',
                borderRadius: 1,
                borderLeft: '4px solid #2196f3',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              }}>
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
                      overflow: 'auto',
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
                      overflow: 'auto',
                    }}>
                      {fullOutput["叫牌历史"]}
                    </Box>
                  </Typography>
                )}
                {fullOutput["自己和队友配合花色张数合计"] && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>配合花色张数合计:</strong>
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
                      overflow: 'auto',
                    }}>
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
                      overflow: 'auto',
                    }}>
                      {fullOutput["止张分析"]}
                    </Box>
                  </Typography>
                )}
                {fullOutput["扣叫控制"] && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>扣叫控制:</strong>
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
                      overflow: 'auto',
                    }}>
                      {fullOutput["扣叫控制"]}
                    </Box>
                  </Typography>
                )}
                {fullOutput["自己和队友关键张合计"] && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>关键张合计:</strong>
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
                      overflow: 'auto',
                    }}>
                      {fullOutput["自己和队友关键张合计"]}
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
                      overflow: 'auto',
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
            );
          })()
        )}
      </Box>
    </Paper>
  );
}

export default AIOutputPanel;