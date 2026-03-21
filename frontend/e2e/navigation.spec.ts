/**
 * E2E tests for navigation and page structure.
 *
 * Tests that all pages are accessible and render correctly.
 * Note: Dashboard pages require authentication via NextAuth middleware.
 */

import { test, expect } from "@playwright/test";

test.describe("Public Pages", () => {
  test("landing page renders", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/complira/i)).toBeVisible();
  });

  test("login page is accessible", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveURL(/login/);
    await expect(page.getByRole("heading", { name: "Sign In" })).toBeVisible();
  });

  test("signup page is accessible", async ({ page }) => {
    await page.goto("/signup");
    await expect(page).toHaveURL(/signup/);
    await expect(page.getByRole("heading", { name: /create account/i })).toBeVisible();
  });

  test("forgot password page is accessible", async ({ page }) => {
    await page.goto("/forgot-password");
    await expect(page.getByText("Reset Password")).toBeVisible();
  });
});

test.describe("Protected Routes (redirect to login)", () => {
  const protectedRoutes = [
    "/dashboard",
    "/dashboard/scans",
    "/dashboard/vex",
    "/dashboard/tokens",
    "/dashboard/projects",
    "/dashboard/repositories",
    "/dashboard/reference",
    "/dashboard/enrichment",
    "/dashboard/settings",
    "/dashboard/profile",
  ];

  for (const route of protectedRoutes) {
    test(`${route} redirects to login`, async ({ page }) => {
      await page.goto(route);
      await page.waitForURL(/login/, { timeout: 10000 });
      await expect(page).toHaveURL(/login/);
    });
  }
});
