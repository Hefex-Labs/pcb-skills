# Maintaining PCB Skills

This repo owns the skills people install. Edit the local KiCad and Altium export instructions and the Altium kit in `odbpp-export/`. The export ends with a verified archive, its path and SHA-256, the board and revision, the assembly variant and any not-fitted designators. Project creation, upload, pricing and offers belong to the MCP in `Hefex-Labs/prototyping-service`.

## When a skill changes

- **Changes inside `odbpp-export/`** need two linked PRs. Commit the source here first. In a checkout of `prototyping-service`, run the import and parity check for that exact commit using the [manual sync procedure](https://github.com/Hefex-Labs/prototyping-service/blob/main/mcp/README.md#export-guide-and-prompt). Include the full source SHA and test result in the service PR. If you lack access to either repo, name the outstanding PR or check in the PR you can open.
- **Land the catalog PR first.** If GitHub squashes or rebases it, import and check the resulting commit on `main` before merging the service PR. Later catalog changes outside `odbpp-export/` do not need another import.
- **Changes confined to another skill** need only its catalog PR. If you add or rename a listed skill, change its advertised capabilities, or change the installation prompt, update the website's Skills tab in a linked service PR.

Use PRs for both repositories. When ownership, file locations or the update procedure change, update these instructions and the affected instructions in the other repo in the same set of PRs. Keep `CLAUDE.md` pointing to this file.
