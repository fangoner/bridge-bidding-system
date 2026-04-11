export const panelStyles = {
  cardTable: {
    desktop: {
      p: 1,
      bgcolor: '#e8e8e8',
      display: 'flex',
      flexDirection: 'column',
      flex: '0 0 auto',
      width: '600px',
      height: '640px',
      overflow: 'hidden'
    },
    mobile: {
      p: 1,
      bgcolor: '#f5f5f5',
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      minHeight: '400px'
    }
  },
  biddingDetail: {
    desktop: {
      p: 1,
      bgcolor: '#e8e8e8',
      display: 'flex',
      flexDirection: 'column',
      flex: '0 0 auto',
      width: '600px',
      height: '640px',
      overflow: 'hidden'
    },
    mobile: {
      p: 0.5,
      bgcolor: '#f5f5f5',
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      height: '400px',
      minHeight: '500px',
      overflow: 'hidden'
    }
  },
  settings: {
    p: { xs: 2, md: 3 },
    mb: 3,
    width: '100%'
  }
}

export const buttonStyles = {
  outlined: {
    fontSize: '0.875rem',
    textTransform: 'none',
    borderColor: 'rgba(0, 0, 0, 0.23)',
    height: '40px',
    px: 1.5
  },
  small: {
    fontSize: '0.75rem',
    textTransform: 'none',
    minWidth: 50
  }
}

export const typographyStyles = {
  title: {
    fontWeight: 600,
    fontSize: '1rem'
  },
  subtitle: {
    fontWeight: 'bold',
    color: '#1976d2'
  }
}

export const dividerStyles = {
  main: {
    mb: 2,
    borderColor: 'rgba(0, 0, 0, 0.3)',
    borderBottomWidth: 2
  },
  section: {
    my: 3,
    borderColor: 'rgba(0, 0, 0, 0.3)',
    borderBottomWidth: 2
  },
  vertical: {
    borderColor: 'rgba(0, 0, 0, 0.2)'
  }
}

export const formControlStyles = {
  small: {
    minWidth: 100
  },
  medium: {
    minWidth: 120
  },
  large: {
    minWidth: 180
  }
}

export const colors = {
  primary: '#1976d2',
  error: '#d32f2f',
  background: {
    light: '#fafafa',
    gray: '#f5f5f5',
    dark: '#e8e8e8'
  },
  border: {
    light: '#e0e0e0',
    medium: '#ddd',
    dark: '#666'
  }
}
