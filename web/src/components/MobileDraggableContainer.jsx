import React, { createContext, useContext } from 'react';
import { Box, useMediaQuery, useTheme } from '@mui/material';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import DragHandleIcon from '@mui/icons-material/DragHandle';

const MobileContext = createContext(false);

function SortableItem({ id, children }) {
  const isMobile = useContext(MobileContext);
  
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
    opacity: isDragging ? 0.8 : 1,
    zIndex: isDragging ? 1000 : 'auto',
  };

  if (!isMobile) {
    return children;
  }

  return (
    <Box
      ref={setNodeRef}
      style={style}
      sx={{
        position: 'relative',
      }}
    >
      {children}
      <Box
        {...attributes}
        {...listeners}
        sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          cursor: 'grab',
          color: 'text.secondary',
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          '&:active': { cursor: 'grabbing' },
          zIndex: 10,
          background: 'rgba(255,255,255,0.8)',
          borderRadius: 1,
          p: 0.5,
          touchAction: 'none',
        }}
      >
        <DragHandleIcon sx={{ fontSize: '1rem' }} />
      </Box>
    </Box>
  );
}

function MobileDraggableContainer({ 
  panelOrder, 
  onReorder, 
  children 
}) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 10,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (active.id !== over.id) {
      const oldIndex = panelOrder.indexOf(active.id);
      const newIndex = panelOrder.indexOf(over.id);
      onReorder(arrayMove(panelOrder, oldIndex, newIndex));
    }
  };

  if (!isMobile) {
    return (
      <MobileContext.Provider value={false}>
        {children}
      </MobileContext.Provider>
    );
  }

  return (
    <MobileContext.Provider value={true}>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={panelOrder}
          strategy={verticalListSortingStrategy}
        >
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {children}
          </Box>
        </SortableContext>
      </DndContext>
    </MobileContext.Provider>
  );
}

export { SortableItem };
export default MobileDraggableContainer;
