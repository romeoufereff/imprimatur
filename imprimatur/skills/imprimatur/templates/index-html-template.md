# Index HTML Template

Deck viewer with navigation. Copy this template and customize the `slides` array with your slide filenames.

---

## Template Code

**Fill `{{FONT_FAMILY}}` from the active pack** — `typography.familyLabel` in
`design-system.json`, or just run `python3 {PLUGIN}/scripts/ds_config.py`. The viewer chrome
is the one part of a deck that is not a slide, so nothing else sets its font; leaving a
literal here meant every deck's navigation rendered in a fallback face whenever the pack was
not the one this template was written against.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Deck Viewer</title>
  <style>
    /* Reset styles */
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    /* Full-screen layout */
    html, body {
      width: 100%;
      height: 100%;
      background: #111;
      overflow: hidden;
      font-family: "{{FONT_FAMILY}}", "-apple-system", sans-serif;
    }

    /* Slide display in iframe */
    iframe {
      width: 100%;
      height: 100%;
      border: none;
      display: block;
    }

    /* Navigation bar */
    #nav {
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      align-items: center;
      gap: 12px;
      background: rgba(0, 0, 0, 0.7);
      border-radius: 99px;
      padding: 10px 20px;
      z-index: 100;
    }

    /* Navigation buttons */
    #nav button {
      background: none;
      border: 1px solid rgba(255, 255, 255, 0.3);
      color: #fff;
      border-radius: 6px;
      padding: 6px 16px;
      cursor: pointer;
      font-size: 14px;
      transition: all 0.2s ease;
    }

    #nav button:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.6);
    }

    /* Slide counter */
    #counter {
      color: rgba(255, 255, 255, 0.6);
      font-size: 13px;
      min-width: 60px;
      text-align: center;
    }
  </style>
</head>
<body>
  <!-- Slide viewer iframe -->
  <iframe id="frame" src="01-cover.html"></iframe>

  <!-- Navigation controls -->
  <div id="nav">
    <button onclick="prev()">← Prev</button>
    <span id="counter">1 / N</span>
    <button onclick="next()">Next →</button>
  </div>

  <!-- Navigation logic -->
  <script>
    // CUSTOMIZE THIS ARRAY: Add your slide filenames here
    const slides = [
      '01-cover.html',
      '02-big-idea.html',
      '03-problem.html',
      '04-solution.html',
      '05-architecture.html',
      '06-proof.html',
      '07-risks.html',
      '08-next-steps.html'
      // Add more slides as needed
    ];

    let i = 0; // Current slide index
    const frame = document.getElementById('frame');
    const counter = document.getElementById('counter');

    // Navigate to slide at index n (clamped to valid range)
    function go(n) {
      i = Math.max(0, Math.min(slides.length - 1, n));
      frame.src = slides[i];
      counter.textContent = `${i + 1} / ${slides.length}`;
    }

    // Go to next slide
    function next() {
      go(i + 1);
    }

    // Go to previous slide
    function prev() {
      go(i - 1);
    }

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        next();
      }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        prev();
      }
    });

    // Initialize: load first slide
    go(0);
  </script>
</body>
</html>
```

---

## How to Use

1. **Copy the template** above
2. **Customize the slides array:**
   ```javascript
   const slides = [
     '01-your-slide-one.html',
     '02-your-slide-two.html',
     '03-your-slide-three.html',
     // ... add all your slides
   ];
   ```
3. **Save as `index.html`** in your deck folder
4. **Test in browser:**
   - Open index.html
   - Verify all slides load
   - Test navigation (buttons + keyboard arrows)
   - Check slide counter shows correct total

---

## Features

- **Responsive iframe:** Slides fill the entire viewport
- **Navigation buttons:** Prev/Next buttons at bottom
- **Slide counter:** Shows "current / total" slide count
- **Keyboard shortcuts:**
  - `Arrow Right` / `Arrow Down` → Next slide
  - `Arrow Left` / `Arrow Up` → Previous slide
- **Bounds checking:** Can't go before first slide or after last slide
- **Dark theme:** Minimalist dark background keeps focus on slides

---

## Customization

### Change starting slide
Replace `go(0)` with `go(n)` where n is the 0-indexed slide number:
```javascript
go(3); // Start on slide 4
```

### Change button text
Update the button labels:
```html
<button onclick="prev()">⬅ Previous</button>
<button onclick="next()">Next ➡</button>
```

### Change navigation bar position
Update the `#nav` CSS (default is bottom-center):
```css
{
  bottom: 20px;      /* Distance from bottom */
  left: 50%;         /* Horizontal center */
  /* Or use: top, right instead */
}
```

### Change colors/styling
Edit the CSS in the `<style>` section:
```css
background: rgba(0, 0, 0, 0.7);  /* Dark background */
color: #fff;                      /* White text */
/* etc. */
```

---

## Notes

- **Keyboard focus:** Keyboard navigation only works when the window has focus (click on slide first if arrows don't work)
- **File paths:** Use relative paths (filenames only) if HTML and slides are in the same folder
- **Absolute paths:** Use full paths if slides are in a subfolder: `slides/01-cover.html`
- **Cross-origin:** If opening from `file://` URL, some browsers may block iframe content — serve over HTTP for production use
