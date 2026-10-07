"""Writes qxlint's 404 page: qxlint run on the missing address, with what it really prints for a path that is not there."""
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
out = WEB / "_site/404.html"
# The terminal on the page shows what qxlint really prints for a path that is not there, and the code it exits with.
missing = (WEB / "_build/missing.txt").read_text()
assert "qxlint: path does not exist: " in missing and missing.rstrip().endswith("exit 2"), missing
page = """<!DOCTYPE html>
<html lang="en-US">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Page not found: qxlint</title>
  <meta name="description" content="This page isn’t part of qxlint’s site. Every rule is on the home page.">
  <meta name="robots" content="noindex">
  <meta name="theme-color" content="#0c1016">
  <meta name="color-scheme" content="dark">
  <link rel="icon" href="/favicon.ico" sizes="48x48">
  <link rel="icon" href="/favicon-96x96.png" type="image/png" sizes="96x96">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <style>
    :root {
      color-scheme: dark;
    }

    body {
      display: grid;
      place-items: center;
      min-height: 100vh;
      min-height: 100dvh;
      box-sizing: border-box;
      margin: 0;
      padding: 32px 16px;
      background: radial-gradient(ellipse 70% 55% at 50% 0%, rgba(139, 127, 210, 0.18), rgba(139, 127, 210, 0)) #0c1016;
      color: #eef0f6;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      text-align: center;
      -webkit-font-smoothing: antialiased;
    }

    main {
      width: min(620px, 100%);
    }

    img {
      display: block;
      width: 88px;
      height: 88px;
      margin: 0 auto 24px;
      filter: drop-shadow(0 16px 26px rgba(0, 0, 0, 0.5));
    }

    .terminal {
      overflow: hidden;
      border-radius: 14px;
      background: #0b0e1a;
      box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.09), 0 30px 70px rgba(0, 0, 0, 0.55);
      text-align: left;
    }

    .bar {
      display: flex;
      gap: 8px;
      align-items: center;
      height: 34px;
      padding: 0 14px;
      background: #151a2a;
    }

    .bar i {
      width: 11px;
      height: 11px;
      border-radius: 50%;
      background: #ff5f57;
    }

    .bar i:nth-child(2) {
      background: #febc2e;
    }

    .bar i:nth-child(3) {
      background: #28c840;
    }

    pre {
      margin: 0;
      padding: 18px 20px 20px;
      color: #c8d3f5;
      font-family: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 14px;
      line-height: 1.75;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    pre > span {
      display: block;
    }

    .prompt {
      color: #a99fe4;
    }

    .exit {
      color: #ff9f45;
      font-weight: 600;
    }

    .cursor {
      display: inline-block;
      width: 0.6em;
      height: 1.15em;
      margin-left: 0.15em;
      vertical-align: -0.2em;
      background: #a99fe4;
    }

    h1 {
      margin: 34px 0 0;
      font-size: clamp(30px, 6vw, 44px);
      font-weight: 700;
      letter-spacing: -0.015em;
    }

    p {
      margin: 14px 0 30px;
      color: #a7acbc;
      font-size: 19px;
      line-height: 1.45;
    }

    a {
      display: inline-block;
      padding: 13px 26px;
      border-radius: 999px;
      background: #a99fe4;
      color: #0c1016;
      font-size: 17px;
      font-weight: 600;
      text-decoration: none;
      transition: background-color 0.2s;
    }

    a:hover {
      background: #c9c2f2;
    }

    a:focus-visible {
      outline: 3px solid #a99fe4;
      outline-offset: 3px;
    }

    /* The lines come one after another, as a terminal prints them, then the cursor waits. */
    @media (prefers-reduced-motion: no-preference) {
      pre > span {
        animation: print 0.01s both;
      }

      pre > span:nth-child(1) { animation-delay: 0.25s; }
      pre > span:nth-child(2) { animation-delay: 0.75s; }
      pre > span:nth-child(3) { animation-delay: 1.35s; }
      pre > span:nth-child(4) { animation-delay: 1.65s; }
      pre > span:nth-child(5) { animation-delay: 2s; }

      .cursor {
        animation: blink 1.1s 2s steps(1) infinite;
      }

      @keyframes print {
        from {
          visibility: hidden;
        }
      }

      @keyframes blink {
        50% {
          opacity: 0;
        }
      }
    }

    @media (max-height: 640px) {
      img {
        width: 64px;
        height: 64px;
        margin-bottom: 16px;
      }

      h1 {
        margin-top: 22px;
      }

      p {
        margin: 10px 0 20px;
      }
    }

    /* A phone held sideways: the terminal and the way home matter more than the icon. */
    @media (max-height: 460px) {
      body {
        padding: 16px;
      }

      img {
        display: none;
      }

      pre {
        padding: 12px 18px 14px;
        line-height: 1.6;
      }

      h1 {
        margin-top: 16px;
        font-size: 28px;
      }

      p {
        margin: 8px 0 16px;
        font-size: 16px;
      }

      a {
        padding: 10px 22px;
      }
    }

    @media (max-width: 640px) {
      pre {
        font-size: 13px;
      }

      p {
        font-size: 17px;
      }
    }
  </style>
</head>
<body>
  <main>
    <img src="/images/qxlint-icon-168.webp" width="88" height="88" alt="" fetchpriority="high">
    <div class="terminal" role="img" aria-label="qxlint run on this address says the path does not exist, and exits with code 2">
      <div class="bar" aria-hidden="true"><i></i><i></i><i></i></div>
      <pre aria-hidden="true"><span><span class="prompt">$</span> qxlint <span data-path="command">this-page</span></span><span>qxlint: path does not exist: <span data-path>this-page</span></span><span><span class="prompt">$</span> echo $?</span><span class="exit">2</span><span><span class="prompt">$</span><i class="cursor"></i></span></pre>
    </div>
    <h1>Nothing to lint here.</h1>
    <p>This page isn’t part of qxlint’s site. Every rule is on the home page.</p>
    <a href="/">Go to qxlint’s home page</a>
  </main>
  <script>
    // The address asked for, as qxlint would print it; quoted on the command line only when a shell would need it.
    let path = location.pathname.replace(/^\\/+|\\/+$/g, "");
    try { path = decodeURIComponent(path); } catch {}
    if (path) {
      const quoted = /^[\\w@%+=:,./-]+$/.test(path) ? path : `'${path.replaceAll("'", "'\\\\''")}'`;
      document.querySelectorAll("[data-path]").forEach((node) => {
        node.textContent = node.dataset.path === "command" ? quoted : path;
      });
    }
  </script>
</body>
</html>
"""
out.write_text(page)
print("bytes", len(page.encode()))
