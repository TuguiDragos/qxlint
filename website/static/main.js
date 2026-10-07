const reveals = document.querySelectorAll(".reveal");
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add("shown");
        observer.unobserve(entry.target);
      }
    }
  }, { rootMargin: "0px 0px -8% 0px" });
  reveals.forEach((element) => observer.observe(element));
} else {
  reveals.forEach((element) => element.classList.add("shown"));
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.textContent = "Copied";
      button.classList.add("done");
    } catch {
      button.textContent = "Press ⌘C";
      const range = document.createRange();
      range.selectNodeContents(button.previousElementSibling);
      getSelection().removeAllRanges();
      getSelection().addRange(range);
    }
    setTimeout(() => {
      button.textContent = "Copy";
      button.classList.remove("done");
    }, 2000);
  });
});

const chips = document.querySelectorAll("[data-rule]");
const rules = document.querySelectorAll(".rule");

const show = (code) => {
  chips.forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.rule === code)));
  rules.forEach((rule) => rule.classList.toggle("active", rule.id === code));
};

chips.forEach((chip) => chip.addEventListener("click", () => {
  show(chip.dataset.rule);
  history.replaceState(null, "", `#${chip.dataset.rule}`);
}));

// A link to one rule, like #qxl201, opens on that rule; otherwise the page opens on the one marked in the HTML.
const asked = location.hash.slice(1);
const known = [...chips].some((chip) => chip.dataset.rule === asked);
show(known ? asked : document.querySelector('[data-rule][aria-pressed="true"]').dataset.rule);
if (known) document.getElementById(asked).scrollIntoView({ block: "start", behavior: "instant" });

// A code block that scrolls sideways takes keyboard focus, so it can be scrolled without a mouse; one that fits does not.
if ("ResizeObserver" in window) {
  const scrollers = new ResizeObserver((entries) => {
    for (const { target } of entries) {
      if (target.scrollWidth > target.clientWidth) target.tabIndex = 0;
      else target.removeAttribute("tabindex");
    }
  });
  document.querySelectorAll(".code pre:not(.output), .cards pre").forEach((pre) => scrollers.observe(pre));
}
