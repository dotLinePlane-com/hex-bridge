---
name: push-hexbridge-github
description: Safely publish reviewed HEX-Bridge repository changes to GitHub when the workspace has no .git metadata or when the user requests a GitHub update.
---

# Publish HEX-Bridge changes

Use the project's `script/push-github.ps1` only when the user intends to sync the entire local project. It clones the default remote (`dotLinePlane-com/hex-bridge`), copies the working tree, commits, and pushes to `master`. Its dry-run does not clone and diff the complete proposed file set, so do not treat `-DryRun` as a content review.

For a focused change, use a temporary clone of the intended remote branch and copy only the reviewed files into it. Before pushing:

1. Confirm repository, branch, and intended file list from the user's request; inspect the remote branch state before staging.
2. Exclude generated `build*` outputs, machine-specific config, local credentials, and ignored/local-only tooling. The local `connect-hex-wifi` skill stores a Wi-Fi password in plaintext; never publish that credential or copy that skill to a public remote. A publishable testing skill should refer to the local Wi-Fi skill without duplicating secrets.
3. Review `git status`, staged `git diff --stat`, and the full staged diff. Scan staged content for credentials, tokens, private keys, and local paths. Do not publish until the actual content is clear of secrets.
4. Run `git diff --check`, commit with a descriptive message, push only the intended branch, and verify the remote commit hash. If the remote has diverged, stop and reconcile instead of force-pushing.

Do not create a release or tag unless the user requested one. Do not amend or overwrite unrelated remote history. When the user asks to publish a narrow set of changes, never mirror the entire workspace just for convenience.
