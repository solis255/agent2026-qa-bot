"use strict";

// The only assistant HTML entry point: Markdown -> DOMPurify fragment -> DOM.
// Raw HTML in model output is untrusted, just like retrieved document contents.
function renderAssistantMarkdown(container, markdownText, sources = []) {
  const text = String(markdownText ?? "");
  container.classList.remove("is-streaming");
  if (!window.marked?.parse || !window.DOMPurify?.isSupported) {
    // Missing/unsupported dependencies must fail closed, never bypass sanitization.
    container.textContent = text.replace(/\[\[cite:[^\]\n]*(?:\]\]|$)/g, "");
    return;
  }
  const fragment = window.DOMPurify.sanitize(
    window.marked.parse(text, { gfm: true, breaks: false, async: false }),
    {
      RETURN_DOM_FRAGMENT: true,
      ALLOWED_TAGS: [
        "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr",
        "ul", "ol", "li", "strong", "em", "del", "blockquote", "pre", "code",
        "table", "thead", "tbody", "tr", "th", "td", "a",
      ],
      ALLOWED_ATTR: ["href", "title", "start"],
      ALLOW_DATA_ATTR: false,
      ALLOW_ARIA_ATTR: false,
    },
  );
  for (const link of fragment.querySelectorAll("a")) {
    const href = (link.getAttribute("href") || "").trim();
    try {
      // No relative, protocol-relative, mailto, data, or javascript destinations.
      if (!/^https?:\/\//i.test(href)) throw new Error("Unsupported link");
      const url = new URL(href);
      if (!["http:", "https:"].includes(url.protocol)) throw new Error("Unsupported link");
      link.setAttribute("href", url.href);
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    } catch (_error) {
      link.replaceWith(...link.childNodes);
    }
  }
  renderInlineCitations(fragment, sources);
  container.replaceChildren(fragment);
}

function safeCitationURL(value) {
  try {
    if (typeof value !== "string" || !/^https?:\/\//i.test(value.trim())) return null;
    const url = new URL(value.trim());
    return ["http:", "https:"].includes(url.protocol) ? url : null;
  } catch (_error) {
    return null;
  }
}

function renderInlineCitations(fragment, sources) {
  const byRef = new Map();
  const conflicts = new Set();
  for (const source of Array.isArray(sources) ? sources : []) {
    const ref = source?.source_ref;
    if (typeof ref !== "string" || !/^[a-zA-Z0-9_-]{1,64}$/.test(ref)) continue;
    if (byRef.has(ref) && byRef.get(ref).source !== source.source) conflicts.add(ref);
    else byRef.set(ref, source);
  }
  const numbers = new Map();
  const walker = document.createTreeWalker(fragment, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const marker = /\[\[cite:([^\]\n]*)(?:\]\]|$)/g;
    if (!node.textContent.includes("[[cite:")) continue;
    const replacement = document.createDocumentFragment();
    let offset = 0;
    for (const match of node.textContent.matchAll(marker)) {
      replacement.append(document.createTextNode(node.textContent.slice(offset, match.index)));
      offset = match.index + match[0].length;
      // Never nest links or turn a code example into an interactive citation.
      if (node.parentElement?.closest("a,pre,code")) continue;
      for (const ref of new Set(match[1].split(",").map((value) => value.trim()))) {
        const source = byRef.get(ref);
        if (!source || conflicts.has(ref)) continue;
        if (!numbers.has(ref)) numbers.set(ref, numbers.size + 1);
        const number = numbers.get(ref);
        const url = safeCitationURL(source.source);
        const citation = document.createElement(url ? "a" : "span");
        const type = { official: "Official", community: "Community", maintainer: "Maintainer" }[source.source_type] || "Unknown";
        const title = String(source.title || "未命名资料");
        citation.className = "inline-citation";
        citation.textContent = `[${number}]`;
        citation.title = `${type} · ${title}\n${url ? url.hostname : "来源链接不可用"}`;
        citation.setAttribute("aria-label", `来源 ${number}：${type}，${title}`);
        if (url) {
          citation.href = url.href;
          citation.target = "_blank";
          citation.rel = "noopener noreferrer";
        } else {
          citation.tabIndex = 0;
        }
        replacement.append(citation);
      }
    }
    replacement.append(document.createTextNode(node.textContent.slice(offset)));
    node.replaceWith(replacement);
  }
}
