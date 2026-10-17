# Local Markdown dependencies

The Web UI uses Marked **18.1.1** (MIT) to parse Markdown and DOMPurify
**3.4.17** (Apache-2.0 OR MPL-2.0) to sanitize it. Browser bundles and upstream
license files are committed here; running NetPilot does not need npm or a CDN.

Sources: [Marked](https://github.com/markedjs/marked),
[DOMPurify](https://github.com/cure53/DOMPurify).

To reproduce the vendored files from the npm integrity-pinned lockfile:

```powershell
cd web
npm ci --ignore-scripts
npm run vendor
npm test
```

Node.js 22.13+ on the 22.x line, or 24+ supported by jsdom, is needed only
for development tests. The jsdom dev dependency is not loaded by the browser.
Review parser/sanitizer security updates together, regenerate the bundles and
rerun the XSS tests whenever updating versions.
