import { test, expect } from '@playwright/test'

test('captures homepage performance timing', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('authToken', 'test-token')
    sessionStorage.setItem(
      'user',
      JSON.stringify({ id: 1, username: 'TestUser', email: 'test@example.com', isAdmin: false })
    )
  })

  await page.goto('/', { waitUntil: 'load' })

  const metrics = await page.evaluate(() => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    const paints = performance.getEntriesByType('paint') as PerformanceEntry[]
    const fcpEntry = paints.find((entry) => entry.name === 'first-contentful-paint')

    return {
      domContentLoaded: navigation ? navigation.domContentLoadedEventEnd : null,
      loadEventEnd: navigation ? navigation.loadEventEnd : null,
      fcp: fcpEntry ? fcpEntry.startTime : null
    }
  })

  expect(metrics.domContentLoaded).not.toBeNull()
  expect(metrics.loadEventEnd).not.toBeNull()

  if (metrics.domContentLoaded !== null) {
    expect(metrics.domContentLoaded).toBeLessThan(5000)
  }
  if (metrics.loadEventEnd !== null) {
    const loadThreshold = process.env.CI ? 8000 : 25000
    expect(metrics.loadEventEnd).toBeLessThan(loadThreshold)
  }

  if (metrics.fcp !== null) {
    const fcpThreshold = process.env.CI ? 4000 : 12000
    expect(metrics.fcp).toBeLessThan(fcpThreshold)
  }
})
