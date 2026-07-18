/**
 * Markdown -> token tree.
 *
 * Pure: takes a string, returns plain objects, touches no DOM. That is what lets
 * it be tested under `node --test` with no browser and no jsdom, and it keeps the
 * parsing separate from the DOM building in render.js.
 *
 * This is a deliberate subset — the constructs that actually show up in an
 * assistant's replies. It is not a CommonMark implementation.
 *
 * Security: this produces *data*, never HTML. render.js turns the tree into DOM
 * nodes with textContent, so markup in LLM output is displayed, never executed.
 * The one place a string reaches an attribute is a link href, which is why
 * sanitizeUrl exists here rather than in the renderer.
 */

/** URL schemes allowed in links. Everything else becomes inert text. */
const SAFE_URL_SCHEMES = ["http:", "https:", "mailto:"];

/**
 * Return the url if it is safe to put in an href, otherwise null.
 *
 * Blocks javascript:, data: and vbscript: URLs, including the obfuscated forms
 * (leading/trailing whitespace, embedded control characters, mixed case) that
 * naive prefix checks miss.
 */
export function sanitizeUrl(url) {
  if (typeof url !== "string") return null;
  // Strip characters browsers ignore when parsing a scheme; "java\nscript:" is
  // a live URL to a browser but not to a naive startsWith check.
  const cleaned = url.replace(/[\u0000-\u0020\u007F]/g, "").trim();
  if (cleaned === "") return null;
  // Relative URLs (no scheme) are same-origin and safe.
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(cleaned) === false) return url.trim();
  try {
    const scheme = cleaned.slice(0, cleaned.indexOf(":") + 1).toLowerCase();
    return SAFE_URL_SCHEMES.includes(scheme) ? url.trim() : null;
  } catch {
    return null;
  }
}

/**
 * Parse inline markup within a single line of text.
 * Returns an array of {type, ...} nodes: text, code, strong, em, link.
 */
export function parseInline(text) {
  const nodes = [];
  let remaining = text;

  // Ordered by precedence: code spans win, so `**not bold**` inside backticks
  // stays literal.
  const patterns = [
    { type: "code", re: /^`([^`]+)`/ },
    { type: "strong", re: /^\*\*([^*]+)\*\*/ },
    { type: "em", re: /^\*([^*]+)\*/ },
    { type: "link", re: /^\[([^\]]*)\]\(([^)\s]+)\)/ },
  ];

  let buffer = "";
  const flush = () => {
    if (buffer !== "") {
      nodes.push({ type: "text", value: buffer });
      buffer = "";
    }
  };

  while (remaining.length > 0) {
    let matched = false;
    for (const { type, re } of patterns) {
      const m = remaining.match(re);
      if (!m) continue;

      if (type === "link") {
        const href = sanitizeUrl(m[2]);
        if (href === null) {
          // Unsafe scheme: keep the whole thing as literal text so the user can
          // see what was there, but it is not clickable.
          buffer += m[0];
        } else {
          flush();
          nodes.push({ type: "link", value: m[1] || href, href });
        }
      } else {
        flush();
        nodes.push({ type, value: m[1] });
      }
      remaining = remaining.slice(m[0].length);
      matched = true;
      break;
    }

    if (!matched) {
      buffer += remaining[0];
      remaining = remaining.slice(1);
    }
  }

  flush();
  return nodes;
}

/**
 * Parse a markdown document into a flat list of block tokens.
 *
 * Blocks: heading{level,inline}, code{lang,value}, list{ordered,items[]},
 * paragraph{inline}.
 */
export function parseMarkdown(markdown) {
  if (typeof markdown !== "string" || markdown === "") return [];

  const lines = markdown.split("\n");
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block. Consumes to the closing fence, or to end of input if
    // the fence never closes — which happens constantly mid-stream, and must not
    // drop the partial code the user is watching arrive.
    const fence = line.match(/^```(\w*)\s*$/);
    if (fence) {
      const lang = fence[1] || "";
      const body = [];
      i += 1;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // step past the closing fence (or past the end)
      blocks.push({ type: "code", lang, value: body.join("\n") });
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[1].length,
        inline: parseInline(heading[2]),
      });
      i += 1;
      continue;
    }

    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const ordered = Boolean(numbered);
      const items = [];
      while (i < lines.length) {
        const m = ordered
          ? lines[i].match(/^\s*\d+[.)]\s+(.*)$/)
          : lines[i].match(/^\s*[-*+]\s+(.*)$/);
        if (!m) break;
        items.push(parseInline(m[1]));
        i += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (line.trim() === "") {
      i += 1;
      continue;
    }

    // Paragraph: consume until a blank line or the start of another block.
    const paragraph = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^```/.test(lines[i]) &&
      !/^#{1,6}\s/.test(lines[i]) &&
      !/^\s*[-*+]\s/.test(lines[i]) &&
      !/^\s*\d+[.)]\s/.test(lines[i])
    ) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push({ type: "paragraph", inline: parseInline(paragraph.join(" ")) });
  }

  return blocks;
}
