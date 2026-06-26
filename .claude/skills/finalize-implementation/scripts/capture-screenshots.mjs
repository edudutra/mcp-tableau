#!/usr/bin/env node
/**
 * Captures PR screenshots with Playwright.
 *
 * Usage:
 *   node capture-screenshots.mjs --slug feat-name --routes /,/other
 *   node capture-screenshots.mjs --slug feat-name --url http://localhost:5173 --mobile
 *
 * Output: .github/pr-screenshots/<slug>/*.png + JSON manifest on stdout
 */

import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const DEFAULT_URL = 'http://localhost:5173';
const DEFAULT_ROUTES = ['/'];
const OUTPUT_ROOT = '.github/pr-screenshots';

function parseArgs(argv) {
  const options = {
    url: DEFAULT_URL,
    slug: `capture-${Date.now()}`,
    routes: DEFAULT_ROUTES,
    mobile: false,
    waitMs: 1500,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--url') options.url = argv[++i];
    else if (arg === '--slug') options.slug = argv[++i];
    else if (arg === '--routes') options.routes = argv[++i].split(',').filter(Boolean);
    else if (arg === '--mobile') options.mobile = true;
    else if (arg === '--wait-ms') options.waitMs = Number(argv[++i]);
    else if (arg === '--help') {
      console.log(`Usage: node capture-screenshots.mjs [options]

Options:
  --slug <name>       Folder name under ${OUTPUT_ROOT}/ (required for PRs)
  --routes <paths>    Comma-separated routes (default: /)
  --url <base>        App base URL (default: ${DEFAULT_URL})
  --mobile            Also capture mobile viewport (390x844)
  --wait-ms <ms>      Extra wait after load (default: 1500)
`);
      process.exit(0);
    }
  }

  return options;
}

function routeToFilename(route, suffix) {
  const base = route === '/' ? 'home' : route.replace(/^\//, '').replace(/\//g, '-');
  return `${base}-${suffix}.png`;
}

async function waitForServer(baseUrl, attempts = 40) {
  const healthUrl = baseUrl.replace(/\/$/, '');

  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(healthUrl, { redirect: 'follow' });
      if (response.ok || response.status < 500) return;
    } catch {
      // retry
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error(`App not reachable at ${baseUrl}. Start frontend (and backend if needed) first.`);
}

async function captureViewport(page, baseUrl, routes, outDir, suffix, waitMs) {
  const shots = [];

  for (const route of routes) {
    const normalized = route.startsWith('/') ? route : `/${route}`;
    const filename = routeToFilename(normalized, suffix);
    const filepath = path.join(outDir, filename);

    await page.goto(`${baseUrl.replace(/\/$/, '')}${normalized}`, {
      waitUntil: 'networkidle',
    });
    await page.waitForTimeout(waitMs);
    await page.screenshot({ path: filepath, fullPage: true });

    shots.push({
      route: normalized,
      viewport: suffix,
      file: filepath,
      markdown: `![${normalized} — ${suffix}](${filepath.replace(/\\/g, '/')})`,
    });
  }

  return shots;
}

function buildMarkdownSection(slug, screenshots) {
  const desktop = screenshots.filter((s) => s.viewport === 'desktop');
  const mobile = screenshots.filter((s) => s.viewport === 'mobile');

  const lines = [
    `Capturas geradas com Playwright (\`${slug}\`).`,
    '',
  ];

  if (desktop.length > 0) {
    lines.push('### Desktop (1280×720)', '');
    desktop.forEach((s) => lines.push(s.markdown, ''));
  }

  if (mobile.length > 0) {
    lines.push('### Mobile (390×844)', '');
    mobile.forEach((s) => lines.push(s.markdown, ''));
  }

  return lines.join('\n').trim();
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const outDir = path.join(OUTPUT_ROOT, options.slug);
  const baseUrl = options.url.replace(/\/$/, '');

  await waitForServer(baseUrl);
  await mkdir(outDir, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
  });
  const page = await context.newPage();

  const screenshots = await captureViewport(
    page,
    baseUrl,
    options.routes,
    outDir,
    'desktop',
    options.waitMs,
  );

  if (options.mobile) {
    await page.setViewportSize({ width: 390, height: 844 });
    const mobileShots = await captureViewport(
      page,
      baseUrl,
      options.routes,
      outDir,
      'mobile',
      options.waitMs,
    );
    screenshots.push(...mobileShots);
  }

  await browser.close();

  const manifest = {
    slug: options.slug,
    outDir,
    screenshots,
    markdownSection: buildMarkdownSection(options.slug, screenshots),
  };

  await writeFile(
    path.join(outDir, 'manifest.json'),
    `${JSON.stringify(manifest, null, 2)}\n`,
  );

  console.log(JSON.stringify(manifest, null, 2));
}

main().catch((error) => {
  console.error(error.message ?? error);
  process.exit(1);
});
