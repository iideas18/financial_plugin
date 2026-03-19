# Wiki Generator Optimizations

## 2026-03-18

- Standardized deep-dive extraction hubs on parent L2 pages:
  - use `<h2 id="deep-dives">`
  - add a `.hub-note` summary paragraph
  - keep one shared `.card-grid.deep-dive-grid` block for extracted topics
- Hardened focus-page promotion:
  - `link-focus-page.py` now escapes inserted text safely
  - helper can create the entire deep-dives section when the parent lacks one
  - helper injects the additional hub CSS tokens when needed
- Raised focus-page structure quality:
  - overview plus summary grid
  - decision-point table
  - mechanism walkthrough
  - behavior diagram
  - annotated code walkthrough
  - edge-case table, configuration, related topics
- Locked in generation hygiene:
  - generated HTML should stay pretty-printed, not minified
  - parent pages should not mix extracted-card hubs with leftover long-form deep-dive prose for the same topics