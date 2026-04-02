<!-- File: .github/prompts/prompts-format.md -->
# Prompts Format

## Prompt File Format

Prompt files are Markdown files with the .prompt.md extension. The optional YAML frontmatter header configures the prompt's behavior:

| Field | Required | Description |
| ----- | -------- | ----------- |
| description | No | A short description of the prompt. |
| name | No | The name of the prompt, used after typing / in chat. If not specified, the file name is used. |
| argument-hint | No | Hint text shown in the chat input field to guide users on how to interact with the prompt. |
| agent | No | The agent used for running the prompt: ask, agent, plan, or the name of a custom agent. By default, the current agent is used. If tools are specified, the default agent is agent. |
| model | No | The language model used when running the prompt. If not specified, the currently selected model in model picker is used. |
| tools | No | A list of tool or tool set names that are available for this prompt. Can include built-in tools, tool sets, MCP tools, or tools contributed by extensions. To include all tools of an MCP server, use the \<server name\>/* format. Learn more about tools in chat. |

## Prompt File Example

Example: perform a security review of a REST API

```markdown
<!-- File: .github/prompts/sec-review-ask-agent.prompt.md -->
---
agent: 'ask'
model: Claude Sonnet 4
tools: ['search/codebase', 'vscode/askQuestions']
description: 'Perform a REST API security review'
---
Perform a REST API security review and provide a TODO list of security issues to address.

* Ensure all endpoints are protected by authentication and authorization
* Validate all user inputs and sanitize data
* Implement rate limiting and throttling
* Implement logging and monitoring for security events

Return the TODO list in a Markdown format, grouped by priority and issue type.

```
