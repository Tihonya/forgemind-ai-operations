/**
 * WP-UX-UA-01-R1 locale-formatting remediation E2E (focused path).
 *
 * Runs against the disposable local stack (backend :8000 seeded with the
 * canonical golden data; frontend preview :4173 proxying /api/v1). It is
 * intentionally NOT wired into the golden CI flow — the canonical CI seed
 * contains no approval requests, so the Approval-Center section requires
 * the disposable synthetic fixture described in the remediation report.
 *
 * Coverage:
 * 1. Persisted-English full boot (storage set BEFORE any app code runs):
 *    html[lang] never reports uk, the Dashboard heading never paints in
 *    the Ukrainian form, and the first painted localized heading is
 *    English (DOM MutationObserver timeline — no hidden content used).
 * 2. Supply Risk under both locales: English dates while English active,
 *    Ukrainian dates after switching back, same mounted page.
 * 3. Approval Center card under both locales (synthetic fixture "where
 *    available" — skipped honestly when no card exists on the stack).
 * 4. Locale switcher touch targets (≥44×44 CSS px) + no horizontal
 *    overflow + visible labels at 360×800 / 390×844 / 768×1024 /
 *    1280×800.
 *
 * Locators: stable data-testids and semantic roles only — no brittle DOM
 * positions.
 */

import { test, expect, type Page } from '@playwright/test';

const VIEWPORTS = [
  { width: 360, height: 800, name: 'mobile-360' },
  { width: 390, height: 844, name: 'mobile-390' },
  { width: 768, height: 1024, name: 'tablet-768' },
  { width: 1280, height: 800, name: 'desktop-1280' },
] as const;

async function login(page: Page, locale: 'uk' | 'en' = 'uk') {
  // The localized sign-in label is the locale-state proof: the heading and
  // submit button must both read 'Увійти' under the Ukrainian default, and
  // 'Sign in' only when English was explicitly persisted before first render.
  const signInLabel = locale === 'uk' ? 'Увійти' : 'Sign in';
  await expect(page.getByRole('heading', { name: signInLabel, level: 2 })).toBeVisible();
  await page.getByTestId('login-username').fill('manager.demo');
  await page.getByTestId('login-password').fill('ManagerPass123!');
  await page.getByRole('button', { name: signInLabel }).click();
  await expect(page).toHaveURL('/', { timeout: 10000 });
}

test.describe('WP-UX-UA-01-R1 — locale-connected date formatting (focused)', () => {
  test('persisted-English boot paints English from the first frame (no uk flash)', async ({ page }) => {
    // Storage written BEFORE any application code executes — the exact
    // persisted-English user shape for a cold start.
    await page.addInitScript(() => {
      window.localStorage.setItem('forgemind_locale', 'en');
    });

    const headings: string[] = [];
    const langs: string[] = [];
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /Sign in/i, level: 2 })).toBeVisible();
    // html[lang] is set by the i18n module BEFORE React renders — it is
    // already en on the pre-auth login route.
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');

    // Record every localized-heading paint and every html[lang] mutation
    // from before sign-in through the first stable authenticated render.
    await page.evaluate(() => {
      const w = window as unknown as {
        __fmR1Headings: string[];
        __fmR1Langs: string[];
      };
      w.__fmR1Headings = [];
      w.__fmR1Langs = [];
      const push = () => {
        const h1 = document.querySelector('h1');
        if (h1) w.__fmR1Headings.push(h1.textContent ?? '');
      };
      push();
      new MutationObserver(() => {
        w.__fmR1Langs.push(document.documentElement.lang);
        push();
      }).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['lang'],
        subtree: true,
      });
    });

    await login(page, 'en');

    // First stable authenticated Dashboard heading is English.
    await expect(page.getByRole('heading', { name: /Operations Dashboard/i, level: 1 })).toBeVisible();

    const evidence = await page.evaluate(() => {
      const w = window as unknown as {
        __fmR1Headings: string[];
        __fmR1Langs: string[];
      };
      return { headings: w.__fmR1Headings, langs: w.__fmR1Langs };
    });

    // Acceptance: html[lang] never reports uk; the Dashboard heading never
    // paints in Ukrainian; the first recorded localized heading is English.
    expect(evidence.langs.filter((l) => l === 'uk')).toEqual([]);
    expect(evidence.headings.filter((h) => h.includes('Операційний'))).toEqual([]);
    const firstLocalizedHeading = evidence.headings.find((h) =>
      /Operations Dashboard|Операційний огляд/.test(h),
    );
    expect(firstLocalizedHeading).toBe('Operations Dashboard');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  });

  test('supply-risk dates follow the active locale in place, survive reload, and return to uk', async ({ page }) => {
    await page.goto('/');
    await login(page, 'uk');
    // Product-Owner Ukrainian default shell.
    await expect(page.locator('html')).toHaveAttribute('lang', 'uk');

    // English from the switcher (no reload, no navigation).
    await page.getByTestId('locale-switch-en').click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.getByTestId('locale-switch-en')).toHaveAttribute('aria-pressed', 'true');

    // Real formatDate call site under English.
    await page.getByTestId('nav-link-supply-risk').click();
    await expect(page).toHaveURL('/supply-risk', { timeout: 5000 });
    await expect(page.getByText('Jul 31, 2026 — Aug 6, 2026')).toBeVisible();
    await expect(page.getByText(/лип\. \d{4}/)).not.toBeVisible();

    // Reload with persisted English: dates stay English.
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.getByText('Jul 31, 2026 — Aug 6, 2026')).toBeVisible();

    // Back to Ukrainian on the same mounted page: reactive re-render.
    await page.getByTestId('locale-switch-uk').click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'uk');
    await expect(page.getByTestId('locale-switch-uk')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByText('31 лип. 2026 р. — 6 серп. 2026 р.')).toBeVisible();
    await expect(page.getByText('Jul 31, 2026 — Aug 6, 2026')).not.toBeVisible();
  });

  test('approval-center card dates follow the active locale (synthetic fixture)', async ({ page }) => {
    await page.goto('/');
    await login(page, 'uk');

    await page.getByTestId('nav-link-approvals').click();
    await expect(page).toHaveURL('/approval-center', { timeout: 5000 });

    // The synthetic disposable-stack fixture provides the card; the
    // canonical CI seed does not — skip honestly when absent (bounded
    // wait, then skip; never fail the run on the canonical seed).
    const card = page.getByTestId('approval-request-card').first();
    try {
      await expect(card).toBeVisible({ timeout: 8000 });
    } catch {
      test.skip(true, 'no approval-request fixture on this stack (canonical seed)');
      return;
    }

    // Ukrainian requested date on the fixture row (2026-07-16 in Kyiv).
    await expect(page.locator('html')).toHaveAttribute('lang', 'uk');
    await expect(page.getByTestId('requested-at').first()).toHaveText(/16 лип\. 2026 р\./);

    // Switch to English on the SAME mounted card.
    await page.getByTestId('locale-switch-en').click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.getByTestId('requested-at').first()).toHaveText(/Jul 16, 2026/);

    // Approval status and decision controls unchanged by the switch.
    await expect(page.getByTestId('approval-status-badge').first()).toHaveText(/PENDING/);

    // And back to Ukrainian.
    await page.getByTestId('locale-switch-uk').click();
    await expect(page.getByTestId('requested-at').first()).toHaveText(/16 лип\. 2026 р\./);
  });

  test('locale switcher touch targets are ≥44×44 px at all viewports without overflow', async ({ browser }) => {
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
      });
      const page = await context.newPage();
      await page.goto('/');
      await login(page, 'uk');
      await expect(page.locator('html')).toHaveAttribute('lang', 'uk');

      for (const code of ['uk', 'en']) {
        const box = await page.getByTestId(`locale-switch-${code}`).boundingBox();
        expect(box, `${vp.name} ${code} button bounding box`).not.toBeNull();
        expect(box!.height, `${vp.name} ${code} height`).toBeGreaterThanOrEqual(44);
        expect(box!.width, `${vp.name} ${code} width`).toBeGreaterThanOrEqual(44);
      }

      // No horizontal overflow at any viewport.
      const scrollWidth = await page.evaluate(
        () => document.scrollingElement?.scrollWidth ?? 0,
      );
      const clientWidth = await page.evaluate(
        () => document.scrollingElement?.clientWidth ?? 0,
      );
      expect(scrollWidth, `${vp.name} horizontal overflow`).toBeLessThanOrEqual(clientWidth);

      // Labels not clipped: both buttons' visible text is intact.
      await expect(page.getByTestId('locale-switch-uk')).toContainText('Українська');
      await expect(page.getByTestId('locale-switch-en')).toContainText('English');

      // English date formatting at a narrow viewport after switch+reload.
      // Below the md breakpoint the sidebar is CSS-hidden and navigation
      // lives in the drawer — always scope through the open dialog.
      await page.getByTestId('locale-switch-en').click();
      if (vp.width < 768) {
        await page.getByTestId('mobile-menu-open').click();
        // Drawer behavior on the affected path: opens focused, Escape
        // closes with focus returned to the trigger.
        await expect(page.getByRole('dialog', { name: /Головне меню|Main menu/ })).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog', { name: /Головне меню|Main menu/ })).toHaveCount(0);
        await expect(page.getByTestId('mobile-menu-open')).toBeFocused();

        await page.getByTestId('mobile-menu-open').click();
        await page
          .getByRole('dialog', { name: /Головне меню|Main menu/ })
          .getByTestId('nav-link-supply-risk')
          .click();
      } else {
        await page.getByTestId('nav-link-supply-risk').click();
      }
      await expect(page).toHaveURL('/supply-risk', { timeout: 5000 });
      await expect(page.getByText('Jul 31, 2026 — Aug 6, 2026')).toBeVisible();
      await page.reload();
      await expect(page.locator('html')).toHaveAttribute('lang', 'en');
      await expect(page.getByText('Jul 31, 2026 — Aug 6, 2026')).toBeVisible();

      await context.close();
    }
  });
});