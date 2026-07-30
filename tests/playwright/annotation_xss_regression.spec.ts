import { test, expect } from '@playwright/test';

/**
 * Regression test for stored DOM-XSS in the annotation managers.
 *
 * Bug: src/web/static/js/annotation-manager.js (alternativeHighlight ~L319,
 * renderExistingAnnotation ~L358) and annotation-manager-mobile.js (~L598,
 * ~L636) assembled `container.innerHTML = beforeText + highlight.outerHTML +
 * afterText` where beforeText/afterText are UNESCAPED substrings of the
 * article's raw scraped text. An article containing literal markup like
 * `<img src=x onerror=alert(1)>` would execute when an annotation was
 * created or when existing annotations rendered on page load.
 *
 * Fix: class-scoped `escapeHtml` static method (matching the pattern in
 * similarity-display.js) applied to beforeText/afterText before innerHTML
 * concatenation, in both desktop and mobile managers.
 *
 * This test loads the JS files directly via addScriptTag on about:blank so
 * it does not depend on a live article — only on the global-setup health
 * check (same as every other Playwright spec in this suite).
 */
test.describe('Annotation manager XSS regression', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('about:blank');
    await page.addScriptTag({
      path: 'src/web/static/js/annotation-manager.js',
    });
    await page.addScriptTag({
      path: 'src/web/static/js/annotation-manager-mobile.js',
    });
  });

  test('[ANN-XSS-001] TextAnnotationManager.escapeHtml escapes angle brackets and quotes', async ({ page }) => {
    const result = await page.evaluate(() => {
      const escaped = TextAnnotationManager.escapeHtml('<img src=x onerror=alert(1)>');
      const sink = document.createElement('div');
      sink.innerHTML = escaped;
      return {
        escaped,
        imgCount: sink.querySelectorAll('img').length,
        hasOnError: Array.from(sink.querySelectorAll('*')).some(el => el.hasAttribute('onerror')),
      };
    });
    expect(result.escaped).toBe('&lt;img src=x onerror=alert(1)&gt;');
    expect(result.imgCount).toBe(0);
    expect(result.hasOnError).toBe(false);
  });

  test('[ANN-XSS-002] MobileTextAnnotationManager.escapeHtml escapes angle brackets and quotes', async ({ page }) => {
    const result = await page.evaluate(() => {
      const escaped = MobileTextAnnotationManager.escapeHtml('<img src=x onerror=alert(1)>');
      const sink = document.createElement('div');
      sink.innerHTML = escaped;
      return {
        escaped,
        imgCount: sink.querySelectorAll('img').length,
        hasOnError: Array.from(sink.querySelectorAll('*')).some(el => el.hasAttribute('onerror')),
      };
    });
    expect(result.escaped).toBe('&lt;img src=x onerror=alert(1)&gt;');
    expect(result.imgCount).toBe(0);
    expect(result.hasOnError).toBe(false);
  });

  test('[ANN-XSS-003] desktop renderExistingAnnotation does not create live img nodes from XSS in surrounding text', async ({ page }) => {
    const result = await page.evaluate(() => {
      const xssPayload = '<img src=x onerror="window.__xss_desktop_render=true">';
      const fullText = xssPayload + ' safe selected text here';
      const startPos = xssPayload.length + 1;
      const endPos = startPos + 4;

      const container = document.createElement('div');
      // Set the container's textContent to the full text (including the
      // XSS payload as literal text, not parsed as HTML). This mirrors how
      // the article-content div is populated on article pages — the raw
      // scraped text is inserted as textContent, which the annotation
      // manager then reads back via this.container.textContent.
      container.textContent = fullText;
      document.body.appendChild(container);

      const manager = new TextAnnotationManager(container, 99999);
      manager.renderExistingAnnotation({
        id: 'test-ann',
        annotation_type: 'huntable',
        start_position: startPos,
        end_position: endPos,
      });

      const imgs = container.querySelectorAll('img').length;
      const hasOnError = Array.from(container.querySelectorAll('*')).some(el => el.hasAttribute('onerror'));
      const spanCount = container.querySelectorAll('span.annotation-highlight').length;
      const textContent = container.textContent;

      container.remove();
      return {
        imgs,
        hasOnError,
        spanCount,
        textContent,
        xssFired: (window as any).__xss_desktop_render === true,
      };
    });
    // No live <img onerror> node should exist in the rendered container.
    expect(result.imgs).toBe(0);
    expect(result.hasOnError).toBe(false);
    // The highlight span (the legitimate feature) must still render.
    expect(result.spanCount).toBe(1);
    // The XSS payload must be visible as inert text, not executed.
    expect(result.textContent).toContain('<img src=x onerror=');
    expect(result.xssFired).toBe(false);
  });

  test('[ANN-XSS-004] desktop alternativeHighlight does not create live img nodes from XSS in surrounding text', async ({ page }) => {
    const result = await page.evaluate(() => {
      const xssPayload = '<img src=x onerror="window.__xss_desktop_alt=true">';
      const fullText = xssPayload + ' safe selected text here';
      const startPos = xssPayload.length + 1;
      const endPos = startPos + 4;

      const container = document.createElement('div');
      container.textContent = fullText;
      document.body.appendChild(container);

      const manager = new TextAnnotationManager(container, 99999);
      const highlight = document.createElement('span');
      highlight.className = 'annotation-highlight annotation-huntable';
      manager.alternativeHighlight(
        {
          id: 'test-ann',
          annotation_type: 'huntable',
          start_position: startPos,
          end_position: endPos,
        },
        highlight,
      );

      const imgs = container.querySelectorAll('img').length;
      const hasOnError = Array.from(container.querySelectorAll('*')).some(el => el.hasAttribute('onerror'));
      const spanCount = container.querySelectorAll('span.annotation-highlight').length;
      const textContent = container.textContent;

      container.remove();
      return {
        imgs,
        hasOnError,
        spanCount,
        textContent,
        xssFired: (window as any).__xss_desktop_alt === true,
      };
    });
    expect(result.imgs).toBe(0);
    expect(result.hasOnError).toBe(false);
    expect(result.spanCount).toBe(1);
    expect(result.textContent).toContain('<img src=x onerror=');
    expect(result.xssFired).toBe(false);
  });

  test('[ANN-XSS-005] mobile renderExistingAnnotation does not create live img nodes from XSS in surrounding text', async ({ page }) => {
    const result = await page.evaluate(() => {
      const xssPayload = '<img src=x onerror="window.__xss_mobile_render=true">';
      const fullText = xssPayload + ' safe selected text here';
      const startPos = xssPayload.length + 1;
      const endPos = startPos + 4;

      const container = document.createElement('div');
      container.textContent = fullText;
      document.body.appendChild(container);

      const manager = new MobileTextAnnotationManager(container, 99999);
      manager.renderExistingAnnotation({
        id: 'test-ann',
        annotation_type: 'huntable',
        start_position: startPos,
        end_position: endPos,
      });

      const imgs = container.querySelectorAll('img').length;
      const hasOnError = Array.from(container.querySelectorAll('*')).some(el => el.hasAttribute('onerror'));
      const spanCount = container.querySelectorAll('span.annotation-highlight').length;
      const textContent = container.textContent;

      container.remove();
      return {
        imgs,
        hasOnError,
        spanCount,
        textContent,
        xssFired: (window as any).__xss_mobile_render === true,
      };
    });
    expect(result.imgs).toBe(0);
    expect(result.hasOnError).toBe(false);
    expect(result.spanCount).toBe(1);
    expect(result.textContent).toContain('<img src=x onerror=');
    expect(result.xssFired).toBe(false);
  });

  test('[ANN-XSS-006] mobile alternativeHighlight does not create live img nodes from XSS in surrounding text', async ({ page }) => {
    const result = await page.evaluate(() => {
      const xssPayload = '<img src=x onerror="window.__xss_mobile_alt=true">';
      const fullText = xssPayload + ' safe selected text here';
      const startPos = xssPayload.length + 1;
      const endPos = startPos + 4;

      const container = document.createElement('div');
      container.textContent = fullText;
      document.body.appendChild(container);

      const manager = new MobileTextAnnotationManager(container, 99999);
      const highlight = document.createElement('span');
      highlight.className = 'annotation-highlight annotation-huntable';
      manager.alternativeHighlight(
        {
          id: 'test-ann',
          annotation_type: 'huntable',
          start_position: startPos,
          end_position: endPos,
        },
        highlight,
      );

      const imgs = container.querySelectorAll('img').length;
      const hasOnError = Array.from(container.querySelectorAll('*')).some(el => el.hasAttribute('onerror'));
      const spanCount = container.querySelectorAll('span.annotation-highlight').length;
      const textContent = container.textContent;

      container.remove();
      return {
        imgs,
        hasOnError,
        spanCount,
        textContent,
        xssFired: (window as any).__xss_mobile_alt === true,
      };
    });
    expect(result.imgs).toBe(0);
    expect(result.hasOnError).toBe(false);
    expect(result.spanCount).toBe(1);
    expect(result.textContent).toContain('<img src=x onerror=');
    expect(result.xssFired).toBe(false);
  });
});
