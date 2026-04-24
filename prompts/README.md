# System Prompts Directory

This directory contains versioned system prompts for the AI DevOps Assistant.

## Structure

- `system/` - Core system prompts for the assistant
- `rag/` - RAG-specific prompts for retrieval and synthesis
- `agents/` - Agent-specific prompts for tool orchestration
- `tools/` - Tool-specific prompts for individual tools

## Naming Convention

- Use descriptive names: `devops_analyzer.md`, `root_cause_analysis.md`
- Include version suffix for versioned prompts: `kubernetes_analyzer_v1.md`
- Use kebab-case for file names

## Managing Prompts

Each prompt file should include:

1. **Purpose**: Clear description of the prompt's intent
2. **Version**: Version number and date
3. **Last Updated**: When the prompt was last modified
4. **Usage**: Instructions on how to use the prompt
5. **Content**: The actual prompt text

### Example Format

```markdown
# Prompt Title

**Purpose**: Brief description
**Version**: 1.0
**Last Updated**: 2024-01-15
**Status**: Active/Draft

## Usage

Instructions on how and when to use this prompt...

## Prompt Content

[Your prompt text here]
```

## Best Practices

1. **Keep it DRY**: Reuse and inherit from base prompts
2. **Clear Intent**: Start with explicit system instructions
3. **Examples**: Include examples of input/output
4. **Iterative**: Version prompts as you refine them
5. **Test**: Validate against test cases before deploying
6. **Document**: Always explain the rationale behind changes

## Versioning

Use semantic versioning: MAJOR.MINOR.PATCH

- MAJOR: Breaking changes to behavior
- MINOR: New capabilities or enhancements
- PATCH: Bug fixes or minor refinements
