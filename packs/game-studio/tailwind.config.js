tailwind.config = {
  theme: {
    extend: {
      colors: {
        'gs-primary': '#C40F4C',
        'gs-primary-mid': '#E8175D',
        'gs-accent': '#4F31D9',
        'gs-deep': '#0A1026',
        'gs-support-1': '#D18A00',
        'gs-support-2': '#00A3AE',
        'gs-ink': '#0A1026',
        'gs-body': '#1B2347',
        'gs-muted': '#5B6486',
        'gs-muted-soft': '#9AA1BE',
        'gs-rule': '#D9DCEA',
        'gs-tint': '#EDEFF7',
        'gs-surface': '#F6F7FB',
        'gs-white': '#ffffff',
        'gs-viz-rose': '#E8175D',
        'gs-viz-amber': '#FFB000',
        'gs-viz-cyan': '#00D3E0',
        'gs-viz-violet': '#6B4DFF',
        'gs-viz-lime': '#B6F02E',
        'gs-viz-green': '#12B76A',
        'gs-viz-rose-soft': '#FF7FA6',
      },

      fontFamily: {
        gs: ["Archivo", "system-ui", "-apple-system", "sans-serif"],
      },

      fontSize: {
        'gs-display': ['132px', { lineHeight: '0.95', fontWeight: '800' }],
        'gs-section': ['132px', { lineHeight: '1.0', fontWeight: '700' }],
        'gs-title': ['84px', { lineHeight: '1.05', fontWeight: '700' }],
        'gs-h2': ['44px', { lineHeight: '1.15', fontWeight: '600' }],
        'gs-h3': ['38px', { lineHeight: '1.2', fontWeight: '600' }],
        'gs-metric': ['132px', { lineHeight: '1.0', fontWeight: '800' }],
        'gs-lead': ['28px', { lineHeight: '1.45', fontWeight: '400' }],
        'gs-subhead': ['38px', { lineHeight: '1.2', fontWeight: '600' }],
        'gs-body-sm': ['22px', { lineHeight: '1.45', fontWeight: '400' }],
        'gs-label': ['20px', { lineHeight: '1.3', fontWeight: '600' }],
        'gs-eyebrow': ['20px', { lineHeight: '1.3', fontWeight: '600' }],
        'gs-caption': ['22px', { lineHeight: '1.45', fontWeight: '400' }],
      },

      letterSpacing: {
        'gs-eyebrow': '0.14em',
        'gs-label': '0.08em',
      },

      borderRadius: {
        'gs-sm': '6px',
        'gs-md': '10px',
        'gs-lg': '16px',
      },
    },
  },
};
