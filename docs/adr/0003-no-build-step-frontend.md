# ADR-0003: the web UI has no build step and vendors nothing

Date: 2026-07-18 · Status: accepted

## Context

The repository had no frontend and no JavaScript surface at all. The plan
called for `marked` → DOMPurify → `innerHTML`.

## Decision

Vanilla ES modules served by `StaticFiles`, and **no `innerHTML` anywhere**:
`markdown.js` parses to a plain token tree, `render.js` builds DOM nodes with
`textContent`.

## Consequences

XSS becomes structurally impossible rather than filtered — there is no sanitiser
to bypass because nothing is ever parsed as markup — and three vendored
libraries disappear along with the need to pin and audit them. Adding npm to
this repo would have meant wiring it into `ci-cd.yml`, dependency-review, Trivy
and the SBOM for a UI that is ~800 lines of JavaScript.

The cost is a markdown subset rather than full CommonMark, which is the right
trade for chat replies. Frontend tests run on node's built-in test runner, so
there is still no `node_modules` and no lockfile to audit; `package.json`
declares `type: module` and nothing else.

If this grows into a multi-view product surface, the agreed escape hatch is
Preact + htm over ESM — still no bundler, real components.
