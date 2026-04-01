/**
 * Post-pipeline check — run this after `python brain/main.py` completes.
 *
 * What it verifies:
 *   1. Backend is up and returns at least one run
 *   2. Login works with demo credentials
 *   3. Dashboard shows the latest run card
 *   4. Player loads: first scene image renders, scene counter is visible
 *   5. Scene navigation works (→ arrow advances to scene 2)
 *   6. Audio ON/OFF button present (audio is JS-managed, no DOM <audio> element)
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
  console.log(`  Has audio:  ${latest.has_audio}`)
  console.log(`  Has PPT:    ${latest.has_ppt}`)
})

test('API: latest run has scenes and images', async ({ request }) => {
  const runsRes = await request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const runId = runs[0].run_id

  const runRes = await request.get(`${BASE_API}/api/runs/${runId}`)
  expect(runRes.status()).toBe(200)

  const data = await runRes.json()
  expect(data.learning_steps).toBeDefined()
  expect(data.learning_steps.length).toBeGreaterThan(0)

  const allScenes = Object.values(data.scenes as Record<string, unknown[]>).flat()
  expect(allScenes.length).toBeGreaterThan(0)
  console.log(`\n  Total scenes in run: ${allScenes.length}`)

  const firstScene = allScenes[0] as Record<string, unknown>
  expect(firstScene.image_url).toBeDefined()
  expect(typeof firstScene.image_url).toBe('string')
  console.log(`  First scene image: ${firstScene.image_url}`)

  const imgRes = await request.get(`${BASE_API}${firstScene.image_url}`)
  expect(imgRes.status()).toBe(200)
  const contentType = imgRes.headers()['content-type']
  expect(contentType).toContain('image')
  console.log(`  Image served OK (${contentType})`)
})

// ─── 2. LOGIN ───────────────────────────────────────────────────────────────

test('UI: login page loads and demo login works', async ({ page }) => {
  await page.goto('/')

  await expect(page.locator('input[type="text"], input[name="username"]').first()).toBeVisible()
  await expect(page.locator('input[type="password"]').first()).toBeVisible()

  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()

  await page.waitForURL('**/dashboard', { timeout: 8000 })
  console.log('\n  Login successful → redirected to dashboard')
})

// ─── 3. DASHBOARD ───────────────────────────────────────────────────────────

test('UI: dashboard shows latest run card', async ({ page }) => {
  await page.goto('/')
  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
  await page.waitForURL('**/dashboard', { timeout: 8000 })

  await page.waitForTimeout(2000)

  const runCards = page.locator('[data-testid="run-card"], .run-card, a[href*="/player/"]')
  const count = await runCards.count()
  expect(count).toBeGreaterThan(0)
  console.log(`\n  Run cards visible on dashboard: ${count}`)

  const runsRes = await page.request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const latestRunId = runs[0].run_id

  console.log(`  Latest run ID: ${latestRunId}`)

  const chapterVisible = await page.locator(`text=${runs[0].chapter}`).count()
  expect(chapterVisible).toBeGreaterThan(0)
  console.log(`  Chapter "${runs[0].chapter}" visible on dashboard ✓`)
})

// ─── 4. PLAYER ──────────────────────────────────────────────────────────────

test('UI: player loads first scene image', async ({ page }) => {
  const runsRes = await page.request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const runId = runs[0].run_id

  await page.goto('/')
  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
  await page.waitForURL('**/dashboard', { timeout: 8000 })

  await page.goto(`/player/${runId}`)
  console.log(`\n  Opened player for: ${runId}`)

  const img = page.locator('img').first()
  await expect(img).toBeVisible({ timeout: 15000 })

  const loaded = await img.evaluate((el: HTMLImageElement) => el.naturalWidth > 0)
  expect(loaded).toBe(true)
  console.log(`  Scene image loaded ✓`)

  const bodyText = await page.textContent('body')
  const hasLS = bodyText?.includes('LS') || bodyText?.includes('Scene') || bodyText?.includes('scene')
  expect(hasLS).toBe(true)
  console.log(`  Scene metadata visible ✓`)
})

test('UI: player scene navigation works (→ goes to scene 2)', async ({ page }) => {
  const runsRes = await page.request.get(`${BASE_API}/api/runs`)
  const runs = await runsRes.json()
  const runId = runs[0].run_id

  await page.goto('/')
  await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
  await page.locator('input[type="password"]').first().fill('academy123')
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
  await page.waitForURL('**/dashboard', { timeout: 8000 })
  await page.goto(`/player/${runId}`)

  await expect(page.locator('img').first()).toBeVisible({ timeout: 15000 })

  const imgSrcBefore = await page.locator('img').first().getAttribute('src')

  await page.keyboard.press('ArrowRight')
  await page.waitForTimeout(800)

  const imgSrcAfter = await page.locator('img').first().getAttribute('src')
  expect(imgSrcAfter).not.toEqual(imgSrcBefore)
  console.log(`\n  Scene 1 → Scene 2 navigation ✓`)
  console.log(`  Before: ${imgSrcBefore?.split('/').pop()}`)
  console.log(`  After:  ${imgSrcAfter?.split('/').pop()}`)
})

// ─── 5. AUDIO CHECK ─────────────────────────────────────────────────────────
// NOTE: The player uses JS new Audio() API — there is no <audio> DOM element.
// We verify audio support by checking the Audio ON/OFF toggle button and
// confirming the audio file URL is actually served by the backend.

test('UI: audio toggle button present and audio file served if run has audio', async ({ page }) => {
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

  // Audio is JS-managed (new Audio() API), not a DOM <audio> element.
  // Verify the Audio ON/OFF toggle button is present.
  const audioToggle = page.locator('button:has-text("Audio")')
  await expect(audioToggle).toBeVisible({ timeout: 5000 })
  const toggleText = await audioToggle.textContent()
  console.log(`\n  Audio toggle button visible: "${toggleText?.trim()}" ✓`)

  // Verify audio file is actually served via the API
  const runRes = await page.request.get(`${BASE_API}/api/runs/${runId}`)
  const runData = await runRes.json()
  const firstScene = Object.values(runData.scenes as Record<string, Array<{audio?: {combined_url?: string}}>>).flat()[0]
  const audioUrl = firstScene?.audio?.combined_url

  if (audioUrl) {
    const audioRes = await page.request.get(`${BASE_API}${audioUrl}`)
    expect(audioRes.status()).toBe(200)
    console.log(`  Audio file served OK: ${audioUrl.split('/').pop()}`)
  } else {
    console.log('  No combined_url for first scene (acceptable)')
  }
})
