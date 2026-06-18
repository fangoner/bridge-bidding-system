// ═══════════════════════════════════════════════════════════════════════════════
// NOTE (2026-06-19): Most style exports below are DEPRECATED.
// Prefer theme tokens via `useTheme()` for colour-aware styles.
// Only PANEL_LAYOUT and formControlStyles sizes remain actively used.
// ═══════════════════════════════════════════════════════════════════════════════

// 桌面版双栏布局共享面板尺寸
export const PANEL_LAYOUT = {
  minWidth: 400,
  maxWidth: 700,
  height: 640,
}

/** @deprecated — use MUI Paper with glass surface via theme */
export const panelStyles = {
  cardTable: {
    desktop: {
      p: 1,
      display: 'flex',
      flexDirection: 'column',
      flex: '0 0 auto',
      width: '600px',
      height: '640px',
      overflow: 'hidden',
    },
    mobile: {
      p: 1,
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      minHeight: '400px',
    },
  },
  biddingDetail: {
    desktop: {
      p: 1,
      display: 'flex',
      flexDirection: 'column',
      flex: '0 0 auto',
      width: '600px',
      height: '640px',
      overflow: 'hidden',
    },
    mobile: {
      p: 0.5,
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      height: '400px',
      minHeight: '500px',
      overflow: 'hidden',
    },
  },
  settings: {
    p: { xs: 2, md: 3 },
    mb: 3,
    width: '100%',
  },
}

/** @deprecated — use MUI Button sx with theme colours */
export const buttonStyles = {
  outlined: {
    fontSize: '0.875rem',
    textTransform: 'none',
    height: '40px',
    px: 1.5,
  },
  small: {
    fontSize: '0.8125rem',
    textTransform: 'none',
    minWidth: 50,
  },
}

/** @deprecated — use theme.palette.text / theme.typography */
export const typographyStyles = {
  title: {
    fontWeight: 600,
    fontSize: '1rem',
  },
  subtitle: {
    fontWeight: 'bold',
  },
}

/** @deprecated — use <Divider /> with theme palette */
export const dividerStyles = {
  main: {
    mb: 2,
    borderBottomWidth: 2,
  },
  section: {
    my: 3,
    borderBottomWidth: 2,
  },
  vertical: {},
}

/** @deprecated — use theme.palette directly */
export const colors = {
  primary: '#1976d2',
  error: '#d32f2f',
  background: {
    light: '#fafafa',
    gray: '#f5f5f5',
    dark: '#e8e8e8',
  },
  border: {
    light: '#e0e0e0',
    medium: '#ddd',
    dark: '#666',
  },
}

export const formControlStyles = {
  small: {
    minWidth: 100,
  },
  medium: {
    minWidth: 120,
  },
  large: {
    minWidth: 180,
  },
}
