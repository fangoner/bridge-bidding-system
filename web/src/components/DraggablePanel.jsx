import React from 'react';
import { Paper, Typography, Box } from '@mui/material';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import DragHandleIcon from '@mui/icons-material/DragHandle';

function DraggablePanel({ id, title, children, dragHandle = true }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.9 : 1,
    zIndex: isDragging ? 1000 : 'auto',
  };

  return (
    <Paper
      ref={setNodeRef}
      style={style}
      elevation={isDragging ? 8 : 2}
      sx={{
        p: 1.5,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        touchAction: 'none',
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: 1,
          cursor: dragHandle ? 'grab' : 'default',
          '&:active': dragHandle ? { cursor: 'grabbing' } : {},
        }}
        {...(dragHandle ? { ...attributes, ...listeners } : {})}
      >
        <Typography variant="h6">
          {title}
        </Typography>
        {dragHandle && (
          <DragHandleIcon
            sx={{
              color: 'text.secondary',
              fontSize: '1.2rem',
            }}
          />
        )}
      </Box>
      <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {children}
      </Box>
    </Paper>
  );
}

export default DraggablePanel;
