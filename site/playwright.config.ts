import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4321",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 13"], browserName: "chromium" } },
  ],
  webServer: {
    cwd: new URL(".", import.meta.url).pathname,
    command: "npx --yes node@22.12.0 node_modules/astro/bin/astro.mjs dev --host 127.0.0.1",
    url: "http://127.0.0.1:4321",
    reuseExistingServer: true,
  },
});
