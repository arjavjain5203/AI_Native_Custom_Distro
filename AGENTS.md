# Repository Guidelines

## Project Structure & Module Organization

This repository currently has two main areas:

- `archlive/`: Arch `archiso` profile for the custom installer image. Key files include [`archlive/profiledef.sh`](/home/arjavjain5203/Coding/AI_Native_Custom_Distro/archlive/profiledef.sh), [`archlive/packages.x86_64`](/home/arjavjain5203/Coding/AI_Native_Custom_Distro/archlive/packages.x86_64), bootloader configs under `grub/`, `syslinux/`, `efiboot/`, and root filesystem overlays under `airootfs/`.
- `docs/`: implementation and architecture documentation for the AI-native developer environment.

Treat `archlive/work/` as generated build output. Do not hand-edit files there unless you are debugging a local image build.

## Build, Test, and Development Commands

- `sudo mkarchiso -v -w archlive/work -o out archlive`: build the Arch ISO from the local profile.
- `find docs -maxdepth 1 -type f | sort`: verify the documentation set.
- `git status --short`: review pending changes before committing.

There is no application runtime or automated test suite checked in yet; most current work is documentation and `archiso` packaging.

## Coding Style & Naming Conventions

Use concise Markdown with clear headings and implementation-focused language. For future Python code, prefer 4-space indentation, `snake_case` for modules/functions, and explicit service/tool names such as `model_router.py` or `github_plugin.py`. Keep shell-oriented filenames lowercase and descriptive.

When editing the Arch profile:

- keep package lists one entry per line
- keep config comments minimal and practical
- prefer reproducible configuration over local machine assumptions

## Testing Guidelines

No test framework is defined yet. Until code lands, validate changes by:

- rebuilding the ISO when `archlive/` changes
- checking docs for broken structure or missing files
- smoke-testing any future daemon/API changes locally before opening a PR

When tests are added, place them under a top-level `tests/` directory and name files `test_*.py`.

## Commit & Pull Request Guidelines

Follow short, imperative commit subjects. The existing history uses the pattern `Add initial README for AI_Native_Custom_Distro`; keep that style, for example `Add archiso package updates`.

Pull requests should include:

- a brief summary of what changed
- affected paths such as `archlive/` or `docs/`
- validation steps you ran
- screenshots only if UI work is introduced later

## Security & Configuration Tips

Do not commit secrets, tokens, or machine-specific credentials. Keep generated artifacts out of source changes unless they are intentionally versioned configuration files.
