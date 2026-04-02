<!-- File: dify-workflow-dsl-specification.md -->
# Dify Workflow DSL YAML Specification

> Derived from the Dify codebase (current DSL version: **0.6.0**). Based on source analysis of `api/services/app_dsl_service.py`, `api/models/workflow.py`, `api/dify_graph/`, and test fixtures.

---

## 1. Top-Level Structure

Every Dify DSL YAML file has these top-level keys:

```yaml
version: "0.6.0"          # DSL version string (required)
kind: app                  # Always "app" (required)
app:                       # App metadata (required)
  name: "My Workflow"
  mode: workflow           # "workflow" | "advanced-chat" | "chat" | "completion" | "agent-chat"
  icon: "🤖"
  icon_type: emoji         # "emoji" | "image" | "link"
  icon_background: "#FFEAD5"
  description: "Description of the app"
  use_icon_as_answer_icon: false
workflow:                  # Workflow definition (required for mode: workflow | advanced-chat)
  graph: { ... }
  features: { ... }
  environment_variables: []
  conversation_variables: []
dependencies: []           # Plugin dependencies list
```

### App Modes

| Mode | Description | Uses `workflow` key | Uses `model_config` key |
| ------ | ------------- | -------------------- | ----------------------- |
| `workflow` | Workflow app (graph-based) | Yes | No |
| `advanced-chat` | Chatflow app (graph + conversation memory) | Yes | No |
| `chat` | Simple chat app | No | Yes |
| `completion` | Text generation app | No | Yes |
| `agent-chat` | Agent chat app | No | Yes |

This document focuses on `workflow` and `advanced-chat` modes.

---

## 2. Workflow Structure

```yaml
workflow:
  graph:
    nodes: [...]           # Array of node objects
    edges: [...]           # Array of edge objects
    viewport:              # Canvas viewport (optional, for UI positioning)
      x: 0
      y: 0
      zoom: 0.7
  features: { ... }        # App features configuration
  environment_variables: [] # Workflow-scoped env vars
  conversation_variables: [] # Conversation-scoped vars (advanced-chat only)
```

---

## 3. Graph: Nodes

Each node in the `nodes` array has this shape:

```yaml
- id: "node_id_string"     # Unique node ID (string, usually a timestamp or descriptive name)
  type: custom              # Always "custom" (React Flow node type)
  data:                     # Node-specific data — the important part
    type: start             # Node type string (see full list below)
    title: "Start"          # Display title
    desc: ""                # Description (optional)
    version: "1"            # Node data version (optional, default "1")
    # ... node-type-specific fields ...
  position:                 # UI canvas position
    x: 30
    y: 227
  positionAbsolute:         # Absolute position (optional)
    x: 30
    y: 227
  sourcePosition: right     # Source handle position (optional)
  targetPosition: left      # Target handle position (optional)
  selected: false           # Selection state (optional)
  height: 90                # Node height (optional)
  width: 244                # Node width (optional)
  zIndex: 0                 # Z-index for layering (optional)
  parentId: "parent_node"   # Parent container node ID (for nodes inside iteration/loop)
  draggable: false          # Whether draggable (optional, false for iteration-start/loop-start)
  selectable: false         # Whether selectable (optional)
```

### Nodes Inside Containers

Nodes inside an **iteration** or **loop** have extra fields in `data`:

```yaml
data:
  isInIteration: true       # Whether inside an iteration container
  isInLoop: true            # Whether inside a loop container
  iteration_id: "iter_node" # Parent iteration node ID
  loop_id: "loop_node"      # Parent loop node ID
```

And at the node level:

```yaml
parentId: "container_node_id"   # Links to the parent container
zIndex: 1002                    # Higher z-index for nested nodes
```

---

## 4. All Node Types

### 4.1 `start` — Start Node

Entry point of the workflow. Defines user input variables.

```yaml
data:
  type: start
  title: Start
  variables:
  - variable: query          # Variable name (used in references)
    label: query             # Display label
    type: text-input         # Input type (see below)
    required: true
    max_length: null         # Max length (null for unlimited)
    options: []              # Options for "select" type
    default: null            # Default value (optional)
    description: ""          # Description (optional)
    hide: false              # Hide from user (optional)
    # File-specific fields:
    allowed_file_types: []   # ["image", "document", ...]
    allowed_file_extensions: []
    allowed_file_upload_methods: []  # ["local_file", "remote_url"]
    json_schema: null        # JSON schema for json_object type
```

**Variable input types** (`VariableEntityType`):

- `text-input` — Single line text
- `paragraph` — Multi-line text
- `number` — Numeric input
- `select` — Dropdown select (uses `options`)
- `file` — Single file upload
- `file-list` — Multiple file upload
- `checkbox` — Boolean checkbox
- `json_object` — JSON object input (uses `json_schema`)

---

### 4.2 `end` — End Node

Terminal node for `workflow` mode. Defines output variables.

```yaml
data:
  type: end
  title: End
  outputs:
  - variable: answer         # Output variable name
    value_type: string       # Output type
    value_selector:          # Source variable selector
    - llm_node               # Node ID
    - text                   # Variable name from that node
```

**Output value types** (`OutputVariableType`):
`string`, `number`, `integer`, `boolean`, `object`, `file`, `array`, `array[string]`, `array[number]`, `array[object]`, `array[boolean]`, `array[file]`, `any`, `array[any]`

---

### 4.3 `answer` — Answer Node

Streaming response node for `advanced-chat` mode. Uses template strings with variable references.

```yaml
data:
  type: answer
  title: Answer
  answer: "{{#llm.text#}}"   # Template string with variable references
```

Variable references use the syntax: `{{#node_id.variable_name#}}`

---

### 4.4 `llm` — LLM Node

Calls a language model.

```yaml
data:
  type: llm
  title: LLM
  model:
    provider: openai          # Provider identifier
    name: gpt-4               # Model name
    mode: chat                # "chat" | "completion"
    completion_params:        # Model parameters
      temperature: 0.7
      max_tokens: 4096
      top_p: 1.0
  prompt_template:            # For chat mode: array of messages
  - role: system
    text: "You are a helpful assistant."
    edition_type: basic       # "basic" | "jinja2" (optional)
    jinja2_text: null         # Jinja2 template (optional, when edition_type is jinja2)
  - role: user
    text: "{{#start_node.query#}}"
  # For completion mode: single template object
  # prompt_template:
  #   text: "Complete this: {{#start_node.query#}}"
  #   edition_type: basic
  prompt_config:
    jinja2_variables: []      # Jinja2 template variables
  context:
    enabled: false            # Whether to inject retrieved context
    variable_selector: []     # Source of context (e.g., ["knowledge_node", "result"])
  memory:                     # Conversation memory (advanced-chat mode)
    window:
      enabled: false
      size: 10
    query_prompt_template: "{{#sys.query#}}"
    role_prefix:              # Optional role prefixes
      user: "Human"
      assistant: "AI"
  vision:
    enabled: false
    configs:
      variable_selector:
      - sys
      - files
      detail: high            # "high" | "low"
  structured_output: null     # JSON schema for structured output (optional)
  structured_output_enabled: false
  reasoning_format: tagged    # "separated" | "tagged"
```

**Prompt message roles**: `system`, `user`, `assistant`

---

### 4.5 `code` — Code Execution Node

Runs Python3 or JavaScript code.

```yaml
data:
  type: code
  title: Code
  code_language: python3      # "python3" | "javascript"
  code: |
    def main(arg1: str) -> dict:
        return {
            "result": arg1.upper(),
        }
  variables:                  # Input variables mapped to function params
  - variable: arg1            # Function parameter name
    value_selector:           # Source variable
    - start_node
    - query
  outputs:                    # Output schema
    result:
      type: string            # "string" | "number" | "object" | "boolean" |
                              # "array[string]" | "array[number]" | "array[object]" | "array[boolean]"
      children: null          # For nested object types (optional)
  dependencies: []            # External dependencies (optional)
```

---

### 4.6 `if-else` — Conditional Branch Node

Routes execution based on conditions.

```yaml
data:
  type: if-else
  title: IF/ELSE
  cases:
  - case_id: "true"          # Case identifier (used as sourceHandle in edges)
    logical_operator: and     # "and" | "or" between conditions
    conditions:
    - variable_selector:      # Variable to evaluate
      - start_node
      - query
      comparison_operator: contains   # See operators below
      value: "hello"          # Comparison value
      id: "uuid-string"       # Unique condition ID
      varType: string         # Variable type hint (optional)
```

**Comparison operators**:

- String/Array: `contains`, `not contains`, `start with`, `end with`, `is`, `is not`, `empty`, `not empty`, `in`, `not in`, `all of`
- Number: `=`, `≠`, `>`, `<`, `≥`, `≤`
- Null checks: `null`, `not null`
- File: `exists`, `not exists`

**Edge sourceHandle values for if-else**:

- First case: `"true"` (or the `case_id`)
- Additional cases: their `case_id`
- Default/else branch: `"false"`

---

### 4.7 `http-request` — HTTP Request Node

Makes HTTP API calls.

```yaml
data:
  type: http-request
  title: HTTP Request
  method: GET                 # GET | POST | PUT | PATCH | DELETE | HEAD | OPTIONS
  url: "https://api.example.com/data"  # Supports variable references
  authorization:
    type: no-auth             # "no-auth" | "api-key"
    config:                   # Required when type is "api-key"
      type: bearer            # "basic" | "bearer" | "custom"
      api_key: ""
      header: ""              # Custom header name (for "custom" type)
  headers: |                  # Headers as key:value per line
    Content-Type: application/json
  params: |                   # Query params as key:value per line
    page: 1
  body:
    type: json                # "none" | "form-data" | "x-www-form-urlencoded" | "raw-text" | "json" | "binary"
    data:                     # Body data entries
    - key: name
      type: text              # "text" | "file"
      value: "{{#start_node.query#}}"
      file: []                # File variable selector (for type: file)
  timeout:
    connect: 10               # Connection timeout (seconds)
    read: 30                  # Read timeout
    write: 30                 # Write timeout
```

**HTTP node outputs** (available downstream):

- `status_code` (number)
- `body` (string)
- `headers` (string)
- `files` (array[file])

---

### 4.8 `tool` — Tool Call Node

Invokes external tools/plugins.

```yaml
data:
  type: tool
  title: Google Search
  provider_id: "langgenius/google"
  provider_type: builtin      # "builtin" | "api" | "workflow"
  provider_name: "Google"
  tool_name: "google_search"
  tool_label: "Google Search"
  tool_configurations:        # Static tool config
    result_type: text
  tool_parameters:            # Dynamic inputs
    query:
      value: "{{#start_node.query#}}"   # For mixed type
      type: mixed              # "mixed" | "variable" | "constant"
    # Variable type example:
    # input:
    #   value: ["start_node", "query"]
    #   type: variable
  tool_node_version: "1"      # Optional version
  credential_id: null         # Plugin credential (optional, stripped on export without secrets)
  plugin_unique_identifier: null
```

---

### 4.9 `template-transform` — Template Transform Node

Renders a Jinja2 template.

```yaml
data:
  type: template-transform
  title: Format Output
  template: |
    Hello, {{ name }}! Your query was: {{ query }}
  variables:                  # Variables available in the template
  - variable: name            # Template variable name
    value_selector:
    - start_node
    - name
  - variable: query
    value_selector:
    - start_node
    - query
```

**Output**: `output` (string)

---

### 4.10 `question-classifier` — Question Classifier Node

Classifies input into categories using an LLM.

```yaml
data:
  type: question-classifier
  title: Question Classifier
  query_variable_selector:
  - start_node
  - query
  model:
    provider: openai
    name: gpt-4
    mode: chat
    completion_params:
      temperature: 0.7
  classes:
  - id: "class_1"
    name: "Technical Question"
  - id: "class_2"
    name: "General Question"
  instruction: "Classify the user's question into one of the categories."
  memory: null                # MemoryConfig (optional, for advanced-chat)
  vision:
    enabled: false
```

**Edge sourceHandle**: The `class_id` (e.g., `"class_1"`, `"class_2"`)

---

### 4.11 `knowledge-retrieval` — Knowledge Retrieval Node

Retrieves context from knowledge bases/datasets.

```yaml
data:
  type: knowledge-retrieval
  title: Knowledge Retrieval
  query_variable_selector:
  - start_node
  - query
  dataset_ids:
  - "dataset-uuid-1"
  - "dataset-uuid-2"
  retrieval_mode: multiple    # "single" | "multiple"
  multiple_retrieval_config:
    top_k: 3
    score_threshold: 0.5
    reranking_mode: reranking_model
    reranking_enable: true
    reranking_model:
      provider: "cohere"
      model: "rerank-english-v2.0"
    weights: null             # WeightedScoreConfig (optional)
  single_retrieval_config:    # Used when retrieval_mode is "single"
    model:
      provider: openai
      name: gpt-4
      mode: chat
  metadata_filtering_mode: disabled  # "disabled" | "automatic" | "manual"
  metadata_model_config: null
  metadata_filtering_conditions: null
```

**Output**: `result` (array[object]) — retrieved document chunks

---

### 4.12 `variable-aggregator` — Variable Aggregator Node

Selects the first available result from multiple branches. Also known as `variable-assigner` (legacy name).

```yaml
data:
  type: variable-aggregator
  title: Variable Aggregator
  output_type: string
  variables:                  # Variables to aggregate (first available wins)
  - - branch_a_node
    - output
  - - branch_b_node
    - output
  advanced_settings:          # Optional group configuration
    group_enabled: true
    groups:
    - group_name: Group1
      output_type: string
      variables:
      - - node_1
        - output
      - - node_2
        - output
      groupId: "uuid"         # Optional group identifier
    - group_name: Group2
      output_type: string
      variables:
      - - node_3
        - output
      - - node_4
        - output
```

**Output**: `output` (type matches `output_type`); with groups: `GroupName.output`

---

### 4.13 `assigner` — Variable Assigner Node (v2)

Writes/updates variable values (often conversation variables).

```yaml
data:
  type: assigner
  title: Variable Assigner
  version: "2"
  items:
  - variable_selector:        # Target variable to update
    - conversation
    - str
    input_type: variable      # "variable" | "constant"
    operation: over-write     # Operation to perform
    value:                    # Source (variable selector for "variable" input_type, literal for "constant")
    - sys
    - query
```

**Operations** (`Operation` enum):

- `over-write` — Replace value
- `clear` — Clear/reset value
- `append` — Append to array
- `extend` — Extend array
- `set` — Set value
- `+=` — Add to number
- `-=` — Subtract from number
- `*=` — Multiply number
- `/=` — Divide number
- `remove-first` — Remove first array element
- `remove-last` — Remove last array element

---

### 4.14 `iteration` — Iteration Node (Container)

Loops over an array, executing inner nodes for each element.

```yaml
data:
  type: iteration
  title: Iteration
  start_node_id: iteration_nodestart   # ID of the iteration-start child node
  iterator_selector:          # Array variable to iterate over
  - code_node
  - result
  output_selector:            # Variable to collect from each iteration
  - code_inner_node
  - result
  is_parallel: false          # Enable parallel execution
  parallel_nums: 10           # Max parallel iterations
  error_handle_mode: terminated  # "terminated" | "continue-on-error" | "remove-abnormal-output"
  flatten_output: true        # Flatten nested array outputs
  height: 178                 # Container dimensions
  width: 388
```

The iteration container must contain an `iteration-start` child node:

```yaml
- data:
    type: iteration-start
    title: ""
    isInIteration: true
  id: iteration_nodestart
  parentId: iteration_node     # Must match iteration container ID
  type: custom-iteration-start # Note: special React Flow type
  draggable: false
  selectable: false
  zIndex: 1002
```

**Iteration outputs**:

- `item` — Current iteration item (available inside the loop)
- `index` — Current iteration index
- `output` — Collected output array (available after iteration completes)

---

### 4.15 `loop` — Loop Node (Container)

Repeats execution until break conditions are met.

```yaml
data:
  type: loop
  title: Loop
  start_node_id: loop_node_start
  loop_count: 10              # Maximum iterations
  logical_operator: and       # "and" | "or" for break conditions
  break_conditions:
  - variable_selector:
    - loop_node
    - num
    comparison_operator: "≥"
    value: "5"
    id: "uuid"
    varType: number
  loop_variables:             # Variables scoped to the loop
  - label: num
    var_type: number
    value_type: constant      # "constant" | "variable"
    value: "1"
    id: "uuid"
  outputs: {}                 # Output mapping
  height: 206
  width: 508
```

The loop container must contain a `loop-start` child node:

```yaml
- data:
    type: loop-start
    title: ""
    isInLoop: true
  id: loop_node_start
  parentId: loop_node
  type: custom-loop-start
  draggable: false
  selectable: false
  zIndex: 1002
```

---

### 4.16 `parameter-extractor` — Parameter Extractor Node

Uses an LLM to extract structured parameters from text.

```yaml
data:
  type: parameter-extractor
  title: Parameter Extractor
  model:
    provider: openai
    name: gpt-4
    mode: chat
    completion_params:
      temperature: 0.3
  query:                      # Input variable selector
  - start_node
  - query
  parameters:
  - name: city
    type: string
    description: "The city name"
    required: true
    options: null             # Enum options (optional)
  - name: date
    type: string
    description: "The date"
    required: false
  instruction: "Extract the city and date from the user's travel query."
  reasoning_mode: function_call  # "function_call" | "prompt"
  memory: null
  vision:
    enabled: false
```

**Parameter types**: `string`, `number`, `boolean`, `array[string]`, `array[number]`, `array[object]`, `array[boolean]`

**Outputs**: Each parameter name becomes an output variable, plus `__is_success` (boolean) and `__reason` (string).

---

### 4.17 `document-extractor` — Document Extractor Node

Extracts text from uploaded documents.

```yaml
data:
  type: document-extractor
  title: Document Extractor
  variable_selector:
  - start_node
  - files
```

**Output**: `text` (string)

---

### 4.18 `list-operator` — List Filter/Sort Node

Filters, sorts, limits, and extracts from arrays.

```yaml
data:
  type: list-operator
  title: List Operator
  variable:
  - node_id
  - array_var
  filter_by:
    enabled: true
    conditions:
    - key: ""
      comparison_operator: contains
      value: "search_term"
  order_by:
    enabled: true
    key: ""
    value: asc                # "asc" | "desc"
  limit:
    enabled: true
    size: 10
  extract_by:
    enabled: false
    serial: "1"
```

---

### 4.19 `human-input` — Human Input Node

Pauses workflow execution and requests human input via a form.

```yaml
data:
  type: human-input
  title: Human Input
  # (Complex configuration — see dify_graph/nodes/human_input/entities.py)
```

---

### 4.20 `agent` — Agent Node

Autonomous agent with tool-use capabilities.

```yaml
data:
  type: agent
  title: Agent
  # (Complex configuration — model, tools, agent parameters)
```

---

## 5. Graph: Edges

Each edge connects two nodes:

```yaml
- id: "edge-unique-id"       # Unique edge ID
  source: "source_node_id"   # Source node ID
  target: "target_node_id"   # Target node ID
  sourceHandle: source        # Source output handle (see below)
  targetHandle: target        # Target input handle (always "target")
  type: custom                # Always "custom"
  zIndex: 0                  # Optional z-index
  data:                      # Optional metadata
    sourceType: start         # Source node type
    targetType: llm           # Target node type
    isInIteration: false
    isInLoop: false
    iteration_id: "iter_node" # If edge is inside iteration
    loop_id: "loop_node"      # If edge is inside loop
```

### sourceHandle Values

| Source Node Type | sourceHandle | Meaning |
| ----------------- | ------------- | --------- |
| Most nodes | `source` | Default output |
| `if-else` | `"true"` / case_id | Matched case branch |
| `if-else` | `"false"` | Default/else branch |
| `question-classifier` | `"class_1"` etc. | Classification result |
| Error strategy | `"fail-branch"` | Error/failure path |
| Error strategy | `"success-branch"` | Success path |

---

## 6. Variable Reference System

### Variable Selectors

Variables are referenced as arrays of strings forming a path:

```yaml
value_selector:
- node_id          # The node that produces the variable
- variable_name    # The variable/output name from that node
```

### Template String References

In text fields (like `answer`, `prompt_template.text`, `url`), variables are referenced with the syntax:

```yaml
{{#node_id.variable_name#}}
```

### System Variables

System variables use `sys` as the node ID:

| Selector | Description |
| ---------- | ------------- |
| `["sys", "query"]` | User's input query |
| `["sys", "files"]` | Uploaded files |
| `["sys", "conversation_id"]` | Conversation ID |
| `["sys", "user_id"]` | User ID |
| `["sys", "dialogue_count"]` | Dialogue count |
| `["sys", "app_id"]` | App ID |
| `["sys", "workflow_id"]` | Workflow ID |
| `["sys", "workflow_run_id"]` | Current run ID |

### Conversation Variables

Referenced with `conversation` as the node ID:

```yaml
value_selector:
- conversation
- variable_name
```

Template: `{{#conversation.variable_name#}}`

### Common Node Outputs

| Node Type | Output Variables |
| ----------- | ----------------- |
| `start` | User-defined variable names |
| `llm` | `text`, `reasoning_content`, `usage` |
| `code` | User-defined output keys |
| `http-request` | `status_code`, `body`, `headers`, `files` |
| `tool` | `text`, `files`, `json` (varies by tool) |
| `template-transform` | `output` |
| `knowledge-retrieval` | `result` |
| `parameter-extractor` | User-defined parameter names + `__is_success`, `__reason` |
| `iteration` | `item` (inside), `index` (inside), `output` (after) |
| `loop` | Loop variable names |
| `variable-aggregator` | `output` or `GroupName.output` |
| `document-extractor` | `text` |

---

## 7. Features Configuration

```yaml
features:
  file_upload:
    enabled: false
    allowed_file_types:       # ["image", "document", "audio", "video", "custom"]
    - image
    allowed_file_extensions:  # [".JPG", ".PNG", ...]
    - .JPG
    - .PNG
    allowed_file_upload_methods:
    - local_file
    - remote_url
    number_limits: 3
    fileUploadConfig:         # Upload size limits
      file_size_limit: 15
      image_file_size_limit: 10
      audio_file_size_limit: 50
      video_file_size_limit: 100
      batch_count_limit: 5
      workflow_file_upload_limit: 10
    image:                    # Legacy image config
      enabled: false
      number_limits: 3
      transfer_methods:
      - local_file
      - remote_url
  opening_statement: ""       # Welcome message for chat
  suggested_questions: []     # Suggested conversation starters
  suggested_questions_after_answer:
    enabled: false
  speech_to_text:
    enabled: false
  text_to_speech:
    enabled: false
    language: ""
    voice: ""
  retriever_resource:
    enabled: false            # Show retrieved sources to user
  sensitive_word_avoidance:
    enabled: false
```

---

## 8. Environment and Conversation Variables

### 8.1. Environment Variables

Workflow-scoped variables (like API keys, secrets). Persist across runs.

```yaml
environment_variables:
- id: "uuid"
  name: api_key
  value: "sk-..."            # Encrypted on export, empty if not include_secret
  value_type: secret          # "string" | "number" | "secret"
  description: "API key"
  selector:
  - environment
  - api_key
```

### 8.2. Conversation Variables

Persist across turns within a conversation (advanced-chat only).

```yaml
conversation_variables:
- id: "uuid"
  name: history_summary
  value: ""                   # Default/initial value
  value_type: string          # "string" | "number" | "object" | "array[string]" | etc.
  description: ""
  selector:
  - conversation
  - history_summary
```

---

## 9. Error Handling

Nodes can define error strategies:

```yaml
data:
  type: llm
  error_strategy: fail-branch   # "fail-branch" | "default-value" | null
  default_value:                 # Used with "default-value" strategy
  - key: text
    type: string
    value: "Error occurred"
  retry_config:
    retry_enabled: true
    max_retries: 3
    retry_interval: 1000          # Milliseconds
```

When `error_strategy` is `fail-branch`, the node gets two additional sourceHandles:

- `success-branch` — Normal execution path
- `fail-branch` — Error execution path

---

## 10. Dependencies

Plugin/model dependencies for portability:

```yaml
dependencies:
- type: plugin                # Dependency type
  value:
    organization: langgenius
    plugin: openai
    version: "1.0.0"
```

---

## 11. Complete Minimal Workflow Example

```yaml
version: "0.6.0"
kind: app
app:
  name: Simple Echo
  mode: workflow
  icon: "🤖"
  icon_type: emoji
  icon_background: "#FFEAD5"
  description: "Echoes the input back"
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
    edges:
    - id: start-to-end
      source: start_node
      sourceHandle: source
      target: end_node
      targetHandle: target
      type: custom
    nodes:
    - data:
        type: start
        title: Start
        variables:
        - variable: query
          label: query
          type: text-input
          required: true
          max_length: null
          options: []
      id: start_node
      position:
        x: 80
        y: 282
      type: custom
    - data:
        type: end
        title: End
        outputs:
        - variable: result
          value_type: string
          value_selector:
          - start_node
          - query
      id: end_node
      position:
        x: 380
        y: 282
      type: custom
    viewport:
      x: 0
      y: 0
      zoom: 1
```

---

## 12. Complete LLM Chatflow Example

```yaml
version: "0.6.0"
kind: app
app:
  name: Simple Chatbot
  mode: advanced-chat
  icon: "🤖"
  icon_type: emoji
  icon_background: "#FFEAD5"
  description: "Simple LLM chatflow"
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
    edges:
    - id: start-to-llm
      source: start_node
      sourceHandle: source
      target: llm_node
      targetHandle: target
      type: custom
    - id: llm-to-answer
      source: llm_node
      sourceHandle: source
      target: answer_node
      targetHandle: target
      type: custom
    nodes:
    - data:
        type: start
        title: Start
        variables: []
      id: start_node
      position:
        x: 80
        y: 282
      type: custom
    - data:
        type: llm
        title: LLM
        model:
          provider: openai
          name: gpt-4
          mode: chat
          completion_params:
            temperature: 0.7
        prompt_template:
        - role: system
          text: "You are a helpful assistant."
        - role: user
          text: "{{#sys.query#}}"
        context:
          enabled: false
          variable_selector: []
        memory:
          window:
            enabled: true
            size: 50
        vision:
          enabled: false
      id: llm_node
      position:
        x: 380
        y: 282
      type: custom
    - data:
        type: answer
        title: Answer
        answer: "{{#llm_node.text#}}"
      id: answer_node
      position:
        x: 680
        y: 282
      type: custom
    viewport:
      x: 0
      y: 0
      zoom: 1
```

---

## 13. Key Source Files Reference

| File | Purpose |
| ------ | --------- |
| `api/services/app_dsl_service.py` | DSL import/export, YAML serialization |
| `api/models/workflow.py` | Workflow ORM model, `to_dict()`, `graph_dict` |
| `api/dify_graph/enums.py` | `BuiltinNodeTypes`, `ErrorStrategy`, `SystemVariableKey` |
| `api/dify_graph/entities/base_node_data.py` | `BaseNodeData` — shared fields for all nodes |
| `api/dify_graph/graph/edge.py` | `Edge` dataclass (tail, head, source_handle) |
| `api/dify_graph/graph/graph.py` | Graph construction from edge/node configs |
| `api/dify_graph/nodes/*/entities.py` | Per-node-type data entities |
| `api/dify_graph/variables/` | Variable types, SegmentType enum |
| `api/tests/fixtures/workflow/*.yml` | Example DSL YAML fixtures |
