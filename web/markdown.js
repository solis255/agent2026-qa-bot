"use strict";

// The only assistant HTML entry point: Markdown -> DOMPurify fragment -> DOM.
// Raw HTML in model output is untrusted, just like retrieved document contents.
function renderAssistantMarkdown(container, markdownText) {
  const text = String(markdownText ?? "");
  container.classList.remove("is-streaming");
  if (!window.marked?.parse || !window.DOMPurify?.isSupported) {
    // Missing/unsupported dependencies must fail closed, never bypass sanitization.
    container.textContent = text;
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
  container.replaceChildren(fragment);
}
