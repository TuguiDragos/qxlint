// Colors code with Tapetum Quantum, read from the theme file itself, and writes HTML spans with short classes.
import fs from "node:fs";
import { codeToTokensBase } from "shiki";
const [themeFile, inFile, outFile] = process.argv.slice(2);
const theme = JSON.parse(fs.readFileSync(themeFile, "utf8"));
theme.name = "tapetum-quantum";
const items = JSON.parse(fs.readFileSync(inFile, "utf8"));
const escape = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
const base = theme.colors["editor.foreground"].toUpperCase();
// The theme's comment gray reads at 4.35:1 on its own background; on the web it is lifted to 4.94:1, same hue
// (style.css, .c).
const CLASS = { "#CD8FF9": "k", "#8AB4FF": "f", "#4DE0D0": "s", "#FF9F45": "n", "#8E97BC": "p", "#FF6E9C": "x", "#6E769E": "c" };
const out = {};
const used = new Set();
for (const { id, code, lang } of items) {
  const lines = await codeToTokensBase(code, { lang, theme });
  out[id] = lines.map((line) => {
    const runs = [];
    for (const t of line) {
      const color = t.color.toUpperCase();
      if (color !== base && !(color in CLASS)) throw new Error(`no class for ${color} in ${id}`);
      const names = [color === base ? "" : CLASS[color], t.fontStyle & 1 ? "i" : "", t.fontStyle & 2 ? "b" : ""].filter(Boolean).join(" ");
      const last = runs.at(-1);
      // Spaces carry no color, so they join whatever comes before them.
      if (last && (last.names === names || !t.content.trim())) last.text += t.content;
      else runs.push({ names: t.content.trim() ? names : "", text: t.content });
    }
    return runs.map(({ names, text }) => {
      names.split(" ").filter(Boolean).forEach((n) => used.add(n));
      return names ? `<span class="${names}">${escape(text)}</span>` : escape(text);
    }).join("");
  }).join("\n");
}
fs.writeFileSync(outFile, JSON.stringify(out));
console.log("highlighted", Object.keys(out).length, "classes", [...used].sort().join(" "), "bg", theme.colors["editor.background"], "fg", base);
