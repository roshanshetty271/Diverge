import { test, expect } from "@playwright/test";

const payload = {
  path_a: "Take the stable job",
  path_b: "Join the startup",
  template_id: null,
  user_name: "Alex",
  age: 29,
  financial_context: null,
  values: "Growth, Stability",
  constraints: "Need the UI to pace messages even when the backend is fast.",
  writing_samples: null,
};

const alphaText = [
  "Alpha paragraph one keeps building the case for the stable job and stays deliberately long so the typewriter reveal has time to breathe and feel like a real first bubble.",
  "Alpha paragraph two adds another layer instead of dumping all the text at once, which is the exact UX we want to preserve on the frontend.",
  "Alpha paragraph three ends with alpha-third-sentinel so the test can detect the moment Alpha fully finishes on screen.",
].join("\n\n");

const betaText = [
  "Beta begins with beta-first-sentinel and should not appear until Alpha has fully rendered and settled.",
  "Beta paragraph two keeps the response moving one bubble at a time instead of appearing as an instant dump.",
].join("\n\n");

const roundData = {
  round_number: 1,
  round_name: "The Ripple",
  round_title: "Year 1: The Ripple",
  alpha: alphaText,
  beta: betaText,
  metrics: null,
  status: "completed",
};

const sseBody = [
  { type: "debate_start", debate_id: "mock-debate", total_rounds: 1 },
  { type: "round_start", round: 1, round_name: roundData.round_name, round_title: roundData.round_title },
  { type: "token", agent: "alpha", round: 1, text: alphaText },
  { type: "agent_done", agent: "alpha", round: 1 },
  { type: "token", agent: "beta", round: 1, text: betaText },
  { type: "agent_done", agent: "beta", round: 1 },
  { type: "round_complete", round: 1, data: roundData },
  {
    type: "complete",
    verdict: "Mock verdict",
    timeline: null,
    debate_id: "mock-debate",
    metrics: [null],
    completed_rounds: 1,
    total_rounds: 1,
    resources: [],
  },
]
  .map((event) => `data: ${JSON.stringify(event)}`)
  .join("\n\n") + "\n\n";

test("frontend stages alpha then beta even when SSE arrives immediately", async ({ page }) => {
  await page.addInitScript((routePayload) => {
    if (location.pathname === "/loading") {
      history.replaceState(
        { usr: { input: routePayload, captchaToken: "mock-captcha" }, key: "mock-key", idx: 0 },
        "",
        "/loading",
      );
    }

    window.__uiCheckMarks = {};
    const recordMarks = () => {
      const text = document.body?.innerText || "";
      const marks = window.__uiCheckMarks;
      const now = performance.now();

      if (!marks.alphaEnd && text.includes("alpha-third-sentinel")) marks.alphaEnd = now;
      if (!marks.betaStart && text.includes("beta-first-sentinel")) marks.betaStart = now;
      if (!marks.verdictReady && text.includes("See the Verdict")) marks.verdictReady = now;

      requestAnimationFrame(recordMarks);
    };

    requestAnimationFrame(recordMarks);
  }, payload);

  await page.route("**/api/capabilities", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        active_provider: "mock",
        intended_provider: "mock",
        openai_fallback_active: false,
        bedrock_ready: true,
        tts: false,
        sentiment: false,
        email_checkins_ready: false,
        knowledge_base: false,
        agentcore_memory: false,
      }),
    });
  });

  await page.route("**/api/debate/stream-tokens", async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
        connection: "keep-alive",
      },
      body: sseBody,
    });
  });

  await page.goto("http://localhost:5173/loading");
  await page.waitForURL("**/debate", { timeout: 10000 });

  await expect(page.locator("body")).toContainText("Alpha is arguing", { timeout: 5000 });
  await expect(page.locator("body")).not.toContainText("beta-first-sentinel");

  await page.waitForTimeout(500);
  await expect(page.locator("body")).not.toContainText("beta-first-sentinel");

  await expect.poll(async () => page.evaluate(() => window.__uiCheckMarks), {
    timeout: 10000,
  }).toMatchObject({
    alphaEnd: expect.any(Number),
    betaStart: expect.any(Number),
    verdictReady: expect.any(Number),
  });

  const marks = await page.evaluate(() => window.__uiCheckMarks);
  expect(marks.alphaEnd).toBeLessThan(marks.betaStart);
  expect(marks.betaStart).toBeLessThan(marks.verdictReady);
});
