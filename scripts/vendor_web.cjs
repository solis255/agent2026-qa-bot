"use strict";

// Reproducible, mechanical copies from the versions pinned in web/package-lock.json.
const fs = require("node:fs");
const path = require("node:path");
const root = path.join(__dirname, "..", "web");
const files = {
  "marked/lib/marked.umd.js": "marked.umd.js",
  "marked/lib/marked.umd.js.map": "marked.umd.js.map",
  "marked/LICENSE": "marked.LICENSE",
  "dompurify/dist/purify.min.js": "purify.min.js",
  "dompurify/dist/purify.min.js.map": "purify.min.js.map",
  "dompurify/LICENSE": "DOMPurify.LICENSE",
  "dompurify/LICENSE-MPL": "DOMPurify.LICENSE-MPL",
};
fs.mkdirSync(path.join(root, "vendor"), { recursive: true });
for (const [source, destination] of Object.entries(files)) {
  fs.copyFileSync(path.join(root, "node_modules", source), path.join(root, "vendor", destination));
}
