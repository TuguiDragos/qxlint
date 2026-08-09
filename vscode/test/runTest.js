// Downloads a VS Code build, loads this extension into it and runs
// test/suite/index.js inside the extension host.
//
// QXLINT_TEST_PATH must point at a qxlint executable. Everything the suite
// asserts depends on the analyser really running, so there is no mock.
//
// On Linux this needs a display: `xvfb-run -a npm run test:e2e`.

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runTests } = require("@vscode/test-electron");

async function main() {
  const extensionDevelopmentPath = path.resolve(__dirname, "..");
  const extensionTestsPath = path.resolve(__dirname, "suite", "index.js");

  const qxlint = process.env.QXLINT_TEST_PATH;
  if (!qxlint) {
    console.error("QXLINT_TEST_PATH is not set. Point it at a qxlint executable.");
    process.exit(1);
  }

  // A short path: VS Code opens a unix socket under the user data directory,
  // and the 103 character limit on those is easy to cross under a temp folder.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "qxe2e-"));
  const workspace = path.join(root, "ws");
  fs.mkdirSync(workspace);
  for (const name of fs.readdirSync(path.join(__dirname, "fixtures"))) {
    fs.copyFileSync(path.join(__dirname, "fixtures", name), path.join(workspace, name));
  }

  // Deliberately empty. The Python extension is not installed, so this run also
  // proves qxlint activates and works without it, which is what the code has
  // always been written for.
  const extensionsDir = path.join(root, "extensions");
  fs.mkdirSync(extensionsDir);

  await runTests({
    extensionDevelopmentPath,
    extensionTestsPath,
    launchArgs: [
      workspace,
      "--extensions-dir",
      extensionsDir,
      "--user-data-dir",
      path.join(root, "user-data"),
      "--disable-workspace-trust",
      "--skip-welcome",
      "--skip-release-notes",
      "--disable-gpu",
    ],
    extensionTestsEnv: {
      QXLINT_TEST_WORKSPACE: workspace,
      QXLINT_TEST_PATH: qxlint,
    },
  });

  if (!fs.existsSync(path.join(root, "e2e-passed"))) {
    console.error("the suite did not reach its end");
    process.exit(1);
  }
  fs.rmSync(root, { recursive: true, force: true });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
