# Hefex Labs Skills

Agent skills for ordering PCB assembly from [Hefex Labs](https://hefex-labs.com) out of
coding agents such as Claude Code, Codex and Cursor.

Skills describe workflows (how to prepare and hand over a board). The Hefex MCP server
provides the tools (projects, quotes, parts, orders). Both work independently.

## Install

```bash
npx skills add Hefex-Labs/skills -a claude-code
npx skills add Hefex-Labs/skills -a codex
```

## Skills

| Skill | Purpose |
|---|---|
| [`odbpp-export`](odbpp-export/SKILL.md) | Export a KiCad or Altium Designer board as ODB++ for a Hefex quote, including do-not-populate parts and assembly variants |

## Layout

One folder per skill, each with a `SKILL.md` (frontmatter `name` and `description`, then
the instructions).
