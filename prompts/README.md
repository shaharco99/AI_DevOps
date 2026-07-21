# Prompts folder (explained simply) 📝

A **prompt** is the set of instructions we hand the AI before it answers — like the
note you'd give a new babysitter: "here's what to do, here's how to behave." This
folder keeps all those notes in one place so we can find, reuse, and improve them.

## What's in here

We sort prompts into drawers by their job:

| Drawer | What lives there |
| --- | --- |
| `system/` | The main "how to behave" note for the assistant |
| `rag/` | Notes for looking things up in the bookshelf (RAG) and summarizing |
| `agents/` | Notes that help the agent pick and use its tools |
| `tools/` | Notes for individual tools |

## How to name a prompt

Give it a clear, lowercase-with-dashes name that says what it does, and add a
version number when it's a versioned one:

- Good: `devops-analyzer.md`, `root-cause-analysis.md`
- Versioned: `kubernetes-analyzer-v1.md`

## What each prompt file should say

Start every prompt file with a tiny "label" so anyone (human or robot) knows what
it is at a glance:

1. **Purpose** — one line: what is this note for?
2. **Version** — which version, and the date
3. **Last Updated** — when it last changed
4. **Usage** — when and how to use it
5. **Content** — the actual instructions

### A quick example

```markdown
# Prompt Title

**Purpose**: Brief description
**Version**: 1.0
**Last Updated**: 2024-01-15
**Status**: Active/Draft

## Usage

When and how to use this prompt...

## Prompt Content

[Your prompt text here]
```

## Good habits 🌟

1. **Don't repeat yourself** — build on a base prompt instead of copy-pasting.
2. **Be clear up front** — say exactly how the AI should act in the first lines.
3. **Show examples** — a sample question and a sample good answer teach a lot.
4. **Improve in small steps** — bump the version each time you refine it.
5. **Test before you ship** — try it on a few real questions first.
6. **Explain your changes** — leave a note about *why* you changed something.

## Version numbers (the MAJOR.MINOR.PATCH idea)

Think of it like editions of a book:

- **MAJOR** (1.0 → 2.0): the behavior really changed — a new edition.
- **MINOR** (1.0 → 1.1): added something new, but old uses still work.
- **PATCH** (1.0.0 → 1.0.1): small fix or wording tweak.
