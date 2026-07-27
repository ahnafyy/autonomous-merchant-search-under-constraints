import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("renders verified research content without overflow", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/");

  await expect(page.locator("#paper-title")).toHaveText(
    "Autonomous Shopping Optimizer",
  );
  const primaryResult = page.locator(".hero-result strong");
  await expect(primaryResult).toContainText("Choose the next merchant and when to buy");
  await expect(primaryResult).toBeInViewport();
  await expect(page.getByText("Ahnaf Prio", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Generated artifacts" })).toBeVisible();
  await expect(page.getByRole("link", { name: "autonomous-shopping-optimizer" })).toHaveCount(2);
  await expect(page.locator('pre[aria-label="Reproduction commands"]')).toHaveCount(0);
  await expect(page.getByText("MERCHANT-PERMIT-OPEN-001", { exact: true })).toBeVisible();
  await expect(page.getByText("no novelty claim yet", { exact: true })).toBeVisible();

  const currentOffer = page.getByRole("spinbutton", { name: "Current offer" });
  const priceCap = page.getByRole("spinbutton", { name: "Maximum purchase price" });
  await expect(page.locator("[data-workbench-action]")).not.toHaveText("Calculating");
  await priceCap.fill("100");
  await currentOffer.fill("110");
  await expect(page.locator("[data-workbench-action]")).not.toHaveText("Buy");
  await expect(page.locator("[data-workbench-explanation]")).toContainText("hard price cap");

  const scenario = page.getByRole("combobox", { name: "Operating regime" });
  await scenario.selectOption("relaxed");
  await expect(page.locator("[data-action]")).toHaveText("Continue");
  await expect(page.locator("[data-readout]")).toContainText("Search again");
  await scenario.selectOption("time-tight");
  await expect(page.locator("[data-action]")).toHaveText("Buy");
  await expect(page.locator("[data-readout]")).toContainText("Buy now");
  await expect(page.locator("[data-next-merchant]")).toHaveText("M4");
  await scenario.selectOption("token-tight");
  await expect(page.locator("[data-next-merchant]")).toHaveText("M2");
  await scenario.selectOption("price-capped");
  await expect(page.locator("[data-action]")).toHaveText("Continue");
  await expect(page.locator("[data-price-cap]")).toHaveText("$100.00");

  const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflows).toBe(false);
  expect(consoleErrors).toEqual([]);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("research-explainer.png"), fullPage: true });
});
