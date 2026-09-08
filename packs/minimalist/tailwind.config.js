tailwind.config = {
  theme: {
    extend: {
      colors: {
        'out-primary': '#201e1d',
        'out-primary-mid': '#605d5d',
        'out-accent': '#ae1800',
        'out-deep': '#2d2b2b',
        'out-support-1': '#7d7979',
        'out-support-2': '#9b9797',
        'out-ink': '#201e1d',
        'out-body': '#444141',
        'out-muted': '#605d5d',
        'out-muted-soft': '#7d7979',
        'out-rule': '#d7d3d3',
        'out-tint': '#f8f4f4',
        'out-surface': '#eae9e9',
        'out-white': '#ffffff',
        'out-neutral-400': '#bab6b6',
        'out-accent-600': '#dd2b0f',
      },

      fontFamily: {
        out: ["Archivo", "system-ui", "-apple-system", "sans-serif"],
      },

      fontSize: {
        'out-display': ['72px', { lineHeight: '1.1', fontWeight: '700' }],
        'out-section': ['64px', { lineHeight: '1.15', fontWeight: '700' }],
        'out-title': ['56px', { lineHeight: '1.15', fontWeight: '700' }],
        'out-h2': ['40px', { lineHeight: '1.2', fontWeight: '700' }],
        'out-h3': ['24px', { lineHeight: '1.3', fontWeight: '700' }],
        'out-metric': ['56px', { lineHeight: '1.0', fontWeight: '700' }],
        'out-lead': ['20px', { lineHeight: '1.6', fontWeight: '400' }],
        'out-subhead': ['24px', { lineHeight: '1.3', fontWeight: '700' }],
        'out-body-sm': ['15px', { lineHeight: '1.55', fontWeight: '400' }],
        'out-label': ['12px', { lineHeight: '1.4', fontWeight: '400' }],
        'out-eyebrow': ['12px', { lineHeight: '1.4', fontWeight: '400' }],
        'out-caption': ['14px', { lineHeight: '1.4', fontWeight: '400' }],
      },

      letterSpacing: {
        'out-eyebrow': '0.08em',
        'out-label': '0.08em',
      },

      borderRadius: {
        'out-sm': '0px',
        'out-md': '0px',
        'out-lg': '0px',
      },
    },
  },
};
