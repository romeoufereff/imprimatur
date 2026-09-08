tailwind.config = {
  theme: {
    extend: {
      colors: {
        'acme-primary': '#416180',
        'acme-primary-mid': '#597ea3',
        'acme-accent': '#749dc4',
        'acme-deep': '#1d2d3d',
        'acme-support-1': '#5d5d60',
        'acme-support-2': '#98989b',
        'acme-ink': '#1d1f20',
        'acme-body': '#424244',
        'acme-muted': '#5d5d60',
        'acme-muted-soft': '#7a7a7d',
        'acme-rule': '#d4d4d7',
        'acme-tint': '#f5f5f8',
        'acme-surface': '#e9e9ea',
        'acme-white': '#ffffff',
      },

      fontFamily: {
        acme: ["Barlow", "system-ui", "-apple-system", "sans-serif"],
      },

      fontSize: {
        'acme-display': ['288px', { lineHeight: '0.95', fontWeight: '600' }],
        'acme-section': ['120px', { lineHeight: '1.0', fontWeight: '600' }],
        'acme-title': ['96px', { lineHeight: '1.05', fontWeight: '600' }],
        'acme-h2': ['40px', { lineHeight: '1.15', fontWeight: '600' }],
        'acme-h3': ['34px', { lineHeight: '1.2', fontWeight: '600' }],
        'acme-metric': ['432px', { lineHeight: '1.0', fontWeight: '600' }],
        'acme-lead': ['34px', { lineHeight: '1.4', fontWeight: '400' }],
        'acme-subhead': ['40px', { lineHeight: '1.3', fontWeight: '700' }],
        'acme-body-sm': ['28px', { lineHeight: '1.4', fontWeight: '400' }],
        'acme-label': ['24px', { lineHeight: '1.3', fontWeight: '500' }],
        'acme-eyebrow': ['24px', { lineHeight: '1.3', fontWeight: '500' }],
        'acme-caption': ['24px', { lineHeight: '1.3', fontWeight: '400' }],
      },

      letterSpacing: {
        'acme-eyebrow': '0.08em',
        'acme-label': '0.08em',
      },

      borderRadius: {
        'acme-sm': '2px',
        'acme-md': '4px',
        'acme-lg': '7px',
      },
    },
  },
};
