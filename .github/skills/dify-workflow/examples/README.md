# Dify Workflow DSL — Example Index

All examples are valid against the [DSL v0.6.0 specification](../references/dsl-specification.md)
and pass the automated validator (`scripts/validate_dify_dsl.py`).

Validate any example:
```bash
python3 scripts/validate_dify_dsl.py examples/<file>.yaml
```

---

## Examples

| File | Mode | Nodes | Complexity | Patterns Demonstrated |
|---|---|---|---|---|
| [minimal-echo.yaml](minimal-echo.yaml) | workflow | 2 | ★☆☆☆☆ | Bare minimum structure, start → end |
| [llm-chatflow.yaml](llm-chatflow.yaml) | advanced-chat | 3 | ★★☆☆☆ | LLM node, memory window, answer node |
| [conditional-routing.yaml](conditional-routing.yaml) | workflow | 6 | ★★★☆☆ | question-classifier, fan-out, variable-aggregator |
| [rag-pipeline.yaml](rag-pipeline.yaml) | workflow | 4 | ★★★☆☆ | knowledge-retrieval, context injection into LLM |
| [code-transform-chain.yaml](code-transform-chain.yaml) | workflow | 5 | ★★★☆☆ | code node, template-transform, LLM chain |
| [conversation-state.yaml](conversation-state.yaml) | advanced-chat | 6 | ★★★☆☆ | conversation variables, variable-assigner, question-classifier |
| [list-operator-filter.yaml](list-operator-filter.yaml) | workflow | 4 | ★★★☆☆ | list-operator (filter/sort/limit), code → list → LLM |
| [iteration-pipeline.yaml](iteration-pipeline.yaml) | workflow | 7 | ★★★★☆ | iteration container, iteration-start, parallel LLM |
| [self-check-loop.yaml](self-check-loop.yaml) | workflow | 6 | ★★★★☆ | loop node, loop-start, score-based break condition |
| [http-fan-out.yaml](http-fan-out.yaml) | workflow | 7 | ★★★★☆ | HTTP fan-out via iteration, `{{#item#}}`, parallel fetch |
| [agent-tool-pipeline.yaml](agent-tool-pipeline.yaml) | advanced-chat | 5 | ★★★★☆ | agent (ReAct), tool binding, error branch via if-else |
| [parameter-extractor.yaml](parameter-extractor.yaml) | workflow | 8 | ★★★★★ | LLM extraction, code validation, if-else routing, aggregation |

---

## Pattern Reference

### Sequential Pipeline
```
start → node_a → node_b → end
```
→ See: [code-transform-chain.yaml](code-transform-chain.yaml)

### Branch and Merge
```
start → classifier → branch_a ─┐
                  └─ branch_b ─┤
                               ↓ aggregator → end
```
→ See: [conditional-routing.yaml](conditional-routing.yaml), [parameter-extractor.yaml](parameter-extractor.yaml)

### LLM Extraction → Validate → Route
```
start → extractor (llm) → validator (code) → if-else → fulfillment
                                                     └─ clarification
```
→ See: [parameter-extractor.yaml](parameter-extractor.yaml)

### Iteration over Array
```
start → array_builder (code) → container (iteration)
                                    iteration-start → inner_node
                             → merge → end
```
→ See: [iteration-pipeline.yaml](iteration-pipeline.yaml), [http-fan-out.yaml](http-fan-out.yaml)

### Self-Correcting Loop
```
start → generator (llm) → loop
                              loop-start → scorer (code)
                                         → if-else (pass?) → loop exit
```
→ See: [self-check-loop.yaml](self-check-loop.yaml)

### RAG Pipeline
```
start → retrieval (knowledge-retrieval) → llm (context injected) → end
```
→ See: [rag-pipeline.yaml](rag-pipeline.yaml)

### Conversation State (multi-turn)
```
start → classifier → collect → assigner ─→ answer (info)
                 └─ qa-llm ──────────────→ answer (qa)
                conversation_variables ──→ (persisted across turns)
```
→ See: [conversation-state.yaml](conversation-state.yaml)

### List Filter and Rank
```
start → code (generate list) → list-operator (filter/sort/limit) → llm → end
```
→ See: [list-operator-filter.yaml](list-operator-filter.yaml)

### Agent with Error Guard
```
start → agent (ReAct + tools) → if-else (error?) → answer (success)
                                               └──→ answer (fallback)
```
→ See: [agent-tool-pipeline.yaml](agent-tool-pipeline.yaml)

---

## Node Type Coverage

| Node Type | Example |
|---|---|
| `start` | All |
| `end` | All workflow examples |
| `answer` | [llm-chatflow.yaml](llm-chatflow.yaml) |
| `llm` | All except minimal-echo |
| `code` | code-transform-chain, iteration-pipeline, self-check-loop, http-fan-out, parameter-extractor |
| `if-else` | parameter-extractor |
| `question-classifier` | conditional-routing |
| `variable-aggregator` | conditional-routing, parameter-extractor |
| `template-transform` | code-transform-chain |
| `knowledge-retrieval` | rag-pipeline |
| `http-request` | http-fan-out |
| `iteration` | iteration-pipeline, http-fan-out |
| `iteration-start` | iteration-pipeline, http-fan-out |
| `loop` | self-check-loop |
| `loop-start` | self-check-loop |
| `list-operator` | [list-operator-filter.yaml](list-operator-filter.yaml) |
| `variable-assigner` | [conversation-state.yaml](conversation-state.yaml) |
| `agent` | [agent-tool-pipeline.yaml](agent-tool-pipeline.yaml) |
| `parameter-extractor` | [parameter-extractor.yaml](parameter-extractor.yaml) |
