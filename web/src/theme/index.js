import { createTheme, alpha } from '@mui/material/styles';

const modernColors = {
  primary: {
    main: '#6366f1',
    light: '#818cf8',
    dark: '#4f46e5',
    contrastText: '#ffffff',
  },
  secondary: {
    main: '#ec4899',
    light: '#f472b6',
    dark: '#db2777',
    contrastText: '#ffffff',
  },
  suits: {
    spades: '#1e293b',
    hearts: '#ef4444',
    diamonds: '#f97316',
    clubs: '#22c55e',
    notrump: '#8b5cf6',
  },
  error: {
    main: '#ef4444',
    light: '#f87171',
    dark: '#dc2626',
    contrastText: '#ffffff',
  },
  warning: {
    main: '#f59e0b',
    light: '#fbbf24',
    dark: '#d97706',
    contrastText: '#ffffff',
  },
  info: {
    main: '#3b82f6',
    light: '#60a5fa',
    dark: '#2563eb',
    contrastText: '#ffffff',
  },
  success: {
    main: '#10b981',
    light: '#34d399',
    dark: '#059669',
    contrastText: '#ffffff',
  },
  background: {
    default: '#f8fafc',
    paper: '#ffffff',
    table: '#0f172a',
  },
  text: {
    primary: '#1e293b',
    secondary: '#64748b',
    disabled: '#94a3b8',
  },
  divider: '#e2e8f0',
  grey: {
    50: '#f8fafc',
    100: '#f1f5f9',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a',
  },
};

const theme = createTheme({
  palette: {
    ...modernColors,
    mode: 'light',
  },
  typography: {
    fontFamily: '"Inter", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    h1: {
      fontSize: '2.5rem',
      fontWeight: 700,
      letterSpacing: '-0.02em',
      color: modernColors.text.primary,
    },
    h2: {
      fontSize: '2rem',
      fontWeight: 700,
      letterSpacing: '-0.01em',
      color: modernColors.text.primary,
    },
    h3: {
      fontSize: '1.5rem',
      fontWeight: 600,
      letterSpacing: '-0.01em',
      color: modernColors.text.primary,
    },
    h4: {
      fontSize: '1.25rem',
      fontWeight: 600,
      color: modernColors.text.primary,
    },
    h5: {
      fontSize: '1.125rem',
      fontWeight: 600,
      color: modernColors.text.primary,
    },
    h6: {
      fontSize: '1rem',
      fontWeight: 600,
      color: modernColors.text.primary,
    },
    subtitle1: {
      fontSize: '1rem',
      fontWeight: 500,
      color: modernColors.text.secondary,
    },
    subtitle2: {
      fontSize: '0.875rem',
      fontWeight: 500,
      color: modernColors.text.secondary,
    },
    body1: {
      fontSize: '1rem',
      color: modernColors.text.primary,
    },
    body2: {
      fontSize: '0.875rem',
      color: modernColors.text.secondary,
    },
    button: {
      fontWeight: 600,
      textTransform: 'none',
    },
  },
  shape: {
    borderRadius: 12,
  },
  shadows: [
    'none',
    '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
    '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
    '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
    '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
    '0 25px 50px -12px rgb(0 0 0 / 0.25)',
    ...Array(18).fill('0 25px 50px -12px rgb(0 0 0 / 0.25)'),
  ],
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          background: 'linear-gradient(135deg, #f8fafc 0%, #e0e7ff 50%, #fce7f3 100%)',
          backgroundAttachment: 'fixed',
          minHeight: '100vh',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          fontWeight: 600,
          padding: '10px 20px',
          transition: 'all 0.2s ease',
          '&:hover': {
            transform: 'translateY(-1px)',
          },
        },
        contained: {
          boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.25)',
          '&:hover': {
            boxShadow: '0 6px 20px 0 rgba(99, 102, 241, 0.35)',
          },
        },
        containedPrimary: {
          background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
          '&:hover': {
            background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
          },
        },
        containedSecondary: {
          background: 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)',
          boxShadow: '0 4px 14px 0 rgba(236, 72, 153, 0.25)',
          '&:hover': {
            background: 'linear-gradient(135deg, #db2777 0%, #ec4899 100%)',
            boxShadow: '0 6px 20px 0 rgba(236, 72, 153, 0.35)',
          },
        },
        outlined: {
          borderWidth: 2,
          '&:hover': {
            borderWidth: 2,
          },
        },
        outlinedPrimary: {
          borderColor: modernColors.primary.main,
          '&:hover': {
            backgroundColor: alpha(modernColors.primary.main, 0.08),
            borderColor: modernColors.primary.dark,
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          backgroundImage: 'none',
          backgroundColor: alpha('#ffffff', 0.9),
          backdropFilter: 'blur(10px)',
        },
        elevation1: {
          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)',
        },
        elevation2: {
          boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.05), 0 4px 6px -4px rgb(0 0 0 / 0.05)',
        },
        elevation3: {
          boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.05), 0 8px 10px -6px rgb(0 0 0 / 0.05)',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          border: `1px solid ${alpha(modernColors.primary.main, 0.1)}`,
          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)',
          transition: 'all 0.3s ease',
          '&:hover': {
            boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.1)',
            transform: 'translateY(-2px)',
          },
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%)',
          boxShadow: '0 4px 20px 0 rgba(99, 102, 241, 0.3)',
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          fontWeight: 500,
        },
        standardSuccess: {
          backgroundColor: alpha(modernColors.success.main, 0.1),
          color: modernColors.success.dark,
          border: `1px solid ${alpha(modernColors.success.main, 0.2)}`,
        },
        standardError: {
          backgroundColor: alpha(modernColors.error.main, 0.1),
          color: modernColors.error.dark,
          border: `1px solid ${alpha(modernColors.error.main, 0.2)}`,
        },
        standardWarning: {
          backgroundColor: alpha(modernColors.warning.main, 0.1),
          color: modernColors.warning.dark,
          border: `1px solid ${alpha(modernColors.warning.main, 0.2)}`,
        },
        standardInfo: {
          backgroundColor: alpha(modernColors.info.main, 0.1),
          color: modernColors.info.dark,
          border: `1px solid ${alpha(modernColors.info.main, 0.2)}`,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 500,
        },
        colorPrimary: {
          background: `linear-gradient(135deg, ${modernColors.primary.main} 0%, ${modernColors.primary.light} 100%)`,
        },
        colorSecondary: {
          background: `linear-gradient(135deg, ${modernColors.secondary.main} 0%, ${modernColors.secondary.light} 100%)`,
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 10,
            transition: 'all 0.2s ease',
            '&:hover': {
              boxShadow: `0 0 0 2px ${alpha(modernColors.primary.main, 0.1)}`,
            },
            '&.Mui-focused': {
              boxShadow: `0 0 0 3px ${alpha(modernColors.primary.main, 0.15)}`,
            },
          },
        },
      },
    },
    MuiSelect: {
      styleOverrides: {
        root: {
          borderRadius: 10,
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          fontWeight: 600,
          textTransform: 'none',
          borderRadius: '8px 8px 0 0',
          '&.Mui-selected': {
            background: alpha(modernColors.primary.main, 0.1),
          },
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: {
          height: 3,
          borderRadius: '3px 3px 0 0',
          background: `linear-gradient(90deg, ${modernColors.primary.main} 0%, ${modernColors.secondary.main} 100%)`,
        },
      },
    },
    MuiSwitch: {
      styleOverrides: {
        root: {
          width: 52,
          height: 30,
          padding: 0,
        },
        switchBase: {
          padding: 3,
          '&.Mui-checked': {
            transform: 'translateX(22px)',
            '& + .MuiSwitch-track': {
              backgroundColor: modernColors.primary.main,
              opacity: 1,
            },
          },
        },
        thumb: {
          width: 24,
          height: 24,
          boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
        },
        track: {
          borderRadius: 15,
          backgroundColor: modernColors.grey[300],
          opacity: 1,
        },
      },
    },
    MuiCheckbox: {
      styleOverrides: {
        root: {
          '&.Mui-checked': {
            color: modernColors.primary.main,
          },
        },
      },
    },
    MuiRadio: {
      styleOverrides: {
        root: {
          '&.Mui-checked': {
            color: modernColors.primary.main,
          },
        },
      },
    },
    MuiFab: {
      styleOverrides: {
        root: {
          boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.3)',
        },
        primary: {
          background: `linear-gradient(135deg, ${modernColors.primary.main} 0%, ${modernColors.primary.light} 100%)`,
        },
        secondary: {
          background: `linear-gradient(135deg, ${modernColors.secondary.main} 0%, ${modernColors.secondary.light} 100%)`,
          boxShadow: '0 4px 14px 0 rgba(236, 72, 153, 0.3)',
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          borderRadius: 8,
          backgroundColor: modernColors.grey[800],
          fontSize: '0.8125rem',
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: 20,
          boxShadow: '0 25px 50px -12px rgb(0 0 0 / 0.25)',
        },
      },
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: {
          fontSize: '1.25rem',
          fontWeight: 700,
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          height: 8,
        },
        bar: {
          background: `linear-gradient(90deg, ${modernColors.primary.main} 0%, ${modernColors.secondary.main} 100%)`,
        },
      },
    },
    MuiCircularProgress: {
      styleOverrides: {
        root: {
          color: modernColors.primary.main,
        },
      },
    },
    MuiAvatar: {
      styleOverrides: {
        root: {
          background: `linear-gradient(135deg, ${modernColors.primary.main} 0%, ${modernColors.secondary.main} 100%)`,
        },
      },
    },
    MuiBadge: {
      styleOverrides: {
        badge: {
          fontWeight: 600,
        },
      },
    },
  },
});

export default theme;
