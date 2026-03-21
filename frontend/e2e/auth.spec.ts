/**
 * E2E tests for authentication flows.
 *
 * Tests login, signup, password reset pages render and submit correctly.
 */

import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test("login page renders with form fields", async ({ page }) => {
    await page.goto("/login");

    await expect(page.getByRole("heading", { name: "Sign In" })).toBeVisible();
    await expect(page.getByLabel("Email Address")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("login page has link to signup", async ({ page }) => {
    await page.goto("/login");

    const signupLink = page.getByRole("link", { name: /sign up/i });
    await expect(signupLink).toBeVisible();
    await expect(signupLink).toHaveAttribute("href", "/signup");
  });

  test("login page has link to forgot password", async ({ page }) => {
    await page.goto("/login");

    const forgotLink = page.getByRole("link", { name: /forgot password/i });
    await expect(forgotLink).toBeVisible();
    await expect(forgotLink).toHaveAttribute("href", "/forgot-password");
  });

  test("login submits and shows feedback", async ({ page }) => {
    await page.goto("/login");

    await page.getByLabel("Email Address").fill("bad@example.com");
    await page.getByLabel("Password").fill("wrongpassword");
    await page.getByRole("button", { name: /sign in/i }).click();

    // Button should show loading state or error should appear
    await expect(
      page.getByText(/signing in|invalid|error|unexpected/i).first()
    ).toBeVisible({ timeout: 15000 });
  });

  test("signup page renders with form fields", async ({ page }) => {
    await page.goto("/signup");

    await expect(page.getByRole("heading", { name: /create account/i })).toBeVisible();
    await expect(page.getByLabel(/name/i).first()).toBeVisible();
    await expect(page.getByLabel(/email/i).first()).toBeVisible();
  });

  test("forgot password page renders", async ({ page }) => {
    await page.goto("/forgot-password");

    await expect(page.getByText("Reset Password")).toBeVisible();
    await expect(page.getByLabel("Email Address")).toBeVisible();
    await expect(page.getByRole("button", { name: /send reset link/i })).toBeVisible();
  });

  test("forgot password shows success after submit", async ({ page }) => {
    await page.goto("/forgot-password");

    await page.getByLabel("Email Address").fill("test@example.com");
    await page.getByRole("button", { name: /send reset link/i }).click();

    // Always shows success (anti-enumeration)
    await expect(page.getByText("Check Your Email")).toBeVisible({ timeout: 10000 });
  });

  test("reset password page shows invalid link without token", async ({ page }) => {
    await page.goto("/reset-password");

    await expect(page.getByText("Invalid Link")).toBeVisible();
  });

  test("reset password page shows form with token", async ({ page }) => {
    await page.goto("/reset-password?token=test_token_123");

    await expect(page.getByText("Set New Password")).toBeVisible();
    await expect(page.getByLabel("New Password")).toBeVisible();
    await expect(page.getByLabel("Confirm Password")).toBeVisible();
  });

  test("verify email page shows verifying state", async ({ page }) => {
    await page.goto("/verify-email?token=test_token");

    // Should show verifying or error (backend not running)
    await expect(
      page.getByText(/verifying|verification failed/i)
    ).toBeVisible({ timeout: 10000 });
  });

  test("unauthenticated user redirected from dashboard", async ({ page }) => {
    await page.goto("/dashboard");

    // Middleware should redirect to login
    await page.waitForURL(/login/, { timeout: 10000 });
    await expect(page).toHaveURL(/login/);
  });
});
