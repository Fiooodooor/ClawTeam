<!-- File: .github/agents/agents-format.md -->
# Custom Agents Format

## Custom Agent File Format

| Field | Description |
|-------|-------------|
| description | A brief description of the custom agent, shown as placeholder text in the chat input field. |
| name | The name of the custom agent. If not specified, the file name is used. |
| argument-hint | Optional hint text shown in the chat input field to guide users on how to interact with the custom agent. |
| tools | A list of tool or tool set names that are available for this custom agent. Can include built-in tools, tool sets, MCP tools, or tools contributed by extensions. To include all tools of an MCP server, use the <server name>/* format. Learn more about tools in chat. |
| agents | A list of agent names that are available as subagents in this agent. Use * to allow all agents, or an empty array [] to prevent any subagent use. If you specify agents, ensure the agent tool is included in the tools property. |
| model | The AI model to use when running the prompt. Specify a single model name (string) or a prioritized list of models (array). When you specify an array, the system tries each model in order until an available one is found. If not specified, the currently selected model in model picker is used. |
| user-invocable | Optional boolean flag to control whether the agent appears in the agents dropdown in chat (default is true). Set to false to create agents that are only accessible as subagents or programmatically. |
| disable-model-invocation | Optional boolean flag to prevent the agent from being invoked as a subagent by other agents (default is false). |
| infer | Deprecated. Use user-invocable and disable-model-invocation instead. Previously, infer: true (the default) made the agent both visible in the picker and available as a subagent. infer: false hid it from both. The new fields give you independent control: use user-invocable: false to hide from the picker while still allowing subagent invocation, or disable-model-invocation: true to prevent subagent invocation while keeping it in the picker. |
| target | The target environment or context for the custom agent (vscode or github-copilot). |
| mcp-servers | Optional list of Model Context Protocol (MCP) server config json to use with custom agents in GitHub Copilot (target: github-copilot). |
| handoffs | Optional list of suggested next actions or prompts to transition between custom agents. Handoff buttons appear as interactive suggestions after a chat response completes. |
| handoffs.label | The display text shown on the handoff button. |
| handoffs.agent | The target agent identifier to switch to. |
| handoffs.prompt | The prompt text to send to the target agent. |
| handoffs.send | Optional boolean flag to auto-submit the prompt (default is false) |
| handoffs.model | Optional language model to use when the handoff executes. Use the qualified model name in the format Model Name (vendor), for example GPT-5 (copilot) or Claude Sonnet 4.5 (copilot). |
| hooks (Preview) | Optional hook commands scoped to this agent. Hooks defined here only run when this agent is active, either invoked by the user or as a subagent. Uses the same format as hook configuration files. Requires chat.useCustomAgentHooks to be enabled. |

## Custom Agent Example

```markdown
<!-- .github/agents/implementation-planning-agent.agent.md -->
---
description: Generate an implementation plan for new features or refactoring existing code.
name: Planner
tools: ['fetch', 'githubRepo', 'search', 'usages']
model: ['Claude Opus 4.5', 'GPT-5.2']  # Tries models in order
handoffs:
  - label: Implement Plan
    agent: agent
    prompt: Implement the plan outlined above.
    send: false
---
# Planning instructions
You are in planning mode. Your task is to generate an implementation plan for a new feature or for refactoring existing code.
Don't make any code edits, just generate a plan.

The plan consists of a Markdown document that describes the implementation plan, including the following sections:

* Overview: A brief description of the feature or refactoring task.
* Requirements: A list of requirements for the feature or refactoring task.
* Implementation Steps: A detailed list of steps to implement the feature or refactoring task.
* Testing: A list of tests that need to be implemented to verify the feature or refactoring task.
```

