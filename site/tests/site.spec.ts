import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("renders verified research content without overflow", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/");

  await expect(page.locator("#paper-title")).toHaveText(
    "When Should a Shopping Agent Stop Searching?",
  );
  const primaryResult = page.locator(".hero-result strong");
  await expect(primaryResult).toContainText(
    "expected saving can repay the next inspection cost",
  );
  await expect(primaryResult).toBeInViewport();
  await expect(page.getByText("Ahnaf Prio", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Source and generated artifacts" })).toBeVisible();
  await expect(page.locator('pre[aria-label="Reproduction commands"]')).toHaveCount(0);
  await expect(page.getByText("PANDORA-ADVANTAGE-001", { exact: true })).toBeVisible();
  await expect(page.getByText("SHOPIFY-SELLER-DECK-STUDY-001", { exact: true })).toBeVisible();

  const decisionRows = page.locator(".decision-table tbody tr");
  expect(await decisionRows.count()).toBeGreaterThan(0);
  await expect(page.getByText("No reliable improvement", { exact: true }).first()).toBeVisible();

  const interactiveDecision = page.locator("[data-recalled-workbench]");
  await expect(interactiveDecision.getByText("Search again", { exact: true })).toBeVisible();
  await interactiveDecision.getByLabel("Tool/API spend").fill("10.00");
  await expect(interactiveDecision.getByText("Buy now", { exact: true })).toBeVisible();

  const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflows).toBe(false);
  expect(consoleErrors).toEqual([]);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("research-explainer.png"), fullPage: true });
});
