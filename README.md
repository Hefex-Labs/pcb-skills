# PCB Skills

![An assembled blue PCB with surface-mount components and the Hefex Labs wordmark](assets/pcb-skills.jpg)

PCB Skills is a collection of tools from [Hefex Labs](https://hefex-labs.com) for working on circuit boards with a coding assistant. Start with [ODB++ export](odbpp-export/SKILL.md) to turn a saved KiCad or Altium Designer board into a manufacturing archive. It contains the board outline, copper layers and assembly data and can go to any manufacturer that accepts ODB++.

## Install with your assistant

Open the board's project folder in Codex or Claude Code and paste this prompt:

> Install the `odbpp-export` skill from https://github.com/Hefex-Labs/skills for the assistant I'm using, in this project only. Tell me where you installed it and how I can try it. Just install the skill for now.

The assistant needs access to this GitHub repository. Exporting a board locally does not require a Hefex account.

<details>
<summary>Install from a terminal</summary>

With Node.js 22.20 or later installed, run the command for your assistant from the project folder.

**Codex**

```sh
npx skills add Hefex-Labs/skills --skill odbpp-export -a codex
```

**Claude Code**

```sh
npx skills add Hefex-Labs/skills --skill odbpp-export -a claude-code
```

See the [skills installer documentation](https://github.com/vercel-labs/skills#install-a-skill) for other supported agents.

</details>

## Try it on a board

> Prepare an ODB++ archive from this project. Ask me which assembly variant to use if there are several, tell me which parts will be left off, and show me where you saved the file.

| Your board | What you need | What the assistant checks |
| --- | --- | --- |
| KiCad | A saved `.kicad_pcb` and a version of `kicad-cli` with ODB++ export | Runs the board's design rules, flags missing part numbers and checks which components the archive marks “do not populate.” |
| Altium Designer | Windows, a saved `.PrjPcb` and an open Altium session. The bundled scripts were tested with Altium Designer 26 Standard. | Lists assembly variants, runs an output job and checks the archive for copper layers. The assistant asks before adding an output job to your project. |

The assistant should finish a local export by giving you the archive path, the selected variant and anything you need to review before sending the board out.

## Get a quote from Hefex

When you're ready for a price, upload the archive in the [Hefex portal](https://prototyping.hefex-labs.com), or [connect your assistant to Hefex](https://prototyping.hefex-labs.com/agents) and ask it to quote the board. The connection gives the assistant tools to upload the archive and check pricing and part availability in your account. You confirm the board and parts and accept any binding offer in the portal.
