// Renders qxlint's share image at the two sizes needed: 1200x630 for the site, 1280x640 for GitHub's social preview.
// Run it again only when the icon or the wording changes: npm install --no-save --prefix website playwright@1,
// npx --prefix website playwright install chromium, then node website/tools/make_card.mjs from the repository root.
import { chromium } from "playwright";
import fs from "node:fs";
const icon = fs.readFileSync(new URL("../../readme-assets/png/qxlint-icon-256.png", import.meta.url)).toString("base64");
const card = (w, h) => `<!DOCTYPE html><html><head><style>
  body { margin: 0; width: ${w}px; height: ${h}px; display: grid; place-items: center; overflow: hidden;
    background: radial-gradient(ellipse 70% 60% at 50% 0%, rgba(139,127,210,.26), rgba(139,127,210,0)) #0c1016;
    font-family: "Inter", system-ui, sans-serif; color: #eef0f6; -webkit-font-smoothing: antialiased; }
  main { text-align: center; width: ${w - 120}px; }
  img { width: 104px; height: 104px; display: block; margin: 0 auto 22px; filter: drop-shadow(0 14px 24px rgba(0,0,0,.5)); }
  h1 { margin: 0; font-size: 58px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.05; }
  p { margin: 14px 0 0; font-size: 30px; font-weight: 600; background: linear-gradient(90deg,#8b7fd2,#a99fe4 45%,#d6d1f7);
    -webkit-background-clip: text; background-clip: text; color: transparent; }
  pre { margin: 34px auto 0; width: fit-content; max-width: 100%; padding: 18px 26px; border-radius: 14px; background: #0b0e1a;
    box-shadow: 0 0 0 1px rgba(255,255,255,.09), 0 24px 60px rgba(0,0,0,.55); text-align: left; color: #c8d3f5;
    font: 19px/1.7 "DejaVu Sans Mono", ui-monospace, monospace; }
  .p { color: #a99fe4 } .l { color: #8e97bc } .c { color: #ff9f45; font-weight: 700 }
</style></head><body><main>
  <img src="data:image/png;base64,${icon}" alt="">
  <h1>Static checks for Qiskit Primitives V2.</h1>
  <p>It reads your code. It never runs it.</p>
  <pre><span class="p">$</span> uvx qxlint .
<span class="l">app.py:44:1:</span> <span class="c">QXL103</span> circuit has no measurement instructions …
<span class="l">service.py:7:31:</span> <span class="c">QXL201</span> channel="ibm_quantum" was removed …</pre>
</main></body></html>`;
const browser = await chromium.launch();
for (const [w, h, out] of [[1200, 630, new URL("../static/images/social.png", import.meta.url)], [1280, 640, new URL("../_build/github-social-preview.png", import.meta.url)]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.setContent(card(w, h), { waitUntil: "networkidle" });
  await page.screenshot({ path: out.pathname });
  await page.close();
}
await browser.close();
console.log("cards made");
