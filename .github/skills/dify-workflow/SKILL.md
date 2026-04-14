---
name: dify-workflow
description: >
  Create, edit, validate, debug, and optimize Dify Workflow DSL YAML files.
  Use when the user asks to: build a Dify workflow, create a Dify app, generate
  Dify DSL YAML, add nodes to a workflow, wire workflow edges, fix a broken Dify
  YAML, validate a workflow against the DSL spec, convert a process diagram into
  a Dify workflow, create a chatflow, set up an LLM pipeline, add branching logic,
  create iteration loops, connect code nodes, design multi-agent workflows, or
  mentions "Dify", "DSL", "workflow YAML", "chatflow", "workflow app". Also use
  when exporting or importing Dify apps via DSL YAML.
argument-hint: 'description of the workflow to create or path to a DSL YAML file to edit/validate'
version: 0.6.0
---

# Dify Workflow DSL — AI Skill

Create, edit, validate, and debug Dify Workflow DSL YAML files. This skill encodes the
complete Dify DSL v0.6.0 specification as actionable procedures, compliance rules, and
ready-to-use patterns.

## When to Use

- User asks to create a new Dify workflow or chatflow
- User wants to add/remove/modify nodes in an existing DSL YAML
- User needs to fix a broken or invalid DSL YAML file
- User wants to convert a process description into a Dify workflow
- User asks to validate a workflow against the DSL specification
- User exports from Dify and wants to understand/modify the YAML
- User designs multi-step LLM pipelines, branching logic, or iteration

## When NOT to Use

- Dify runtime debugging (Python API errors, Docker issues) — use standard debugging
- Dify plugin/extension development — use Dify plugin SDK docs
- Simple chat/completion apps that don't use the `workflow` key

---

## Quick Reference — DSL Version 0.6.0

### Top-Level Structure (Required)

```yaml
version: "0.6.0"          # MUST be "0.6.0"
kind: app                  # MUST be "app"
app:
  name: "Workflow Name"
  mode: workflow           # "workflow" | "advanced-chat"
  icon: "🤖"
  icon_type: emoji
  icon_background: "#FFEAD5"
  description: "What this app does"
  use_icon_as_answer_icon: false
dependencies: []
workflow:
  graph:
    nodes: [...]
    edges: [...]
    viewport: { x: 0, y: 0, zoom: 1 }
  features: { ... }
  environment_variables: []
  conversation_variables: []
```

### App Modes

| Mode | Requires `workflow` | Terminal Node | Memory Support |
|------|-------------------|---------------|----------------|
| `workflow` | Yes | `end` node | No |
| `advanced-chat` | Yes | `answer` node | Yes (`sys.query`, conversation vars) |

### All Node Types

| Type | Purpose | Key Outputs |
|------|---------|-------------|
| `start` | Entry point, defines user inputs | User-defined variables |
| `end` | Terminal (workflow mode) | Maps output variables |
| `answer` | Streaming response (advanced-chat) | Template string |
| `llm` | LLM call | `text`, `reasoning_content`, `usage` |
| `code` | Python3/JavaScript execution | User-defined outputs |
| `if-else` | Conditional branching | Routes via sourceHandle |
| `http-request` | HTTP API call | `status_code`, `body`, `headers`, `files` |
| `tool` | External tool/plugin | `text`, `files`, `json` |
| `template-transform` | Jinja2 rendering | `output` |
| `question-classifier` | LLM-based classification | Routes via class sourceHandle |
| `knowledge-retrieval` | RAG from datasets | `result` (array) |
| `variable-aggregator` | First-available selection | `output` |
| `assigner` | Write/update variables | (side effect) |
| `iteration` | Loop over array | `item`, `index`, `output` |
| `loop` | Repeat until condition | Loop variables |
| `parameter-extractor` | LLM structured extraction | Named params + `__is_success` |
| `document-extractor` | Extract text from files | `text` |
| `list-operator` | Filter/sort/limit arrays | Transformed array |
| `human-input` | Pause for human input | Form data |
| `agent` | Autonomous agent with tools | Agent output |

### Variable Reference Syntax

```yaml
# In value_selector fields (array path):
value_selector:
  - node_id
  - variable_name

# In template strings (answer, prompt_template.text, url):
"{{#node_id.variable_name#}}"

# System variables (use "sys" as node_id):
"{{#sys.query#}}"          # User's input
"{{#sys.files#}}"          # Uploaded files
"{{#sys.conversation_id#}}" # Conversation ID

# Conversation variables (advanced-chat only):
"{{#conversation.my_var#}}"
```

### Edge Wiring Rules

```yaml
edges:
  - id: "unique-edge-id"
    source: "source_node_id"
    target: "target_node_id"
    sourceHandle: source       # Default for most nodes
    targetHandle: target       # Always "target"
    type: custom               # Always "custom"
```

| Source Node Type | sourceHandle | When |
|-----------------|--------------|------|
| Most nodes | `source` | Default output |
| `if-else` | `"true"` or case_id | Matched condition |
| `if-else` | `"false"` | Else/default branch |
| `question-classifier` | `"class_1"`, etc. | Classification result |
| Error strategy nodes | `"success-branch"` | Success path |
| Error strategy nodes | `"fail-branch"` | Error path |

---

## Procedure — Create a New Workflow

### Step 1 — Determine Mode and Structure

Ask/infer:
- **Mode**: `workflow` (batch processing, API endpoint) or `advanced-chat` (conversational)?
- **Inputs**: What does the user provide? → defines `start` node variables
- **Outputs**: What should come back? → defines `end` node (workflow) or `answer` node (advanced-chat)
- **Steps**: What transformations/logic happen in between?

### Step 2 — Scaffold the Skeleton

Start with the mandatory structure:

```yaml
version: "0.6.0"
kind: app
app:
  name: "<descriptive name>"
  mode: workflow
  icon: "🤖"
  icon_type: emoji
  icon_background: "#FFEAD5"
  description: "<what the workflow does>"
  use_icon_as_answer_icon: false
dependencies: []
workflow:
  conversation_variables: []
  environment_variables: []
  features:
    file_upload:
      enabled: false
    opening_statement: ""
    retriever_resource:
      enabled: false
    sensitive_word_avoidance:
      enabled: false
    speech_to_text:
      enabled: false
    suggested_questions: []
    suggested_questions_after_answer:
      enabled: false
    text_to_speech:
      enabled: false
  graph:
    nodes: []
    edges: []
    viewport:
      x: 0
      y: 0
      zoom: 1
```

### Step 3 — Define Nodes

For each processing step, create a node object. Every node needs:

```yaml
- id: "unique_node_id"        # Lowercase, underscores, descriptive
  type: custom                 # Always "custom"
  data:
    type: <node_type>          # From the node types table above
    title: "Human-Readable Name"
    # ... type-specific fields
  position:
    x: <horizontal>            # Space nodes 300px apart horizontally
    y: <vertical>              # Center at ~282 vertically
```

**Layout convention**: Place nodes left-to-right, 300px apart horizontally, centered at y=282.

### Step 4 — Wire Edges

Connect every node. Rules:
- Every node except `start` must have at least one incoming edge
- Every node except `end`/`answer` must have at least one outgoing edge
- `if-else` needs one edge per case + one for `"false"` (else)
- `question-classifier` needs one edge per class
- Iterations: edges inside the container use `isInIteration: true`

### Step 5 — Validate

Run through the compliance checklist (see below) or use the validation script:

```bash
python3 .github/skills/dify-workflow/scripts/validate_dify_dsl.py <file.yaml>
```

---

## Procedure — Add a Node to an Existing Workflow

1. Read the existing YAML and identify the insertion point
2. Create the new node with a unique `id` not used by any existing node
3. Add edges: incoming from the predecessor, outgoing to the successor
4. If inserting mid-chain, update the predecessor's outgoing edge to point to the new node
5. Ensure variable references from downstream nodes still resolve
6. Validate

---

## Procedure — Debug a Broken Workflow

Common failure modes and fixes:

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Node not reachable" | Missing incoming edge | Add edge from predecessor |
| "Variable not found" | Wrong `value_selector` path | Check node_id and output name |
| "Invalid sourceHandle" | Wrong handle for branching node | Use `"true"`/`"false"` for if-else |
| Workflow won't import | YAML syntax error | Validate YAML parsing first |
| Node runs but empty output | Wrong variable type | Match `value_type` to actual output |
| Iteration produces nothing | Missing `output_selector` | Point it to the inner node's output |
| LLM node timeout | Large context / no timeout | Set `completion_params.max_tokens` |
| Chat has no memory | Memory not enabled | Set `memory.window.enabled: true` |

---

## Compliance Rules — Mandatory

These rules MUST be satisfied for any generated DSL YAML:

### C1. Structural Integrity

- [ ] `version` is `"0.6.0"` (string, quoted)
- [ ] `kind` is `app`
- [ ] `app.mode` is `workflow` or `advanced-chat`
- [ ] `workflow.graph.nodes` is a non-empty array
- [ ] `workflow.graph.edges` is an array
- [ ] `workflow.features` is present (even if all disabled)

### C2. Start Node

- [ ] Exactly ONE node with `data.type: start` exists
- [ ] Every user input variable has `variable`, `label`, `type`, and `required`
- [ ] Variable types are valid: `text-input`, `paragraph`, `number`, `select`, `file`, `file-list`, `checkbox`, `json_object`
- [ ] `select` type variables have non-empty `options` array

### C3. Terminal Node

- [ ] Workflow mode: at least one `end` node exists
- [ ] Advanced-chat mode: at least one `answer` node exists
- [ ] `end` node: every output has `variable`, `value_type`, and valid `value_selector`
- [ ] `answer` node: `answer` field uses valid `{{#node_id.variable#}}` references

### C4. Edge Completeness

- [ ] Every edge has: `id`, `source`, `target`, `sourceHandle`, `targetHandle`, `type`
- [ ] `targetHandle` is always `"target"`
- [ ] `type` is always `"custom"`
- [ ] Every non-start node is reachable (has at least one incoming edge)
- [ ] Every non-terminal node has at least one outgoing edge
- [ ] `if-else` nodes have edges for every case_id plus `"false"`
- [ ] `question-classifier` nodes have edges for every class_id

### C5. Variable References

- [ ] All `value_selector` arrays reference valid `[node_id, variable_name]` pairs
- [ ] Template strings `{{#node_id.variable#}}` reference existing nodes upstream
- [ ] No circular references
- [ ] System variables use `sys` prefix: `["sys", "query"]`, `["sys", "files"]`, etc.
- [ ] Conversation variables use `conversation` prefix (advanced-chat only)

### C6. LLM Nodes

- [ ] `model` has `provider`, `name`, `mode`
- [ ] `prompt_template` is an array of `{role, text}` objects for chat mode
- [ ] Roles are valid: `system`, `user`, `assistant`
- [ ] At least one `user` message exists
- [ ] Variable references in prompt text resolve to upstream node outputs

### C7. Code Nodes

- [ ] `code_language` is `python3` or `javascript`
- [ ] `code` field contains the actual code string
- [ ] `variables` maps function parameter names to valid `value_selector` paths
- [ ] `outputs` declares every key that the code returns with a valid type

### C8. Container Nodes (Iteration / Loop)

- [ ] Iteration has a child `iteration-start` node with `parentId` matching the container `id`
- [ ] Iteration `iterator_selector` points to an array variable
- [ ] Iteration `output_selector` points to a variable inside the loop body
- [ ] Loop has a child `loop-start` node with matching `parentId`
- [ ] Inner nodes have `isInIteration: true` (or `isInLoop: true`) in their data
- [ ] Inner edges have `isInIteration: true` (or `isInLoop: true`) in their data

### C9. No Hardcoded Secrets

- [ ] No API keys, tokens, or passwords in plain text
- [ ] Use `environment_variables` with `value_type: secret` for sensitive values
- [ ] Reference secrets via `["environment", "var_name"]` selectors

---

## Patterns — Common Workflow Architectures

### Pattern 1: Sequential LLM Pipeline

```
start → llm_1 → llm_2 → llm_3 → end
```

Use when: Multi-step processing (analyze → transform → format).

Each LLM node feeds its `text` output to the next via `{{#prev_node.text#}}`.

### Pattern 2: Conditional Routing

```
start → classifier → [class_1] → llm_technical → end
                   → [class_2] → llm_general → end
```

Use when: Different handling based on input type. `question-classifier` routes to specialized LLM nodes.

### Pattern 3: If-Else Branching with Aggregation

```
start → if_else → [true]  → llm_a ─┐
                → [false] → llm_b ─┤
                                    └→ aggregator → end
```

Use when: Conditional logic with a single output. `variable-aggregator` merges branches.

### Pattern 4: Parallel Fan-Out

```
start → code_split → iteration → [inner: llm_process] → end
```

Use when: Processing multiple items independently. `iteration` with `is_parallel: true`.

### Pattern 5: RAG Pipeline

```
start → knowledge_retrieval → llm (context injected) → end
```

Use when: Answering from a knowledge base. Enable `context.enabled: true` on the LLM node.

### Pattern 6: Self-Check Loop

```
start → llm_generate → code_validate → loop_check →
        [pass] → end
        [fail] → llm_fix → code_validate (cycle back)
```

Use when: Quality gates. Use `loop` node with break condition on validation score.

### Pattern 7: HTTP-Enriched Pipeline

```
start → http_fetch_data → code_parse → llm_analyze → end
```

Use when: External API data feeds the LLM. Parse HTTP `body` in a code node first.

### Pattern 8: Multi-Agent Expert Pipeline

```
start → planner_llm → iteration →
  [inner: expert_llm → validator_code → if_pass] →
  aggregator → supervisor_llm → end
```

Use when: Complex multi-step expert analysis with self-check per step.

---

## LLM Node — Complete Template

```yaml
- id: my_llm
  type: custom
  position: { x: 380, y: 282 }
  data:
    type: llm
    title: "My LLM Node"
    model:
      provider: openai           # or anthropic, etc.
      name: gpt-4
      mode: chat
      completion_params:
        temperature: 0.7
        max_tokens: 4096
    prompt_template:
      - role: system
        text: "You are a helpful assistant."
      - role: user
        text: "{{#start.query#}}"
    context:
      enabled: false
      variable_selector: []
    memory: null                 # Set for advanced-chat
    vision:
      enabled: false
```

## Code Node — Complete Template

```yaml
- id: my_code
  type: custom
  position: { x: 380, y: 282 }
  data:
    type: code
    title: "Process Data"
    code_language: python3
    code: |
      def main(input_text: str) -> dict:
          lines = input_text.strip().split("\n")
          return {
              "line_count": len(lines),
              "summary": lines[0] if lines else ""
          }
    variables:
      - variable: input_text
        value_selector:
          - start
          - query
    outputs:
      line_count:
        type: number
      summary:
        type: string
```

## If-Else Node — Complete Template

```yaml
- id: my_branch
  type: custom
  position: { x: 380, y: 282 }
  data:
    type: if-else
    title: "Check Condition"
    cases:
      - case_id: "true"
        logical_operator: and
        conditions:
          - variable_selector:
              - start
              - query
            comparison_operator: is not
            value: ""
            id: "cond-1"

# Edges for if-else:
- id: branch-true
  source: my_branch
  sourceHandle: "true"          # Matches case_id
  target: process_node
  targetHandle: target
  type: custom

- id: branch-false
  source: my_branch
  sourceHandle: "false"         # Else branch
  target: fallback_node
  targetHandle: target
  type: custom
```

## Iteration Node — Complete Template

```yaml
# Container node
- id: my_iter
  type: custom
  position: { x: 380, y: 200 }
  data:
    type: iteration
    title: "Process Items"
    start_node_id: my_iter_start
    iterator_selector:
      - code_node
      - items
    output_selector:
      - inner_llm
      - text
    is_parallel: false
    parallel_nums: 10
    error_handle_mode: terminated
    height: 200
    width: 400

# Required child: iteration-start
- id: my_iter_start
  type: custom-iteration-start
  parentId: my_iter
  draggable: false
  selectable: false
  zIndex: 1002
  data:
    type: iteration-start
    title: ""
    isInIteration: true

# Inner processing node
- id: inner_llm
  type: custom
  parentId: my_iter
  zIndex: 1002
  position: { x: 200, y: 50 }
  data:
    type: llm
    title: "Process Item"
    isInIteration: true
    iteration_id: my_iter
    model:
      provider: openai
      name: gpt-4
      mode: chat
      completion_params:
        temperature: 0.3
    prompt_template:
      - role: user
        text: "Process: {{#my_iter.item#}}"
    context:
      enabled: false
      variable_selector: []
    vision:
      enabled: false

# Inner edge (note isInIteration in data)
- id: iter-start-to-llm
  source: my_iter_start
  sourceHandle: source
  target: inner_llm
  targetHandle: target
  type: custom
  data:
    isInIteration: true
    iteration_id: my_iter
```

## HTTP Request Node — Complete Template

```yaml
- id: api_call
  type: custom
  position: { x: 380, y: 282 }
  data:
    type: http-request
    title: "Fetch API Data"
    method: GET
    url: "https://api.example.com/data?q={{#start.query#}}"
    authorization:
      type: api-key
      config:
        type: bearer
        api_key: "{{#environment.api_key#}}"
    headers: ""
    params: ""
    body:
      type: none
      data: []
    timeout:
      connect: 10
      read: 30
      write: 30
```

---

## Question Classifier Node — Complete Template

Classifies input text into one of N named classes and routes to a different
downstream edge per class. Each class has a dedicated `sourceHandle` on the node.

```yaml
- id: classifier
  type: custom
  position: { x: 380, y: 300 }
  data:
    type: question-classifier
    title: "Intent Router"
    instruction: >-
      Classify whether the user's request is a Refund, Technical Support,
      General Enquiry, or Other. Choose exactly one category.
    query_variable_selector:
      - start
      - query
    model:
      provider: openai
      name: gpt-4o-mini
      mode: chat
      completion_params:
        temperature: 0.0
    classes:
      - id: "class-refund"
        name: "Refund Request"
      - id: "class-tech"
        name: "Technical Support"
      - id: "class-general"
        name: "General Enquiry"
      - id: "class-other"
        name: "Other"
    # Every class ID above needs exactly one outgoing edge with
    # sourceHandle: "<class-id>" in the edges list.
```

**Edge wiring** — one edge per class:
```yaml
- { id: c-refund,  source: classifier, sourceHandle: "class-refund",   target: refund-handler,  targetHandle: target, type: custom }
- { id: c-tech,    source: classifier, sourceHandle: "class-tech",     target: tech-handler,    targetHandle: target, type: custom }
- { id: c-general, source: classifier, sourceHandle: "class-general",  target: general-handler, targetHandle: target, type: custom }
- { id: c-other,   source: classifier, sourceHandle: "class-other",    target: fallback,        targetHandle: target, type: custom }
```

---

## Parameter Extractor Node — Complete Template

Extracts structured parameters from free-text user input using an LLM.
Outputs are available as `{{#node_id.param_name#}}`.

```yaml
- id: extractor
  type: custom
  position: { x: 380, y: 300 }
  data:
    type: parameter-extractor
    title: "Extract Parameters"
    query_variable_selector:
      - start
      - user_input
    model:
      provider: openai
      name: gpt-4o-mini
      mode: chat
      completion_params:
        temperature: 0.0
    reasoning_mode: function_call      # "function_call" | "prompt"
    parameters:
      - name: location
        type: string
        description: "City or place the user is asking about"
        required: true
        default: ""
      - name: date
        type: string
        description: "Date in YYYY-MM-DD format, or 'today'"
        required: false
        default: "today"
      - name: category
        type: select
        description: "Category of interest"
        required: false
        default: "general"
        options:
          - news
          - weather
          - events
          - general
    # If extraction fails, falls back to defaults (required params raise error)
    error_strategy: default-value
```

---

## Knowledge Retrieval Node — Complete Template

Queries one or more Dify knowledge bases (datasets) and injects retrieved chunks
as context into downstream LLM prompts.

```yaml
- id: retriever
  type: custom
  position: { x: 380, y: 300 }
  data:
    type: knowledge-retrieval
    title: "Knowledge Retrieval"
    query_variable_selector:
      - start
      - question
    retrieval_mode: hybrid           # "single" | "multiple" | "hybrid"
    multiple_retrieval_config:
      reranking_enable: true
      reranking_mode: weighted_score
      weights:
        semantic_item:
          weight: 0.7
        keyword_item:
          weight: 0.3
      top_k: 5
      score_threshold_enabled: true
      score_threshold: 0.4
    dataset_configs:
      retrieval_config:
        search_method: hybrid_search
        reranking_enable: true
        top_k: 5
        score_threshold_enabled: true
        score_threshold: 0.4
      datasets:
        datasets:
          - dataset:
              enabled: true
              id: "<your-dataset-uuid>"
    # Output: `result` (array of retrieved chunks)
    # Reference in LLM: set context.enabled: true and context.variable_selector
```

**Using retrieved context in an LLM node**:
```yaml
- id: answer-llm
  data:
    type: llm
    context:
      enabled: true
      variable_selector:
        - retriever
        - result
    prompt_template:
      - role: system
        text: "Use the following context to answer:\n{{#context#}}"
      - role: user
        text: "{{#start.question#}}"
```

---

## List Operator Node — Complete Template

Filters, sorts, deduplicates, and slices array outputs from upstream code/iteration nodes.

```yaml
- id: filter-results
  type: custom
  position: { x: 380, y: 300 }
  data:
    type: list-operator
    title: "Filter & Rank Results"
    # Input: a variable that holds an array of objects
    variable:
      - code-node
      - results
    # Filter: keep items matching conditions
    filter_by:
      enabled: true
      conditions:
        - variable: score        # key within each array item
          comparison_operator: ">="
          value:
            type: constant
            value: "70"
        - variable: category
          comparison_operator: "contains"
          value:
            type: constant
            value: "article"
      logical_operator: and
    # Sort
    order_by:
      enabled: true
      value: score               # key to sort by
      order: desc
    # Slice to top N
    limit:
      enabled: true
      size: 5
    # Extract a sub-field from each object (optional)
    extract_by:
      enabled: false
    # Output variable: `result` (filtered array)
```

---

## Variable Assigner Node — Complete Template

Writes a value into a **conversation variable** to persist state across turns.
Only meaningful in `advanced-chat` mode where conversation variables exist.

```yaml
- id: update-state
  type: custom
  position: { x: 380, y: 300 }
  data:
    type: variable-assigner
    title: "Update State"
    # List of assignments (can update multiple conversation vars at once)
    assign_list:
      - write_mode: over-write      # "over-write" | "append"
        variable_selector:
          - conversation
          - current_stage           # conversation variable name
        value:
          type: selector
          value_selector:
            - stage-llm             # source node id
            - text                  # output field from that node
      - write_mode: append
        variable_selector:
          - conversation
          - attempt_log
        value:
          type: constant
          value: "attempt made"
```

**Conversation variable must be declared** at the workflow level:
```yaml
workflow:
  conversation_variables:
    - id: cv-stage
      name: current_stage
      value_type: string
      default_value: "init"
```

---

## Agent Node — Complete Template

Runs an autonomous ReAct or function-call agent that can invoke tools iteratively
until it reaches a final answer.

```yaml
- id: research-agent
  type: custom
  position: { x: 380, y: 300 }
  data:
    type: agent
    title: "Research Agent"
    agent_mode:
      strategy: react              # "react" | "function-call" | "tool-call"
      max_iterations: 5
    model:
      provider: openai
      name: gpt-4o
      mode: chat
      completion_params:
        temperature: 0.2
        max_tokens: 2048
    prompt_template:
      - id: sys
        role: system
        text: >-
          You are a research assistant. Use tools to gather data before answering.
          Think step by step. When done, provide a clear final answer.
    memory:
      window:
        enabled: true
        size: 10
    tools:
      - provider_type: builtin     # "builtin" | "workflow" | "api"
        plugin_id: websearch
        tool_name: web_search
        tool_label: "Web Search"
        tool_description: "Search the internet for current information"
        not_used: false
        tool_parameters:
          query:
            type: selector
            value: null            # provided by agent at runtime
          max_results:
            type: constant
            value: "5"
    # Outputs: `text` (final answer), `error` (if failed), tool call logs
    outputs:
      text:
        type: string
      error:
        type: string
```

---

## Template Transform Node — Complete Template

Renders a Jinja2-style template string, substituting variables from upstream nodes.
Useful as a lightweight text-assembly step (no LLM cost).

```yaml
- id: text-assembler
  type: custom
  position: { x: 380, y: 300 }
  data:
    type: template-transform
    title: "Assemble Report"
    template: |
      # {{topic}} Report

      **Summary**: {{summary}}

      **Key Points**:
      {{key_points}}

      Generated at: {{timestamp}}
    # Variables injected into the template (name → node output selector)
    variables:
      - variable: topic
        value_selector:
          - start
          - topic
      - variable: summary
        value_selector:
          - llm-summariser
          - text
      - variable: key_points
        value_selector:
          - code-formatter
          - formatted_points
      - variable: timestamp
        value_selector:
          - sys
          - current_datetime
    # Output: `output` (rendered string)
```

---

## Common Pitfalls

| Pitfall | Prevention |
|---------|-----------|
| Forgetting `type: custom` on nodes | Every node has `type: custom` at the node level |
| Using `type: custom` as the `data.type` | `data.type` is the node type (`llm`, `code`, etc.) |
| Missing `sourceHandle`/`targetHandle` on edges | Always include both; `targetHandle` is always `"target"` |
| `version` as number instead of string | Use `"0.6.0"` (quoted), not `0.6.0` |
| `end` node in advanced-chat mode | Use `answer` node instead |
| `answer` node in workflow mode | Use `end` node instead |
| Variable ref in text without `#` delimiters | Must be `{{#node.var#}}` not `{{node.var}}` |
| `value_selector` with wrong nesting | It's a flat array: `[node_id, var]` not `[[node_id, var]]` |
| Edges inside iteration missing `isInIteration` | Add `data.isInIteration: true` and `data.iteration_id` |
| LLM `prompt_template` as object instead of array | For chat mode, it MUST be an array of `{role, text}` objects |
| Code node returns keys not declared in `outputs` | Every returned key must be in `outputs` with its type |

---

## Error Handling — Node-Level

Any node can use error strategies:

```yaml
data:
  error_strategy: fail-branch    # "fail-branch" | "default-value" | null
  default_value:                  # Only with "default-value"
    - key: text
      type: string
      value: "Fallback result"
  retry_config:
    retry_enabled: true
    max_retries: 3
    retry_interval: 1000          # Milliseconds
```

When using `fail-branch`, add edges for both `"success-branch"` and `"fail-branch"` sourceHandles.

---

## Environment Variables and Secrets

```yaml
workflow:
  environment_variables:
    - id: "env-1"
      name: api_key
      value: ""                   # Empty in exported DSL (secret)
      value_type: secret          # "string" | "number" | "secret"
      description: "API key"
      selector:
        - environment
        - api_key
```

Reference in nodes: `value_selector: [environment, api_key]` or `{{#environment.api_key#}}`.

---

## Conversation Variables (Advanced-Chat Only)

```yaml
workflow:
  conversation_variables:
    - id: "conv-1"
      name: chat_history
      value: ""
      value_type: string
      description: "Running summary"
      selector:
        - conversation
        - chat_history
```

Update with `assigner` node using `operation: over-write` or `append`.

---

## Plugin Dependencies

When a workflow uses external tools/providers, declare them:

```yaml
dependencies:
  - type: plugin
    value:
      organization: langgenius
      plugin: openai
      version: "1.0.0"
  - type: marketplace
    value:
      marketplace_plugin_unique_identifier: "langgenius/x:0.0.16@hash"
```

---

## Validation Checklist — Run Before Delivering

1. **Parse**: YAML is valid (no syntax errors)
2. **Structure**: All top-level keys present (`version`, `kind`, `app`, `workflow`, `dependencies`)
3. **Start node**: Exactly one, with properly typed variables
4. **Terminal node**: At least one `end` (workflow) or `answer` (advanced-chat)
5. **Edges**: Every non-start node reachable; every non-terminal node has outgoing edge
6. **References**: All `value_selector` and `{{#...#}}` resolve to upstream nodes
7. **Branching**: if-else has edges for all cases + false; classifier has edges for all classes
8. **Containers**: iteration/loop have proper start child nodes with `parentId` linkage
9. **Secrets**: No hardcoded API keys or tokens
10. **IDs**: All node IDs and edge IDs are unique within their respective arrays

Automated validation: `python3 .github/skills/dify-workflow/scripts/validate_dify_dsl.py <file>`

---

## Additional Resources

- **`references/dsl-specification.md`** — Complete DSL v0.6.0 specification with full field schemas for every node type
- **`examples/minimal-echo.yaml`** — Simplest possible workflow (start → end)
- **`examples/llm-chatflow.yaml`** — Basic LLM chatflow with memory (advanced-chat)
- **`examples/conditional-routing.yaml`** — If-else branching with aggregation
- **`examples/conversation-state.yaml`** — Conversation variable state machine (advanced-chat)
- **`examples/iteration-pipeline.yaml`** — Parallel iteration over array items
- **`examples/code-transform-chain.yaml`** — Code node + template transform + LLM pipeline
- **`examples/list-operator-filter.yaml`** — Code → list-operator (filter/sort/limit) → LLM
- **`examples/rag-pipeline.yaml`** — Knowledge retrieval → context-injected LLM
- **`examples/self-check-loop.yaml`** — LLM generation with validation loop
- **`examples/http-fan-out.yaml`** — HTTP fan-out via iteration
- **`examples/agent-tool-pipeline.yaml`** — ReAct agent with tools and error branch
- **`examples/parameter-extractor.yaml`** — LLM parameter extraction → validate → route
- **`examples/README.md`** — Full example index with complexity ratings and pattern reference

Validate all examples at once:
```bash
python3 .github/skills/dify-workflow/scripts/validate_dify_dsl.py --dir examples/
```

---

## Procedure — Convert a Chat App to a Workflow

Use this procedure when migrating a simple `chat` or `completion` Dify app to a
`workflow` or `advanced-chat` DSL-based app.

### Step 1 — Choose the Target Mode

| Original App Type | Target Mode | Reason |
|---|---|---|
| `chat` (conversational) | `advanced-chat` | Preserves turn history; use `answer` node |
| `completion` (one-shot) | `workflow` | No history; use `end` node |
| Mixture of both | `advanced-chat` | Safer default; `end` nodes can't be reused |

### Step 2 — Map Old Prompts to Node Structure

Each prompt block in the old app becomes a chain of nodes:

```
Simple chat prompt → start → llm (system prompt moved to prompt_template[0]) → answer
```

If the old app had **pre-processing code** (webhooks, middleware), move it to a
`code` node between `start` and the first `llm`:

```
start → code (pre-processing) → llm → answer
```

### Step 3 — Convert Form Variables

Old completion app has a `inputs` block — map each field to a start node variable:

```yaml
# OLD (completion app)
inputs:
  - key: topic
    type: text-input
    required: true

# NEW (workflow DSL)
- id: start
  data:
    type: start
    variables:
      - variable: topic
        label: "Topic"
        type: text-input
        required: true
        max_length: null
        options: []
```

### Step 4 — Add Memory to the LLM Node

For `advanced-chat` mode, enable memory so the LLM receives conversation history:

```yaml
memory:
  window:
    enabled: true
    size: 10    # last N turns
```

For `workflow` mode (one-shot), set `memory: null` or omit it.

### Step 5 — Replace End with Answer (if advanced-chat)

In `workflow` mode: keep `end` node with `outputs`.
In `advanced-chat` mode: replace with `answer` node using `answer:` field:

```yaml
# WRONG in advanced-chat:
- data:
    type: end
    outputs: [...]

# CORRECT in advanced-chat:
- data:
    type: answer
    answer: "{{#llm.text#}}"
```

### Step 6 — Validate

```bash
python3 .github/skills/dify-workflow/scripts/validate_dify_dsl.py --strict <output.yaml>
```

---

## DSL Version Migration Guide

### Upgrading from DSL v0.5.x to v0.6.0

| Change | v0.5.x | v0.6.0 |
|---|---|---|
| `dependencies` key | Optional / absent | Required (use `[]` if none) |
| `conversation_variables` | Not supported | Supported in `advanced-chat` |
| `environment_variables` | Not supported | Supported; use for secrets |
| `loop` node | Not available | Added in v0.6.0 |
| `agent` node | Not available | Added in v0.6.0; replaces custom agent workarounds |
| `list-operator` node | Not available | Added in v0.6.0 |
| `parameter-extractor` | Used LLM + code workaround | Native node type |
| `question-classifier` classes | Had `label` field | Renamed to `name` in v0.6.0 |
| `if-else` cases | `condition_id` on each condition | Removed; conditions are an array with `logical_operator` at the case level |
| `start` form field `hide` | Not supported | Supported in v0.6.0 for password masking |
| `memory.window` | Set via `memory_config` | Moved to `memory.window.size` |
| `completion_params.stop` | Array of stop sequences | Deprecated; remove if present |

### Breaking Changes

1. **`question-classifier` class fields**: If your v0.5.x DSL has `label:` on each
   class object, rename to `name:`.

2. **`if-else` case structure**: If cases have a flat `conditions` at the data level
   (not nested under `cases`), restructure:
   ```yaml
   # v0.5.x (BROKEN in v0.6.0):
   data:
     type: if-else
     conditions:
       - comparison_operator: "=="
         variable_selector: [start, flag]
         value: "true"

   # v0.6.0 (CORRECT):
   data:
     type: if-else
     cases:
       - case_id: "true"
         logical_operator: and
         conditions:
           - comparison_operator: "=="
             variable_selector: [start, flag]
             value: "true"
   ```

3. **Missing `dependencies`**: Add `dependencies: []` at the top level if absent.

4. **Hardcoded secrets**: v0.6.0 workflows are more likely to be version-controlled.
   Move all secrets to `environment_variables` with `value_type: secret`.

### Compatibility Checker

Run the validator with `--strict` to surface v0.5.x legacy patterns:
```bash
python3 scripts/validate_dify_dsl.py --strict your-workflow.yaml
```

The `--strict` flag enables additional URL and security pattern checks that catch
insecure patterns common in pre-v0.6.0 workflows.

---

## Production Issues — Known Patterns and Fixes

These anti-patterns were found in real production workflows during compliance checks.
Use the validator (`scripts/validate_dify_dsl.py`) to detect them automatically.

### P1 — Empty `iterator_selector` on Iteration Node

**Symptom**: `iterator_selector: []` in the iteration container's `data` block.

**Root cause**: The array source was deleted or never wired before the iteration was
published. Dify silently allows empty selectors in the editor but the iteration will
fail at runtime.

**Fix**: Set `iterator_selector` to the correct upstream variable path:
```yaml
iterator_selector:
- <source_node_id>
- <output_variable_name>   # must be an array/list type
```

**Validator**: `[ERROR] Node 'X': iteration has empty 'iterator_selector' — no input array to iterate`

---

### P2 — Inner Node with Missing `parentId`

**Symptom**: A node has `isInIteration: true` or `isInLoop: true` in its `data`
block but has **no `parentId`** at the node level.

**Root cause**: Occurs when a node is cut/pasted from within a container and the
editor strips `parentId`, or when a node is manually written with the inner-node
flags but the container reference was forgotten.

**Impact**: The node is not rendered inside the container in the Dify UI, and its
variable outputs may not be visible to downstream container-internal nodes.

**Fix**: Add `parentId: '<container_node_id>'` to the node:
```yaml
- data:
    isInLoop: true
    type: code
    ...
  id: 'orphaned_node_id'
  parentId: '<loop_or_iteration_container_id>'   # ← add this
```

**Validator**: `[WARN] Node 'X' (code) declares isInIteration/isInLoop but has no 'parentId'`

---

### P3 — Outer Node Falsely Tagged `isInLoop`

**Symptom**: An outer-graph node (with no `parentId`) has `isInLoop: true` in its
`data`. This causes the Dify UI to render the node in the wrong context.

**Root cause**: Usually from copy-paste of inner-container nodes to the outer graph.
The editor copies the `isInLoop` flag but does not assign a `parentId`, creating a
hybrid state.

**Fix**: Set `isInLoop: false` (and remove `loop_id`) on outer nodes:
```yaml
- data:
    isInLoop: false   # ← was true; this node has no parentId, it's an outer node
    title: MyOuterNode
    ...
  id: 'outer_node_id'
  # parentId is absent — correct for outer nodes
```

---

### P4 — Hardcoded Secrets in YAML

**Symptom**: API keys, GitHub PATs, or bearer tokens appear as literal strings in
`authorization.config.api_key`, HTTP `headers`, or `start` node field defaults.

**Root cause**: Copied from a working local test directly into the DSL YAML.

**Security risk**: DSL YAML files are often committed to source control or shared
across teams. Hardcoded tokens will be exposed.

**Fix**: Move secrets to Dify's `environment_variables` with `value_type: secret`,
then reference via `{{#environment.var_name#}}`:

```yaml
# In workflow.environment_variables (top level):
environment_variables:
- id: env-git-token
  name: git_api_key
  value: ""          # ← empty — set at runtime in Dify UI

# In HTTP node authorization:
authorization:
  config:
    api_key: '{{#environment.git_api_key#}}'
    type: bearer
  type: api-key
```

For **start node form fields** that collect tokens from users, use `hide: true` so
the value is masked in the Dify UI:
```yaml
- variable: git_api_key
  type: text-input
  hide: true          # ← masks input in the run form
  required: true
  default: ""         # ← never put a real token here
```

**Validator**: `[ERROR] Possible hardcoded GitHub personal access token detected in YAML`

---

### P5 — Duplicate `iteration-start` + `loop-start` in Same Container

**Symptom**: A container node has both an `iteration-start` child and a `loop-start`
child registered under it.

**Root cause**: Manual hybridization or corrupted Dify editor state when the
container was switched from `iteration` to `loop` (or vice versa) without cleaning
up the old start node.

**Impact**: Ambiguous routing — the DSL spec says `start_node_id` should point to
exactly one start node. The runtime behavior is undefined.

**Fix**: Remove the stale start node and ensure `start_node_id` references the
correct surviving start node. For `iteration` containers, the start type should be
`iteration-start`. For `loop` containers, it should be `loop-start`.

---

## Advanced Patterns

### A1 — Multi-Stage Expert Swarm (NIC Porting Pattern)

The pattern used in `dify-expert-team-stage.yaml`: an LLM decomposes work into sub-steps
upstream, then an **iteration container** runs a team of parallel expert-LLM agents for each
sub-step.

```
start
  └─ github_fetch (http-request)
       └─ context_builder (code)
            └─ stage_planner (llm)        ← produces structured step list
                 └─ expert_team (iteration)  ← iterates over steps
                      iteration-start
                           └─ agent_0 (llm)  ─┐
                           └─ agent_1 (llm)   ├─ experts
                           └─ agent_2 (llm)  ─┘
                                └─ aggregator (variable-aggregator)
                                     └─ supervisor_gate (code)  ← scoring
                                          └─ git_commit (code)
  └─ git_push (http-request)
       └─ create_pr (http-request)
            └─ end
```

**Key properties**:
- `iterator_selector` points to the LLM's `text` output (stage plan as markdown)
- `is_parallel: false` — sub-steps run sequentially, each one builds on the last
- Inner agents use `{{#item#}}` to reference the current iteration item
- `output_selector` collects the final deliverable from the last inner node

**Iteration container template**:
```yaml
- data:
    type: iteration
    start_node_id: <id>start0
    iterator_selector:
    - <stage_planner_node_id>
    - text
    output_selector:
    - <final_inner_node_id>
    - <output_var>
    is_parallel: false
    flatten_output: true
    error_handle_mode: terminated
  id: <id>
  parentId:             # absent — this is an outer node
```

---

### A2 — HTTP Fan-Out via Iteration

When you need to call the same HTTP endpoint multiple times with different parameters
(e.g., fetch multiple GitHub files), use `iteration` with a code node that builds the
URL list, then an `http-request` node inside the container:

```
start
  └─ url_builder (code)       → outputs: urls: ["url1","url2","url3"]
       └─ fetch_loop (iteration)
            iteration-start
                 └─ fetcher (http-request)  url={{#item#}}
                      └─ parser (code)
  └─ merge_results (variable-aggregator)
       └─ end
```

---

### A3 — Parameter Extractor → Structured Pipeline

Use an LLM with structured output enabled + a code node to validate/transform the
extraction before feeding downstream agents:

```
start (raw user input)
  └─ extractor (llm, structured_output_enabled: true)
       └─ validator (code)   ← validates required fields, sets defaults
            └─ router (if-else)  ← branch on validation result
                 ├─ true_branch: agent_pipeline (llm)
                 └─ false_branch: request_clarification (llm)
                      └─ aggregator (variable-aggregator)
                           └─ answer
```

---

### A4 — Conversation State Machine (advanced-chat)

Use `conversation_variables` to track multi-turn state across sessions. Conversation
variables persist across turns within a session (unlike regular node outputs which
reset each turn).

```yaml
workflow:
  conversation_variables:
  - id: cv-stage
    name: current_stage
    value_type: string
    default_value: "init"
  - id: cv-count
    name: attempt_count
    value_type: number
    default_value: "0"
```

Reference in nodes: `{{#conversation.current_stage#}}`

Update with `variable-assigner` node type:
```yaml
- data:
    type: variable-assigner
    assigned_variable_selector:
    - conversation
    - current_stage
    write_mode: overwrite
    input_variable_selector:
    - my_llm_node
    - text
  id: update_stage
```

Typical state machine flow:
```
start
  └─ read_state (llm, reads conversation.current_stage)
       └─ router (question-classifier, classifies user intent)
            ├─ "next" → advance_stage (variable-assigner)
            ├─ "retry" → retry_handler (llm)
            └─ "done"  → summarizer (llm)
                 └─ answer
```

---

### A5 — Parallel Fan-Out with Aggregation

Run multiple independent expert agents in parallel, then merge:

```yaml
# No direct parallel node — achieve via multiple edges FROM one source:
edges:
- source: router
  target: agent_code_review
  sourceHandle: source
- source: router
  target: agent_security
  sourceHandle: source
- source: router
  target: agent_performance
  sourceHandle: source
# All three converge on variable-aggregator:
- source: agent_code_review
  target: aggregator
  sourceHandle: source
- source: agent_security
  target: aggregator
  sourceHandle: source
- source: agent_performance
  target: aggregator
  sourceHandle: source
```

**`variable-aggregator` template**:
```yaml
- data:
    type: variable-aggregator
    variables:
    - - agent_code_review
      - text
    - - agent_security
      - text
    - - agent_performance
      - text
    output_type: string
  id: aggregator
```

---

### A6 — Agent + Error Guard Pattern

When deploying an autonomous agent node, always add an `if-else` gate downstream
to separate successful completions from runtime failures. Agents can fail due to
tool errors, model refusals, or context exhaustion.

```
start
  └─ agent (ReAct, tools: [web_search, calculator])
       └─ error-gate (if-else: agent.error is-empty → true/false)
            ├─ true:  answer-success   "{{#agent.text#}}"
            └─ false: answer-fallback  "I hit an issue: {{#agent.error#}}"
```

**Key properties**:
- Agent outputs `text` (final answer) and `error` (failure reason)
- Gate condition: `variable_selector: [agent, error]`, `comparison_operator: is-empty`
- Both branches end with `answer` nodes (in advanced-chat) or `end` (workflow)
- Set `max_iterations: 5` to cap runaway tool-calling loops
- Bind only the tools the agent actually needs — excess tools confuse ReAct reasoning

→ See: [examples/agent-tool-pipeline.yaml](examples/agent-tool-pipeline.yaml)

---

### A7 — List Filtering Pipeline

When code or an API returns a large array that needs post-processing before
sending to an LLM (cost control, relevance, de-duplication), use `list-operator`
to filter, sort, and cap the list:

```
start
  └─ codegen (code)     → returns: results: array[object]
       └─ filter (list-operator)
            filter_by: {score >= 70}
            order_by: score desc
            limit: 5
       └─ summariser (llm)   receives top-5 objects
            └─ end
```

**Key properties**:
- `list-operator.variable` selector must point to an `array[object]` output
- `filter_by.conditions[].variable` is a **key within each array item**, not a node ref
- Use `limit.size` to cap context size sent to the LLM — prevents token overflow
- `order_by.value` is also an item key name, not a `value_selector`
- Chaining two list-operators (filter → extract) is valid and common

→ See: [examples/list-operator-filter.yaml](examples/list-operator-filter.yaml)

---

### A8 — Conversation State Machine (Cross-Turn Context)

Collect and accumulate structured user context across multiple chat turns using
`conversation_variables` + `variable-assigner`. The question-classifier routes
each turn to the correct phase: info-collection or Q&A.

```
# Per-turn flow:
start
  └─ intent-classifier (question-classifier)
       ├─ class-info → info-llm → ctx-assigner (update conversation.context) → answer
       └─ class-qa   → qa-llm (reads conversation.context) → answer

# conversation.context persists across all turns in the session
```

**Key properties**:
- Declare `conversation_variables` at the workflow level with a `string` type
- `variable-assigner` uses `write_mode: over-write` to replace context each turn
  or `write_mode: append` to accumulate
- LLM prompt accesses state via `{{#conversation.context#}}`
- State is **session-scoped** — it resets on a new conversation session

→ See: [examples/conversation-state.yaml](examples/conversation-state.yaml)

---

## Performance Tips

1. **Parallelism**: Set `is_parallel: true` on iteration nodes when inner steps are
   independent. Set `parallel_nums` to control the concurrency cap.

2. **Token budget**: Use `completion_params.max_tokens` on LLM nodes to prevent
   runaway generations in tightly-looped pipelines.

3. **HTTP timeouts**: Always set `timeout.read` to at least `60` for LLM-backed APIs.
   Set `retry_config.max_retries: 3` with `retry_interval: 100`ms.

4. **Context pruning**: In multi-turn chatflows, set `memory.window.size` to limit
   history injection. Default `memory: null` injects full history — expensive.

5. **Streaming**: In `advanced-chat` mode, prefer `answer` nodes that receive LLM
   `text` output for streaming UX. Avoid chaining multiple heavy LLMs before `answer`.

6. **List-operator before LLM**: Always use `list-operator` to cap arrays to ≤10
   items before injecting into an LLM prompt. Large arrays inflate token count and
   degrade reasoning quality — filter first, then summarise.

7. **Agent iteration cap**: Always set `agent_mode.max_iterations` ≤ 8.
   Uncapped agents can consume hundreds of LLM calls before a timeout.

---

## Debugging Workflows in Dify

| Error Message | Cause | Fix |
|---|---|---|
| `iterator_selector is empty` | Iteration has no source array | Set `iterator_selector` to `[node_id, var]` |
| `Variable not found: #X.Y#` | Node ID or output var typo | Check `value_selector` paths against actual node IDs |
| `Node is unreachable` | Missing incoming edge | Add edge with `source: upstream_id`, `target: node_id` |
| `Unexpected character in YAML` | Unquoted `:` or `{` in strings | Wrap strings in single quotes |
| `Graph must have exactly one start node` | Two `type: start` nodes | Delete duplicate start node |
| `Answer node required for advanced-chat` | Mode is `advanced-chat` but only `end` node exists | Replace `end` with `answer` node |
| `Iteration start node not found` | `start_node_id` value doesn't match any inner node ID | Fix `start_node_id` to match the `iteration-start` child node's `id` |
| `Agent hit max_iterations` | Agent tool loop did not converge | Increase `max_iterations`, simplify tools, or add explicit stop conditions |
| `class has no outgoing edge` | question-classifier class not wired | Add an edge with `sourceHandle: "<class-id>"` for every class |
| `list-operator missing 'variable'` | list-operator has no input array | Set `variable: [node_id, output_array_field]` |
