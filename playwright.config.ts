import { defineConfig, devices } from "@playwright/test";
// BASE_URL: the deployed site (CI) or a local preview (npm run preview).
export default defineConfig({
  testDir: "tests", timeout: 90_000, retries: 1, workers: 2,
  use: { baseURL: process.env.BASE_URL || "http://localhost:4173/", trace: "off", ...(process.env.PW_EXE ? { launchOptions: { executablePath: process.env.PW_EXE } } : {}) },
  projects: [
    { name: "desktop", testIgnore: /watch\.spec/, use: { viewport: { width: 1600, height: 900 } } },
    { name: "tablet", testIgnore: /watch\.spec/, use: { viewport: { width: 768, height: 1024 } } },
    { name: "phone", testIgnore: /watch\.spec/, use: { ...devices["Pixel 7"], viewport: { width: 360, height: 760 } } },
    // ZopStopper (/watch/): desktop 1440 and phone 390
    { name: "watch-desktop", testMatch: /watch\.spec/, use: { viewport: { width: 1440, height: 900 } } },
    { name: "watch-phone", testMatch: /watch\.spec/, use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
  ],
});
