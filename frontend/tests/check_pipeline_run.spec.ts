/**
 * Post-pipeline check — run this after `python brain/main.py` completes.
 *
 * What it verifies:
 *   1. Backend is up and returns at least one run
 *   2. Login works with demo credentials
 *   3. Dashboard shows the latest run card
 *   4. Player loads: first scene image renders, scene counter is visible
 *   5. Scene navigation works (→ arrow advances to scene 2)
 *   6. Audio element is present (if run has audio)
 *
 * Requirements:
 *   - Backend running:  uvicorn backend.server:app --port 8000
 *   - Frontend running: cd frontend && npm run dev
 */

import { test, expect } from '@playwright/test'

const BASE_API = 'http://localhost:8000'

// ─── 1. API HEALTH CHECK ────────────────────────────────────────────────────

test('API: backend is up and has at least one run', async ({ request }) => {
  const res = await request.get(`${BASE_API}/api/runs`)
  expect(res.status()).toBe(200)

  const runs = await res.json()
  expect(Array.isArray(runs)).toBe(true)
  expect(runs.length).toBeGreaterThan(0)

  const latest = runs[0]
  console.log(`\n  Latest run: ${latest.run_id}`)
  console.log(`  Chapter:    ${latest.chapter}`)
  console.log(`  Scenes:     ${latest.scene_count}`)
  console.log(`  Has audio:  ${latest.has_audio}`)
  console.log(`  Has PPT:    ${latest.has_ppt}`)
})

test('API: latest run has scenes and images', async ({ request }) => {
  // Get latest run id
  const runsRes = await request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const runId = runs[0].run_id

  // Fetch full run data
  const runRes = await request.get(`${BASE_API}/api/runs/${runId}`)
  expect(runRes.status()).toBe(200)

  const data = await runRes.json()
  expect(data.learning_steps).toBeDefined()
  expect(data.learning_steps.length).toBeGreaterThan(0)

  // Check scenes exist
  const allScenes = Object.values(data.scenes as Record<string, unknown[]>).flat()
  expect(allScenes.length).toBeGreaterThan(0)
  console.log(`\n  Total scenes in run: ${allScenes.length}`)

  // Check first scene has image_url
  const firstScene = allScenes[0] as Record<string, unknown>
  expect(firstScene.image_url).toBeDefined()
  expect(typeof firstScene.image_url).toBe('string')
  console.log(`  First scene image: ${firstScene.image_url}`)

  // Check image is actually served
  const imgRes = await request.get(`${BASE_API}${firstScene.image_url}`)
  expect(imgRes.status()).toBe(200)
  const contentType = imgRes.headers()['content-type']
  expect(contentType).toContain('image')
  console.log(`  Image served OK (${contentType})`)
})

// ─── 2. LOGIN ───────────────────────────────────────────────────────────────

test('UI: login page loads and demo login works', async ({ page }) => {
  await page.goto('/')

  // Login page should render
  await expect(page.locator('input[type="text"], input[name="username"]').first()).toBeVisible()
  await expect(page.locator('input[type="password"]').first()).toBeVisible()

  // Fill demo credentials
  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()

  // Should redirect to dashboard
  await page.waitForURL('**/dashboard', { timeout: 8000 })
  console.log('\n  Login successful → redirected to dashboard')
})

// ─── 3. DASHBOARD ───────────────────────────────────────────────────────────

test('UI: dashboard shows latest run card', async ({ page }) => {
  // Login first
  await page.goto('/')
  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
  await page.waitForURL('**/dashboard', { timeout: 8000 })

  // Wait for run cards to load
  await page.waitForTimeout(2000)

  // There should be at least one run card visible
  const runCards = page.locator('[data-testid="run-card"], .run-card, a[href*="/player/"]')
  const count = await runCards.count()
  expect(count).toBeGreaterThan(0)
  console.log(`\n  Run cards visible on dashboard: ${count}`)

  // Get latest run id from API to verify it shows up
  const runsRes = await page.request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const latestRunId = runs[0].run_id

  // Check the latest run id appears somewhere on the page
  const pageText = await page.textContent('body')
  const runIdShort = latestRunId.replace('run_', '')   // e.g. "20250331_120000"
  console.log(`  Latest run ID: ${latestRunId}`)

  // Either the full ID or the chapter name should be visible
  const chapterVisible = await page.locator(`text=${runs[0].chapter}`).count()
  expect(chapterVisible).toBeGreaterThan(0)
  console.log(`  Chapter "${runs[0].chapter}" visible on dashboard ✓`)
})

// ─── 4. PLAYER ──────────────────────────────────────────────────────────────

test('UI: player loads first scene image', async ({ page }) => {
  // Get latest run id
  const runsRes = await page.request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const runId = runs[0].run_id

  // Login
  await page.goto('/')
  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
  await page.waitForURL('**/dashboard', { timeout: 8000 })

  // Navigate directly to player
  await page.goto(`/player/${runId}`)
  console.log(`\n  Opened player for: ${runId}`)

  // Wait for scene image to appear and load
  const img = page.locator('img').first()
  await expect(img).toBeVisible({ timeout: 15000 })

  // Check image actually loaded (naturalWidth > 0 means it painted)
  const loaded = await img.evaluate((el: HTMLImageElement) => el.naturalWidth > 0)
  expect(loaded).toBe(true)
  console.log(`  Scene image loaded ✓`)

  // Scene counter or scene ID should be visible somewhere
  const bodyText = await page.textContent('body')
  const hasLS = bodyText?.includes('LS') || bodyText?.includes('Scene') || bodyText?.includes('scene')
  expect(hasLS).toBe(true)
  console.log(`  Scene metadata visible ✓`)
})

test('UI: player scene navigation works (→ goes to scene 2)', async ({ page }) => {
  const runsRes = await page.request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const runId = runs[0].run_id

  // Login + open player
  await page.goto('/')
  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
  await page.waitForURL('**/dashboard', { timeout: 8000 })
  await page.goto(`/player/${runId}`)

  // Wait for first image
  await expect(page.locator('img').first()).toBeVisible({ timeout: 15000 })

  // Capture current image src
  const imgSrcBefore = await page.locator('img').first().getAttribute('src')

  // Press right arrow to go to scene 2
  await page.keyboard.press('ArrowRight')
  await page.waitForTimeout(800)

  // Image should have changed
  const imgSrcAfter = await page.locator('img').first().getAttribute('src')
  expect(imgSrcAfter).not.toEqual(imgSrcBefore)
  console.log(`\n  Scene 1 → Scene 2 navigation ✓`)
  console.log(`  Before: ${imgSrcBefore?.split('/').pop()}`)
  console.log(`  After:  ${imgSrcAfter?.split('/').pop()}`)
})

// ─── 5. AUDIO CHECK ─────────────────────────────────────────────────────────

test('UI: audio element is present if run has audio', async ({ page }) => {
  const runsRes = await page.request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const latestRun = runs[0]

  if (!latestRun.has_audio) {
    console.log('\n  Skipping audio check — this run was generated without audio')
    return
  }

  const runId = latestRun.run_id

  await page.goto('/')
  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
  await page.waitForURL('**/dashboard', { timeout: 8000 })
  await page.goto(`/player/${runId}`)

  await expect(page.locator('img').first()).toBeVisible({ timeout: 15000 })

  // Audio element should be in the DOM
  const audioEl = page.locator('audio')
  const audioCount = await audioEl.count()
  expect(audioCount).toBeGreaterThan(0)
  console.log(`\n  Audio element found in player ✓`)

  // Verify the audio src points to a real file
  const audioSrc = await audioEl.first().getAttribute('src')
  if (audioSrc) {
    const audioRes = await page.request.get(`${BASE_API}${audioSrc}`)
    expect(audioRes.status()).toBe(200)
    console.log(`  Audio file served OK: ${audioSrc.split('/').pop()}`)
  }
})
