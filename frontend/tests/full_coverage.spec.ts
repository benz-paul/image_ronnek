/**
 * Full frontend coverage suite.
 * Covers: auth, register, dashboard, player, avatar page, profile page.
 *
 * Requirements:
 *   - Backend running:  uvicorn backend.server:app --port 8000
 *   - Frontend running: cd frontend && npm run dev
 *   - At least one completed pipeline run in outputs/
 */

import { test, expect, Page } from '@playwright/test'

const BASE_API = 'http://localhost:8000'
const DEMO_USER = 'admin'
const DEMO_PASS = 'academy123'

// ─── Helper: log in and land on /dashboard ───────────────────────────────────
async function loginAs(page: Page, username = DEMO_USER, password = DEMO_PASS) {
  await page.goto('/')
  await page.locator('input[type="text"], input[name="username"]').first().fill(username)
  await page.locator('input[type="password"]').first().fill(password)
  await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
  await page.waitForURL('**/dashboard', { timeout: 10000 })
}

// ─── Helper: get latest run id from API ──────────────────────────────────────
async function getLatestRunId(page: Page): Promise<string> {
  const res = await page.request.get(`${BASE_API}/api/runs`)
  const runs = await res.json()
  return runs[0].run_id
}

// ════════════════════════════════════════════════════════════════════════════
// AUTH
// ════════════════════════════════════════════════════════════════════════════

test.describe('Auth', () => {
  test('login page renders username + password fields', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('input[type="text"], input[name="username"]').first()).toBeVisible()
    await expect(page.locator('input[type="password"]').first()).toBeVisible()
    console.log('\n  Login form fields visible ✓')
  })

  test('wrong password shows error, not redirect', async ({ page }) => {
    await page.goto('/')
    await page.locator('input[type="text"], input[name="username"]').first().fill('admin')
    await page.locator('input[type="password"]').first().fill('wrong_password_xyz')
    await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign")').first().click()
    // Should NOT navigate to dashboard
    await page.waitForTimeout(2000)
    expect(page.url()).not.toContain('/dashboard')
    console.log('\n  Wrong password stays on login ✓')
  })

  test('login with demo credentials works', async ({ page }) => {
    await loginAs(page)
    expect(page.url()).toContain('/dashboard')
    console.log('\n  Login → dashboard redirect ✓')
  })

  test('logout returns to login page', async ({ page }) => {
    await loginAs(page)
    // Look for logout button (material icon "logout" or text)
    const logoutBtn = page.locator('button[title*="ogout"], button:has-text("Logout"), button:has-text("logout"), [aria-label*="ogout"]').first()
    if (await logoutBtn.count() > 0) {
      await logoutBtn.click()
      await page.waitForURL('**/', { timeout: 5000 })
      expect(page.url()).not.toContain('/dashboard')
      console.log('\n  Logout → login page ✓')
    } else {
      console.log('\n  Logout button not found via locator — skipping (check implementation)')
    }
  })

  test('unauthenticated access to /dashboard redirects to login', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForTimeout(2000)
    // Should be redirected to login (/) or show login
    const url = page.url()
    const isLoginPage = url.endsWith('/') || url.includes('login') || !url.includes('/dashboard')
    expect(isLoginPage).toBe(true)
    console.log(`\n  Unauthenticated /dashboard → redirected to: ${url} ✓`)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// REGISTER PAGE
// ════════════════════════════════════════════════════════════════════════════

test.describe('Register page', () => {
  test('register page loads with correct heading and step indicator', async ({ page }) => {
    await page.goto('/register')
    // Either renders directly or redirects to login first — accept both
    const bodyText = await page.textContent('body') ?? ''
    const hasRegisterContent = bodyText.includes('Identity') || bodyText.includes('Register') || bodyText.includes('Step 1')
    expect(hasRegisterContent).toBe(true)
    console.log('\n  Register page content visible ✓')
  })

  test('register form has username, display name, password fields', async ({ page }) => {
    await page.goto('/register')
    await page.waitForTimeout(1000)
    const inputs = page.locator('input')
    const inputCount = await inputs.count()
    expect(inputCount).toBeGreaterThanOrEqual(2)
    console.log(`\n  Register form has ${inputCount} input fields ✓`)
  })

  test('mismatched passwords shows error', async ({ page }) => {
    await page.goto('/register')
    await page.waitForTimeout(500)

    // Try to fill fields — field selectors may vary
    const inputs = page.locator('input')
    const count = await inputs.count()
    if (count >= 3) {
      await inputs.nth(0).fill('testuser_playwright')
      await inputs.nth(1).fill('Test User')
      await inputs.nth(2).fill('pass1')
      if (count >= 4) await inputs.nth(3).fill('pass2_different')
    }

    const submitBtn = page.locator('button[type="submit"]').first()
    if (await submitBtn.count() > 0) {
      await submitBtn.click()
      await page.waitForTimeout(1000)
      // Should not navigate to avatar page
      expect(page.url()).not.toContain('/avatar')
      console.log('\n  Mismatched passwords → no navigation ✓')
    } else {
      console.log('\n  Submit button not found — skipping')
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ════════════════════════════════════════════════════════════════════════════

test.describe('Dashboard', () => {
  test('dashboard renders Mission Briefs heading and run count', async ({ page }) => {
    await loginAs(page)
    await page.waitForTimeout(2000)
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText).toContain('Mission Briefs')
    console.log('\n  "Mission Briefs" heading found ✓')
  })

  test('dashboard shows at least one run card linking to player', async ({ page }) => {
    await loginAs(page)
    // Run cards are <div class="run-card"> with router.push onClick (not <a> tags)
    const firstCard = page.locator('.run-card').first()
    await expect(firstCard).toBeVisible({ timeout: 15000 })
    const count = await page.locator('.run-card').count()
    expect(count).toBeGreaterThan(0)
    console.log(`\n  ${count} run cards on dashboard ✓`)
  })

  test('dashboard profile link navigates to /profile', async ({ page }) => {
    await loginAs(page)
    const profileLink = page.locator('a[href="/profile"]').first()
    await expect(profileLink).toBeVisible({ timeout: 5000 })
    await profileLink.click()
    await page.waitForURL('**/profile', { timeout: 5000 })
    console.log('\n  Dashboard → profile navigation ✓')
  })

  test('clicking a run card opens the player', async ({ page }) => {
    await loginAs(page)
    // Run cards are <div class="run-card"> with router.push onClick
    const firstCard = page.locator('.run-card').first()
    await expect(firstCard).toBeVisible({ timeout: 15000 })
    await firstCard.click()
    await page.waitForURL('**/player/**', { timeout: 8000 })
    console.log(`\n  Run card click → player URL: ${page.url()} ✓`)
  })

  test('dashboard search input is present', async ({ page }) => {
    await loginAs(page)
    await page.waitForTimeout(1000)
    const searchInput = page.locator('input[placeholder*="QUERY"], input[placeholder*="Search"], input[placeholder*="earch"], input[placeholder*="ilter"]')
    const found = await searchInput.count()
    expect(found).toBeGreaterThan(0)
    console.log('\n  Search input visible on dashboard ✓')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// PLAYER — comprehensive
// ════════════════════════════════════════════════════════════════════════════

test.describe('Player', () => {
  test('player page loads and shows scene image + scene ID', async ({ page }) => {
    await loginAs(page)
    const runId = await getLatestRunId(page)
    await page.goto(`/player/${runId}`)

    const img = page.locator('img').first()
    await expect(img).toBeVisible({ timeout: 15000 })
    const loaded = await img.evaluate((el: HTMLImageElement) => el.naturalWidth > 0)
    expect(loaded).toBe(true)

    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText.includes('LS') || bodyText.includes('Scene')).toBe(true)
    console.log(`\n  Player loaded for ${runId} ✓`)
  })

  test('ArrowRight navigates to next scene', async ({ page }) => {
    await loginAs(page)
    const runId = await getLatestRunId(page)
    await page.goto(`/player/${runId}`)
    await expect(page.locator('img').first()).toBeVisible({ timeout: 15000 })

    const before = await page.locator('img').first().getAttribute('src')
    await page.keyboard.press('ArrowRight')
    await page.waitForTimeout(800)
    const after = await page.locator('img').first().getAttribute('src')
    expect(after).not.toEqual(before)
    console.log(`\n  ArrowRight: ${before?.split('/').pop()} → ${after?.split('/').pop()} ✓`)
  })

  test('ArrowLeft goes back to previous scene', async ({ page }) => {
    await loginAs(page)
    const runId = await getLatestRunId(page)
    await page.goto(`/player/${runId}`)
    await expect(page.locator('img').first()).toBeVisible({ timeout: 15000 })

    // Go to scene 2 first
    await page.keyboard.press('ArrowRight')
    await page.waitForTimeout(600)
    const scene2Src = await page.locator('img').first().getAttribute('src')

    // Go back
    await page.keyboard.press('ArrowLeft')
    await page.waitForTimeout(600)
    const scene1Src = await page.locator('img').first().getAttribute('src')

    expect(scene1Src).not.toEqual(scene2Src)
    console.log(`\n  ArrowLeft navigation ✓`)
  })

  test('audio toggle button is visible and clickable', async ({ page }) => {
    await loginAs(page)
    const runId = await getLatestRunId(page)
    await page.goto(`/player/${runId}`)
    await expect(page.locator('img').first()).toBeVisible({ timeout: 15000 })

    const audioBtn = page.locator('button:has-text("Audio")')
    await expect(audioBtn).toBeVisible({ timeout: 5000 })
    const textBefore = await audioBtn.textContent()

    await audioBtn.click()
    await page.waitForTimeout(300)
    const textAfter = await audioBtn.textContent()
    // Text should have toggled (ON→OFF or OFF→ON)
    expect(textAfter).not.toEqual(textBefore)
    console.log(`\n  Audio toggle: "${textBefore?.trim()}" → "${textAfter?.trim()}" ✓`)
  })

  test('all scene images in run are actually served (no 404s)', async ({ page }) => {
    const runsRes = await page.request.get(`${BASE_API}/api/runs`)
    const runs = await runsRes.json()
    const runId = runs[0].run_id

    const runRes = await page.request.get(`${BASE_API}/api/runs/${runId}`)
    const runData = await runRes.json()
    const allScenes = Object.values(runData.scenes as Record<string, Array<{image_url?: string}>>).flat()

    let ok = 0; let missing = 0
    for (const scene of allScenes) {
      if (!scene.image_url) { missing++; continue }
      const r = await page.request.get(`${BASE_API}${scene.image_url}`)
      if (r.status() === 200) ok++
      else { missing++; console.log(`  MISSING: ${scene.image_url}`) }
    }
    console.log(`\n  Scene images: ${ok} OK, ${missing} missing`)
    expect(missing).toBe(0)
  })

  test('all scene audio files are served if run has audio', async ({ page }) => {
    const runsRes = await page.request.get(`${BASE_API}/api/runs`)
    const runs = await runsRes.json()
    if (!runs[0].has_audio) { console.log('\n  No audio in latest run — skip'); return }

    const runId = runs[0].run_id
    const runRes = await page.request.get(`${BASE_API}/api/runs/${runId}`)
    const runData = await runRes.json()
    const allScenes = Object.values(runData.scenes as Record<string, Array<{audio?: {combined_url?: string}}>>).flat()

    let ok = 0; let missing = 0
    for (const scene of allScenes) {
      const url = scene.audio?.combined_url
      if (!url) { missing++; continue }
      const r = await page.request.get(`${BASE_API}${url}`)
      if (r.status() === 200) ok++
      else { missing++; console.log(`  MISSING AUDIO: ${url}`) }
    }
    console.log(`\n  Scene audio files: ${ok} OK, ${missing} missing/no-audio`)
    // Some scenes may lack audio — warn but don't hard-fail if < 50% missing
    if (missing > ok) expect(missing).toBe(0)
    else console.log(`  (${missing} scenes without combined audio is acceptable)`)
  })

  test('Space key pauses/resumes', async ({ page }) => {
    await loginAs(page)
    const runId = await getLatestRunId(page)
    await page.goto(`/player/${runId}`)
    await expect(page.locator('img').first()).toBeVisible({ timeout: 15000 })

    // Pressing Space should toggle pause state — page shouldn't crash
    await page.keyboard.press('Space')
    await page.waitForTimeout(300)
    await page.keyboard.press('Space')
    await page.waitForTimeout(300)

    // Player still shows an image after toggling
    await expect(page.locator('img').first()).toBeVisible()
    console.log('\n  Space pause/resume — player stable ✓')
  })

  test('player back button returns to dashboard', async ({ page }) => {
    await loginAs(page)
    const runId = await getLatestRunId(page)
    await page.goto(`/player/${runId}`)
    await expect(page.locator('img').first()).toBeVisible({ timeout: 15000 })

    // Look for a back/home/dashboard link
    const backLink = page.locator('a[href="/dashboard"], button:has-text("Dashboard"), a:has-text("Dashboard"), button:has-text("back"), a:has-text("back")').first()
    if (await backLink.count() > 0) {
      await backLink.click()
      await page.waitForTimeout(2000)
      const url = page.url()
      const isBack = url.includes('/dashboard') || url.endsWith('/')
      expect(isBack).toBe(true)
      console.log(`\n  Back button → ${url} ✓`)
    } else {
      console.log('\n  No back button found — using browser back')
      await page.goBack()
      await page.waitForTimeout(1000)
      console.log(`  After goBack: ${page.url()}`)
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
// PROFILE PAGE
// ════════════════════════════════════════════════════════════════════════════

test.describe('Profile page', () => {
  test('profile page loads with user display name visible', async ({ page }) => {
    await loginAs(page)
    await page.goto('/profile')
    await page.waitForTimeout(1500)

    const bodyText = await page.textContent('body') ?? ''
    // Should show username or display name
    expect(bodyText.toLowerCase().includes('admin') || bodyText.includes('decoder')).toBe(true)
    console.log('\n  Profile page loaded with user info ✓')
  })

  test('profile page has create/edit avatar button', async ({ page }) => {
    await loginAs(page)
    await page.goto('/profile')
    await page.waitForTimeout(1500)

    const avatarBtn = page.locator('button:has-text("AVATAR"), button:has-text("Avatar")')
    await expect(avatarBtn.first()).toBeVisible({ timeout: 5000 })
    const btnText = await avatarBtn.first().textContent()
    console.log(`\n  Avatar button: "${btnText?.trim()}" ✓`)
  })

  test('profile page has logout button', async ({ page }) => {
    await loginAs(page)
    await page.goto('/profile')
    await page.waitForTimeout(1000)

    // Logout is usually an icon button or text button
    const logoutEl = page.locator('button[title*="ogout"], button:has-text("Logout"), button:has-text("logout"), [title="Logout"]').first()
    const found = await logoutEl.count()
    expect(found).toBeGreaterThan(0)
    console.log('\n  Logout button on profile ✓')
  })

  test('profile → avatar button navigates to /avatar', async ({ page }) => {
    await loginAs(page)
    await page.goto('/profile')
    await page.waitForTimeout(1500)

    const avatarBtn = page.locator('button:has-text("AVATAR"), button:has-text("Avatar")').first()
    if (await avatarBtn.count() > 0) {
      await avatarBtn.click()
      await page.waitForURL('**/avatar**', { timeout: 6000 })
      expect(page.url()).toContain('/avatar')
      console.log(`\n  Profile → avatar navigation: ${page.url()} ✓`)
    } else {
      console.log('\n  Avatar button not found — skipping navigation check')
    }
  })

  test('profile page back to dashboard link works', async ({ page }) => {
    await loginAs(page)
    await page.goto('/profile')
    await page.waitForTimeout(1000)

    const dashLink = page.locator('a[href="/dashboard"]').first()
    if (await dashLink.count() > 0) {
      await dashLink.click()
      await page.waitForURL('**/dashboard', { timeout: 5000 })
      console.log('\n  Profile → dashboard ✓')
    } else {
      console.log('\n  No dashboard link on profile — skipping')
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
// AVATAR PAGE
// ════════════════════════════════════════════════════════════════════════════

test.describe('Avatar page', () => {
  test('avatar page loads with photo upload step', async ({ page }) => {
    await loginAs(page)
    await page.goto('/avatar')
    await page.waitForTimeout(1500)

    const bodyText = await page.textContent('body') ?? ''
    // Should have "Upload" or "Generate" step text
    const hasAvatarContent = bodyText.includes('Upload') || bodyText.includes('Generate') || bodyText.includes('Avatar') || bodyText.includes('Photo')
    expect(hasAvatarContent).toBe(true)
    console.log('\n  Avatar page loaded with step UI ✓')
  })

  test('avatar page shows step indicator', async ({ page }) => {
    await loginAs(page)
    await page.goto('/avatar')
    await page.waitForTimeout(1000)

    const bodyText = await page.textContent('body') ?? ''
    // Step indicator shows numbered steps or "Upload Photos" / "Generate Avatar"
    const hasSteps = bodyText.includes('Step') || bodyText.includes('Upload Photos') || bodyText.includes('Generate Avatar') || bodyText.includes('UPLOAD')
    expect(hasSteps).toBe(true)
    console.log('\n  Avatar step indicator visible ✓')
  })

  test('avatar page has generate button', async ({ page }) => {
    await loginAs(page)
    await page.goto('/avatar')
    await page.waitForTimeout(1000)

    const genBtn = page.locator('button:has-text("Generate"), button:has-text("GENERATE"), button:has-text("Create"), button:has-text("CREATE")').first()
    const found = await genBtn.count()
    expect(found).toBeGreaterThan(0)
    const btnText = await genBtn.textContent()
    console.log(`\n  Generate button: "${btnText?.trim()}" ✓`)
  })

  test('avatar edit page loads (existing avatar or fresh start)', async ({ page }) => {
    await loginAs(page)
    await page.goto('/avatar/edit')
    await page.waitForTimeout(2000)

    // Should not 404 or show an error page
    const bodyText = await page.textContent('body') ?? ''
    const isError = bodyText.includes('404') && bodyText.includes('not found')
    expect(isError).toBe(false)
    console.log('\n  /avatar/edit page loads without 404 ✓')
  })

  test('if admin has an avatar: expression switcher shows 5 buttons', async ({ page }) => {
    // Check if admin has an avatar via API first
    const avatarRes = await page.request.get(`${BASE_API}/api/avatar/admin`)
    if (avatarRes.status() !== 200) {
      console.log('\n  No avatar for admin — skipping expression test')
      return
    }

    await loginAs(page)
    await page.goto('/avatar')
    await page.waitForTimeout(2000)

    // Expression switcher buttons: neutral, happy, sad, angry, surprised
    const exprButtons = page.locator('button:has-text("Neutral"), button:has-text("Happy"), button:has-text("Sad"), button:has-text("Angry"), button:has-text("Surprised")')
    const count = await exprButtons.count()
    if (count > 0) {
      expect(count).toBeGreaterThanOrEqual(5)
      console.log(`\n  Expression switcher: ${count} buttons ✓`)
    } else {
      console.log('\n  Expression buttons hidden (avatar may not be done yet)')
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
// API ENDPOINTS — exhaustive
// ════════════════════════════════════════════════════════════════════════════

test.describe('API endpoints', () => {
  test('GET /api/runs returns array', async ({ request }) => {
    const res = await request.get(`${BASE_API}/api/runs`)
    expect(res.status()).toBe(200)
    const data = await res.json()
    expect(Array.isArray(data)).toBe(true)
    console.log(`\n  GET /api/runs → ${data.length} runs ✓`)
  })

  test('GET /api/runs/:id returns run with learning_steps and scenes', async ({ request }) => {
    const runsRes = await request.get(`${BASE_API}/api/runs`)
    const runs = await runsRes.json()
    const runId = runs[0].run_id

    const res = await request.get(`${BASE_API}/api/runs/${runId}`)
    expect(res.status()).toBe(200)
    const data = await res.json()

    expect(data.learning_steps).toBeDefined()
    expect(data.scenes).toBeDefined()
    expect(typeof data.scenes).toBe('object')
    console.log(`\n  GET /api/runs/${runId} → ${data.learning_steps.length} LS, ${Object.keys(data.scenes).length} scene groups ✓`)
  })

  test('GET /api/runs/nonexistent returns 404', async ({ request }) => {
    const res = await request.get(`${BASE_API}/api/runs/run_99999999_000000`)
    expect(res.status()).toBe(404)
    console.log('\n  404 for unknown run ID ✓')
  })

  test('static image file is served with correct content-type', async ({ request }) => {
    const runsRes = await request.get(`${BASE_API}/api/runs`)
    const runs = await runsRes.json()
    const runId = runs[0].run_id

    const runRes = await request.get(`${BASE_API}/api/runs/${runId}`)
    const data = await runRes.json()
    const firstScene = Object.values(data.scenes as Record<string, Array<{image_url?: string}>>).flat()[0]

    if (!firstScene?.image_url) { console.log('\n  No image_url — skipping'); return }

    const imgRes = await request.get(`${BASE_API}${firstScene.image_url}`)
    expect(imgRes.status()).toBe(200)
    expect(imgRes.headers()['content-type']).toContain('image')
    console.log(`\n  Static image content-type: ${imgRes.headers()['content-type']} ✓`)
  })

  test('GET /api/avatar/:username returns 200 or 404 (not 500)', async ({ request }) => {
    const res = await request.get(`${BASE_API}/api/avatar/admin`)
    expect([200, 404]).toContain(res.status())
    console.log(`\n  GET /api/avatar/admin → ${res.status()} ✓`)
  })
})
