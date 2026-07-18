/**
 * Token tree -> DOM.
 *
 * There is no innerHTML anywhere in this file, and no string is ever parsed as
 * HTML. Every piece of model output reaches the page as textContent on a node
 * this code created, so markup in an LLM reply is *displayed* rather than
 * executed. That is a structural guarantee rather than a filtering one: there is
 * no sanitiser to bypass because nothing is ever treated as markup.
 *
 * The single exception is a link href, and markdown.js has already restricted
 * those to http/https/mailto before a token gets here.
 */

import { parseMarkdown } from "./markdown.js";

/** Create an element with optional class and text. */
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Render inline token nodes into a parent element. */
function renderInline(parent, nodes) {
  for (const node of nodes) {
    switch (node.type) {
      case "code":
        parent.appendChild(el("code", "inline-code", node.value));
        break;
      case "strong":
        parent.appendChild(el("strong", null, node.value));
        break;
      case "em":
        parent.appendChild(el("em", null, node.value));
        break;
      case "link": {
        const a = el("a", null, node.value);
        a.href = node.href;
        a.target = "_blank";
        // noopener: without it the opened page can reach back through
        // window.opener and navigate this one.
        a.rel = "noopener noreferrer";
        parent.appendChild(a);
        break;
      }
      default:
        parent.appendChild(document.createTextNode(node.value));
    }
  }
}

/** Build a code block with a language label and a copy button. */
function renderCodeBlock(block) {
  const wrapper = el("div", "code-block");

  const header = el("div", "code-header");
  header.appendChild(el("span", "code-lang", block.lang || "text"));

  const copy = el("button", "code-copy", "Copy");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(block.value);
      copy.textContent = "Copied";
    } catch {
      copy.textContent = "Copy failed";
    }
    setTimeout(() => {
      copy.textContent = "Copy";
    }, 1500);
  });
  header.appendChild(copy);

  wrapper.appendChild(header);
  const pre = el("pre");
  pre.appendChild(el("code", null, block.value));
  wrapper.appendChild(pre);
  return wrapper;
}

/**
 * Render markdown text into a container element, replacing its contents.
 * @param {HTMLElement} container
 * @param {string} markdown
 */
export function renderMarkdown(container, markdown) {
  container.replaceChildren();
  for (const block of parseMarkdown(markdown)) {
    switch (block.type) {
      case "heading": {
        const h = el(`h${Math.min(block.level + 2, 6)}`);
        renderInline(h, block.inline);
        container.appendChild(h);
        break;
      }
      case "code":
        container.appendChild(renderCodeBlock(block));
        break;
      case "list": {
        const list = el(block.ordered ? "ol" : "ul");
        for (const item of block.items) {
          const li = el("li");
          renderInline(li, item);
          list.appendChild(li);
        }
        container.appendChild(list);
        break;
      }
      default: {
        const p = el("p");
        renderInline(p, block.inline);
        container.appendChild(p);
      }
    }
  }
}

/**
 * Build a tool-call chip.
 *
 * Starts pending on tool_start and is resolved by resolveToolChip on tool_end.
 * This is what makes the agent legible: without it a tool call is invisible and
 * the UI just appears to hang.
 */
export function createToolChip(name, params) {
  const chip = el("details", "tool-chip pending");
  const summary = el("summary");
  summary.appendChild(el("span", "tool-icon", "\u{1F527}"));
  summary.appendChild(el("span", "tool-name", name));
  summary.appendChild(el("span", "tool-status", "running…"));
  chip.appendChild(summary);

  const body = el("div", "tool-body");
  body.appendChild(el("pre", "tool-params", JSON.stringify(params ?? {}, null, 2)));
  chip.appendChild(body);
  return chip;
}

/** Resolve a pending chip with its outcome. */
export function resolveToolChip(chip, { ok, durationMs, summary, error }) {
  chip.classList.remove("pending");
  chip.classList.add(ok ? "ok" : "failed");

  const status = chip.querySelector(".tool-status");
  if (status) {
    const duration = durationMs !== null && durationMs !== undefined ? ` · ${durationMs}ms` : "";
    status.textContent = (ok ? summary || "done" : error || "failed") + duration;
  }
}
