# skill_to_windows

This repository is a small VS Code skill workspace focused on two things:

- authoring and refining custom agent skills under `.github/skills/`
- validating that those skills work well in a Windows-first environment

At the moment the workspace contains a Windows-porting skill and a stock analysis skill.

## Included Skills

### transfer-skill-to-windows

Path: `.github/skills/transfer-skill-to-windows/SKILL.md`

Purpose:

- adapt an existing skill folder or zip file so it works on Windows
- detect Unix-only commands, shell assumptions, hardcoded paths, and packaging issues
- produce a separate `_windows_ready` output by default
- rebuild and verify the zip artifact when the input is a zip file

Typical use cases:

- convert a bash-oriented skill for PowerShell users
- fix a partially converted Windows copy
- validate that docs, scripts, and packaged output all match

Example prompts:

- `transfer this skill folder to Windows: C:\skills\my-skill`
- `adapt this zip for Windows support: C:\downloads\some-skill.zip`

### stock-kline-analysis

Path: `.github/skills/stock-kline-analysis/SKILL.md`

Purpose:

- resolve stock identifiers across A-share, HK, and US markets
- fetch daily, weekly, and monthly K-line data
- compute indicators such as MA, Bollinger Bands, MACD, RSI, and ATR
- generate charts and a structured analysis report
- support multi-symbol relative strength and portfolio-style comparison

Implementation scripts live in `.github/skills/stock-kline-analysis/scripts/`.

## Repository Layout

```text
.
├── .github/
│   └── skills/
│       ├── stock-kline-analysis/
│       │   ├── SKILL.md
│       │   └── scripts/
│       └── transfer-skill-to-windows/
│           └── SKILL.md
├── .vscode/
└── README.md
```

## How To Use

Open this workspace in VS Code with GitHub Copilot Chat enabled.

The skills are workspace-scoped, so prompts that match their intent can use the definitions in `.github/skills/` directly. In practice, that means you can ask for Windows conversion of another skill or ask for stock K-line analysis without having to restate the full workflow each time.

## Windows Notes

This workspace is intentionally biased toward Windows validation.

Design assumptions:

- prefer PowerShell-compatible commands for examples and helper scripts
- avoid machine-specific absolute paths in docs and code
- keep Unix shell files only when they are preserved for cross-platform compatibility
- when converting zipped skills, verify both the edited folder and the rebuilt zip

## Development Notes

If you add more skills to this repository:

1. place them under `.github/skills/<skill-name>/`
2. keep the skill root name aligned with the `name` field in `SKILL.md`
3. avoid hardcoded local paths in docs, tests, and scripts
4. if the skill ships as a zip conversion target, validate the packaged artifact as well as the extracted folder

## Status

This repository is currently a working skill sandbox rather than a packaged product. The main source of truth is the `SKILL.md` file inside each skill folder.