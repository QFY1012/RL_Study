// Browser settings shared by snapshot.mjs and render.mjs, so the live page and
// every offline render come out of the same viewport, locale and color scheme.
export const CONTEXT = {
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
  locale: "en-US",
  timezoneId: "UTC",
  colorScheme: "light",
  reducedMotion: "reduce",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}

// Waits for fonts and images, then puts every animation in its end state (finite
// ones) or its first frame (infinite ones), so two renders of the same DOM match.
export async function settle(page) {
  await page.evaluate(async () => {
    await document.fonts.ready
    await Promise.all([...document.images].filter((i) => !i.complete).map((i) => new Promise((r) => { i.onload = i.onerror = r; setTimeout(r, 5000) })))
    const freeze = (root) => {
      for (const a of root.getAnimations({ subtree: true })) {
        try { a.finish() } catch { a.pause(); a.currentTime = 0 }
      }
    }
    freeze(document)
    for (const el of document.querySelectorAll("*")) if (el.shadowRoot) freeze(el.shadowRoot)
    for (const v of document.querySelectorAll("video")) { v.pause(); v.currentTime = 0 }
  })
  await page.waitForTimeout(500)
}
