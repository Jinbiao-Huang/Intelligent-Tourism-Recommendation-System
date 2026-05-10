import { test, expect } from '@playwright/test'

test('redirects unauthenticated users to auth page', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/auth$/)
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
})

test('shows planner page when session is present', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('authToken', 'test-token')
    sessionStorage.setItem(
      'user',
      JSON.stringify({ id: 1, username: 'TestUser', email: 'test@example.com', isAdmin: false })
    )
  })

  await page.goto('/')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: /旅游协作工作台/ })).toBeVisible()
  await expect(page.getByText('规划您的奇妙旅程')).toBeVisible()
})
