---
name: transfer-skill-to-windows
description: Adapt an existing agent skill so it works cleanly on Windows when the input is either a skill folder path or a zip file.
---

# Transfer Skill To Windows

Use this skill when the user wants to make an existing skill work on Windows, especially when the original skill assumes Unix shells, Unix paths, or Linux/macOS tooling.

This skill accepts either:

- A path to a skill folder
- A path to a zip file that contains a skill folder

The goal is to produce a Windows-compatible version of the skill with the smallest practical set of changes, while preserving the original workflow and intent.

## What This Skill Produces

This skill helps you:

- Inspect the incoming skill package or folder
- Identify Windows-incompatible assumptions
- Rewrite instructions, commands, and examples for Windows
- Preserve cross-platform behavior when practical
- Return an updated skill folder ready to use on Windows

## When To Use This Skill

Use this skill when the user asks for any of the following:

- Transfer a skill to Windows
- Make a skill support Windows
- Convert a skill that uses bash or Unix paths
- Patch a skill distributed as a folder or zip so it works on Windows

Do not use this skill for general application migration. This skill is specifically for agent skills and their supporting files.

## Inputs To Gather

Before making changes, confirm or infer the following:

1. The input type:
   - Skill folder path
   - Zip file path
2. The desired output behavior:
   - In-place update
   - Create a separate Windows-ready copy
3. Whether the user wants:
   - Windows-only support
   - Cross-platform support with Windows compatibility

If the user does not specify output behavior, default to creating a separate Windows-ready copy so the source remains untouched.

## Workflow

### 1. Load The Skill Contents

If the input is a folder:

- Inspect the directory structure
- Locate `SKILL.md` and any helper scripts, templates, or config files

If the input is a zip file:

- Extract it to a working directory
- Inspect the extracted contents
- Identify the actual skill root that contains `SKILL.md`

If the extracted archive does not contain a `SKILL.md`, stop and tell the user the package does not look like a valid skill.

### 2. Inventory Windows Risks

Inspect `SKILL.md` and any referenced files for these common issues:

- Commands written only for `bash`, `sh`, or `zsh`
- Use of `&&`, `export`, `chmod`, `rm`, `cp`, `mv`, `cat`, `grep`, `sed`, `awk`, `find`, `xargs`, `tar`, `unzip`, or `which`
- Unix-style absolute paths such as `/tmp/...` or `/usr/local/...`
- Path examples that assume `/` separators in shell commands
- Shebang-based scripts such as `#!/bin/bash`
- Scripts that depend on executable permission bits
- References to tools commonly missing on Windows
- Instructions that assume case-sensitive filesystems
- Symlink-heavy workflows without Windows fallback guidance

Also inspect supporting files such as:

- `.ps1`, `.bat`, `.cmd`, `.sh`
- `package.json`
- `pyproject.toml`
- `requirements.txt`
- README or usage examples
- Template files referenced by the skill

### 3. Decide The Conversion Strategy

Prefer this order of solutions:

1. Make instructions tool-based rather than shell-specific when possible
2. Replace Unix-only shell examples with PowerShell equivalents
3. Keep cross-platform examples if they are already valid on Windows
4. Add Windows notes only where a direct rewrite would reduce clarity

If a command can be expressed in a VS Code tool workflow, prefer that over raw shell instructions.

### 4. Rewrite For Windows

Apply the smallest change set that makes the skill usable on Windows.

Typical rewrites include:

- Replace bash command examples with PowerShell examples
- Replace `export NAME=value` with `$env:NAME = 'value'`
- Replace `rm -rf path` with `Remove-Item -Recurse -Force path`
- Replace `cp src dst` with `Copy-Item src dst`
- Replace `mv src dst` with `Move-Item src dst`
- Replace `cat file` with `Get-Content file`
- Replace `grep pattern file` with `Select-String -Path file -Pattern pattern`
- Replace `which tool` with `Get-Command tool`
- Replace `chmod +x script.sh` by removing the permission requirement or by providing a `.ps1` alternative
- Replace archive extraction examples with `Expand-Archive`
- Replace Unix temp-directory assumptions with Windows-safe paths or tool-managed temp locations

Also normalize instructional language:

- Use Windows path examples when showing local filesystem paths
- Avoid telling users to invoke `bash -lc` unless that is a hard requirement
- Prefer PowerShell 5.1 compatible commands unless the skill clearly requires PowerShell 7+

### 5. Update Supporting Files

If the skill includes helper scripts:

- Convert `.sh` scripts into `.ps1` equivalents when needed
- Update references inside `SKILL.md` to the new script names
- Preserve original scripts if the goal is cross-platform support

If the skill contains examples or templates with shell snippets:

- Rewrite those snippets for Windows
- Keep the original semantics intact

If the skill references zipped input or extracted folders:

- Ensure the instructions explicitly say how to handle both on Windows

### 6. Validate The Result

Before finishing, verify:

- `SKILL.md` still describes the original task accurately
- Every command shown is runnable on Windows or clearly marked otherwise
- Any referenced files actually exist after conversion
- Paths and examples are internally consistent
- The skill does not rely on Unix-only permission or shell behavior without explanation

### 7. Report The Outcome

Summarize:

- What Windows incompatibilities were found
- Which files were changed
- Whether the result is Windows-only or cross-platform
- Any remaining limitations, such as required third-party tools

## Decision Rules

- If the skill is documentation-only, focus on rewriting instructions and examples
- If the skill contains scripts, convert the scripts or provide Windows-native alternatives
- If the skill depends on a Unix-only tool with no practical Windows equivalent, call that out explicitly and propose the least disruptive fallback
- If the user provides a zip file, do not assume the archive root is the skill root; inspect it first
- If the user provides a folder path, do not duplicate large files unless the user asked for a separate output

## Completion Criteria

The task is complete when:

- A valid `SKILL.md` exists in the converted skill
- Windows users can follow the instructions without relying on bash-only behavior
- Any required helper files are updated or replaced
- The user receives a concise summary of the migration and any remaining caveats

## Example Prompts

- Convert this skill folder to work on Windows: `C:\skills\my-skill`
- Adapt this zipped skill for Windows support and keep it cross-platform: `C:\downloads\my-skill.zip`
- Audit this skill for Unix-only assumptions and produce a Windows-ready copy

## Notes For The Agent

- Prefer precise edits over broad rewrites
- Preserve the author's intent and workflow
- Do not remove useful cross-platform guidance unless it conflicts with Windows usability
- If the skill is ambiguous, ask one focused question after producing the first draft of the conversion plan