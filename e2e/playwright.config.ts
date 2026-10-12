import { defineConfig, devices } from '@playwright/test';

const python = process.env.E2E_PYTHON ?? 'python3';

export default defineConfig({
  testDir: './tests',
  // One database, one rate limiter: keep the tests sequential.
  workers: 1,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // Real FastAPI app + real Postgres; only retrieval and the LLM are replaced (see server.py).
      command: `${python} server.py`,
      url: 'http://localhost:8000/api/health',
      timeout: 90_000,
      // Never reuse: a server already on :8000 could be your real API (real database, real LLM).
      reuseExistingServer: false,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      // The real frontend, talking to the API above.
      command: 'npx vite --port 3000 --strictPort',
      cwd: '../frontend',
      url: 'http://localhost:3000',
      timeout: 90_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
