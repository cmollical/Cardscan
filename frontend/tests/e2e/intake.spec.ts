import { test, expect, type Page } from "@playwright/test";
import path from "node:path";
const fixture = path.resolve("tests/e2e/synthetic-front.jpg");
const back = path.resolve("tests/e2e/synthetic-back.jpg");
async function capture(page: Page) {
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await page.getByLabel("Upload front", { exact: true }).setInputFiles(fixture);
  await page.getByLabel("Upload back", { exact: true }).setInputFiles(back);
  await page
    .getByRole("button", { name: "Add to review queue", exact: true })
    .click();
}
async function identify(page: Page) {
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await page
    .getByRole("button", { name: /New card.*Front and back captured/ })
    .first()
    .click();
  await page.getByLabel("Search card name", { exact: true }).fill("Charizard");
  await page
    .getByRole("button", { name: "Search catalog", exact: true })
    .click();
  await page
    .getByRole("button", { name: /Charizard.*Base Set.*4\/102/ })
    .first()
    .click();
  await expect(page.getByLabel("Card name", { exact: true })).toHaveValue(
    "Charizard",
  );
  await expect(
    page.getByRole("button", { name: "Confirm identity", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Confirm identity", exact: true })
    .click();
}
test("mobile manual capture → exact pricing → durable inventory → CSV → edit → confirmed delete", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Your collection, in order." }),
  ).toBeVisible();
  await capture(page);
  await identify(page);
  await page
    .getByRole("button", { name: "LP Lightly Played", exact: false })
    .click();
  await page
    .getByRole("button", { name: "Confirm condition & get price", exact: true })
    .click();
  await expect(page.locator(".price-value")).toHaveText("$527.70");
  await page.getByLabel("Listing price", { exact: true }).fill("500.00");
  await page
    .getByRole("button", { name: "Preview listing", exact: true })
    .click();
  await expect(page.getByLabel("Final listing price")).toHaveValue("500.00");
  await page
    .getByLabel("Listing notes")
    .fill("Synthetic E2E listing, not a real card.");
  await page
    .getByRole("button", { name: "Approve & save to inventory", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Saved to inventory");
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Charizard.*4\/102.*LP/ }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Charizard.*4\/102.*LP/ }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  expect((await download).suggestedFilename()).toBe(
    "TallyBinder-inventory.csv",
  );
  await page
    .getByRole("button", { name: /LP Charizard.*4\/102/ })
    .first()
    .click();
  await page.getByLabel("Final listing price").fill("480.00");
  await page
    .getByRole("button", { name: "Approve & save to inventory", exact: true })
    .click();
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await expect(page.locator(".inventory-open strong")).toContainText("$480.00");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: /Delete Charizard/ }).click();
  await expect(
    page.getByRole("heading", { name: "Start your first page." }),
  ).toBeVisible();
});
test("batch capture stays available, photos survive reload and identity changes clear prices", async ({
  page,
}) => {
  await page.goto("/");
  await capture(page);
  await capture(page);
  await page.reload();
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(page.locator(".queue-row")).toHaveCount(2);
  await identify(page);
  await page
    .getByRole("button", { name: "LP Lightly Played", exact: false })
    .click();
  await page
    .getByRole("button", { name: "Confirm condition & get price", exact: true })
    .click();
  await expect(page.locator(".price-value")).toHaveText("$527.70");
  await page.getByRole("button", { name: "2 Condition", exact: true }).click();
  await page
    .getByRole("button", { name: "MP Moderately Played", exact: false })
    .click();
  await page.getByRole("button", { name: "3 Price", exact: true }).click();
  await expect(page.locator(".price-value")).toHaveText("Price unavailable");
  await page
    .getByRole("button", { name: "Refresh exact price", exact: true })
    .click();
  await expect(page.locator(".price-value")).toHaveText("$364.73");
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Open camera", exact: true }),
  ).toBeVisible();
});
test("PWA metadata, mobile layout, camera-denial fallback and API failure", async ({
  page,
}) => {
  await page.goto("/");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const manifest = await page.request.get("/manifest.webmanifest");
  expect((await manifest.json()).name).toBe("TallyBinder");
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
    "href",
    "/icons/apple-touch-icon.png",
  );
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await page.getByRole("button", { name: "Open camera", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Upload front", { exact: true })).toBeAttached();
  await page.route("**/api/backend/inventory?*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "database_unavailable" } }),
    }),
  );
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("database unavailable");
});

test("cloud sign-in exchanges the access key without storing it in localStorage", async ({
  page,
}) => {
  let signed = false;
  let submitted = "";
  await page.route("**/api/backend/app/config", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ai_enabled: false,
        model: null,
        access_token_required: true,
        auth_mode: "session",
        authenticated: signed,
        max_reservation_usd: null,
      }),
    }),
  );
  await page.route("**/api/backend/auth/login", async (route) => {
    submitted = route.request().postDataJSON().access_key;
    signed = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: '{"authenticated":true}',
    });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Sign in securely", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("App access token")
    .fill("synthetic-cloud-access-key-for-browser-test");
  await page
    .getByRole("button", { name: "Sign in securely", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your collection, in order." }),
  ).toBeVisible();
  expect(submitted).toBe("synthetic-cloud-access-key-for-browser-test");
  expect(
    await page.evaluate(() => localStorage.getItem("tallybinder.accessToken")),
  ).toBeNull();
});
