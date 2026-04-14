#!/usr/bin/env python3
"""Dify Workflow DSL v0.6.0 Validator.

Validates a Dify DSL YAML file against the specification.
Reports errors, warnings, and a compliance summary.

Usage:
    python3 validate_dify_dsl.py <file.yaml> [--strict] [--json]
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


VALID_APP_MODES = {"workflow", "advanced-chat", "chat", "completion", "agent-chat"}
WORKFLOW_MODES = {"workflow", "advanced-chat"}

VALID_NODE_TYPES = {
    "start", "end", "answer", "llm", "code", "if-else", "http-request",
    "tool", "template-transform", "question-classifier", "knowledge-retrieval",
    "variable-aggregator", "variable-assigner", "assigner", "iteration",
    "iteration-start", "loop", "loop-start", "parameter-extractor",
    "document-extractor", "list-operator", "human-input", "agent",
}

VALID_VARIABLE_TYPES = {
    "text-input", "paragraph", "number", "select", "file", "file-list",
    "checkbox", "json_object", "secret-input",
}

VALID_OUTPUT_TYPES = {
    "string", "number", "integer", "boolean", "object", "file",
    "array", "array[string]", "array[number]", "array[object]",
    "array[boolean]", "array[file]", "any", "array[any]",
}

VALID_CODE_LANGUAGES = {"python3", "javascript"}

VALID_PROMPT_ROLES = {"system", "user", "assistant"}

VALID_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

VALID_COMPARISON_OPS = {
    "contains", "not contains", "start with", "end with", "is", "is not",
    "empty", "not empty", "in", "not in", "all of",
    "=", "≠", ">", "<", "≥", "≤",
    "null", "not null", "exists", "not exists",
}

# Template variable reference pattern: {{#node_id.variable_name#}}
VAR_REF_PATTERN = re.compile(r"\{\{#([^.#]+)\.([^#]+)#\}\}")


class ValidationResult:
    """Collects errors and warnings during validation."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def note(self, msg: str):
        self.info.append(msg)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> dict:
        return {
            "passed": self.passed,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "info": len(self.info),
        }

    def print_report(self):
        if self.errors:
            print(f"\n{'='*60}")
            print(f"ERRORS ({len(self.errors)}):")
            print(f"{'='*60}")
            for e in self.errors:
                print(f"  [ERROR] {e}")

        if self.warnings:
            print(f"\n{'='*60}")
            print(f"WARNINGS ({len(self.warnings)}):")
            print(f"{'='*60}")
            for w in self.warnings:
                print(f"  [WARN]  {w}")

        if self.info:
            print(f"\n{'='*60}")
            print(f"INFO ({len(self.info)}):")
            print(f"{'='*60}")
            for i in self.info:
                print(f"  [INFO]  {i}")

        print(f"\n{'='*60}")
        status = "PASSED" if self.passed else "FAILED"
        print(f"RESULT: {status} — {len(self.errors)} errors, "
              f"{len(self.warnings)} warnings")
        print(f"{'='*60}")

    def to_json(self) -> str:
        return json.dumps({
            **self.summary(),
            "error_messages": self.errors,
            "warning_messages": self.warnings,
            "info_messages": self.info,
        }, indent=2)


def validate_top_level(dsl: dict, result: ValidationResult):
    """Check top-level structure."""
    version = dsl.get("version")
    if version is None:
        result.error("Missing required top-level key: 'version'")
    elif str(version) != "0.6.0":
        result.warn(f"Version is '{version}', expected '0.6.0'")

    kind = dsl.get("kind")
    if kind is None:
        result.error("Missing required top-level key: 'kind'")
    elif kind != "app":
        result.error(f"'kind' must be 'app', got '{kind}'")

    app = dsl.get("app")
    if app is None:
        result.error("Missing required top-level key: 'app'")
    elif not isinstance(app, dict):
        result.error("'app' must be a mapping")
    else:
        mode = app.get("mode")
        if mode is None:
            result.error("Missing 'app.mode'")
        elif mode not in VALID_APP_MODES:
            result.error(f"Invalid app.mode '{mode}'. Valid: {VALID_APP_MODES}")
        if not app.get("name"):
            result.warn("'app.name' is empty or missing")

    if "dependencies" not in dsl:
        result.warn("Missing 'dependencies' key (should be [] if no deps)")

    return app


def validate_workflow_structure(dsl: dict, app: dict, result: ValidationResult):
    """Check workflow key and graph structure."""
    mode = app.get("mode", "")
    if mode not in WORKFLOW_MODES:
        result.note(f"App mode '{mode}' does not use workflow key — skipping workflow validation")
        return None, None, None

    workflow = dsl.get("workflow")
    if workflow is None:
        result.error(f"Mode '{mode}' requires 'workflow' key")
        return None, None, None
    if not isinstance(workflow, dict):
        result.error("'workflow' must be a mapping")
        return None, None, None

    graph = workflow.get("graph")
    if graph is None:
        result.error("Missing 'workflow.graph'")
        return workflow, None, None
    if not isinstance(graph, dict):
        result.error("'workflow.graph' must be a mapping")
        return workflow, None, None

    nodes = graph.get("nodes")
    edges = graph.get("edges")

    if nodes is None:
        result.error("Missing 'workflow.graph.nodes'")
    elif not isinstance(nodes, list):
        result.error("'workflow.graph.nodes' must be an array")
        nodes = None
    elif len(nodes) == 0:
        result.error("'workflow.graph.nodes' is empty — need at least start + terminal node")

    if edges is None:
        result.warn("Missing 'workflow.graph.edges' (may be valid for single-node workflows)")
        edges = []
    elif not isinstance(edges, list):
        result.error("'workflow.graph.edges' must be an array")
        edges = []

    if "features" not in workflow:
        result.warn("Missing 'workflow.features'")

    return workflow, nodes, edges


def validate_nodes(nodes: list, mode: str, result: ValidationResult, strict: bool = False):
    """Validate individual nodes and collect node map."""
    node_map = {}  # id -> node data type
    node_ids = set()
    start_count = 0
    end_count = 0
    answer_count = 0

    # Pre-pass: collect all node IDs so cross-references resolve in any order
    for node in nodes:
        if isinstance(node, dict) and node.get("id"):
            node_ids.add(node["id"])

    seen_ids = set()
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            result.error(f"Node at index {i} is not a mapping")
            continue

        node_id = node.get("id")
        if not node_id:
            result.error(f"Node at index {i} missing 'id'")
            continue

        if node_id in seen_ids:
            result.error(f"Duplicate node ID: '{node_id}'")
        seen_ids.add(node_id)

        data = node.get("data")
        if not isinstance(data, dict):
            result.error(f"Node '{node_id}': missing or invalid 'data'")
            continue

        node_type = data.get("type")
        if not node_type:
            result.error(f"Node '{node_id}': missing 'data.type'")
            continue

        if node_type not in VALID_NODE_TYPES:
            result.warn(f"Node '{node_id}': unknown node type '{node_type}'")

        node_map[node_id] = node_type

        # Check React Flow node type
        rf_type = node.get("type")
        if node_type in ("iteration-start",) and rf_type != "custom-iteration-start":
            result.warn(f"Node '{node_id}': iteration-start should have type 'custom-iteration-start'")
        elif node_type in ("loop-start",) and rf_type != "custom-loop-start":
            result.warn(f"Node '{node_id}': loop-start should have type 'custom-loop-start'")
        elif node_type not in ("iteration-start", "loop-start") and rf_type != "custom":
            if rf_type is not None:
                result.warn(f"Node '{node_id}': expected type 'custom', got '{rf_type}'")

        # Type-specific validation
        if node_type == "start":
            start_count += 1
            _validate_start_node(node_id, data, result)
        elif node_type == "end":
            end_count += 1
            _validate_end_node(node_id, data, result)
        elif node_type == "answer":
            answer_count += 1
            _validate_answer_node(node_id, data, node_map, result)
        elif node_type == "llm":
            _validate_llm_node(node_id, data, result)
        elif node_type == "code":
            _validate_code_node(node_id, data, result)
        elif node_type == "if-else":
            _validate_if_else_node(node_id, data, result)
        elif node_type == "http-request":
            _validate_http_node(node_id, data, result, strict)
        elif node_type == "iteration":
            _validate_iteration_node(node_id, data, node_ids, nodes, result)
        elif node_type == "loop":
            _validate_loop_node(node_id, data, node_ids, result)
        elif node_type == "knowledge-retrieval":
            _validate_knowledge_retrieval_node(node_id, data, result)
        elif node_type == "question-classifier":
            _validate_question_classifier_node(node_id, data, result)
        elif node_type == "parameter-extractor":
            _validate_parameter_extractor_node(node_id, data, result)
        elif node_type == "variable-aggregator":
            _validate_variable_aggregator_node(node_id, data, result)
        elif node_type == "template-transform":
            _validate_template_transform_node(node_id, data, result)
        elif node_type == "list-operator":
            _validate_list_operator_node(node_id, data, result)
        elif node_type == "agent":
            _validate_agent_node(node_id, data, result)

    # Global checks
    if start_count == 0:
        result.error("No 'start' node found")
    elif start_count > 1:
        result.error(f"Multiple start nodes found ({start_count}), expected exactly 1")

    if mode == "workflow":
        if end_count == 0:
            result.error("Workflow mode requires at least one 'end' node")
        if answer_count > 0:
            result.warn("Workflow mode should not have 'answer' nodes (use 'end' instead)")
    elif mode == "advanced-chat":
        if answer_count == 0:
            result.error("Advanced-chat mode requires at least one 'answer' node")
        if end_count > 0:
            result.warn("Advanced-chat mode should not have 'end' nodes (use 'answer' instead)")

    return node_map


def _validate_start_node(node_id: str, data: dict, result: ValidationResult):
    variables = data.get("variables", [])
    if not isinstance(variables, list):
        result.error(f"Node '{node_id}': 'variables' must be an array")
        return
    for v in variables:
        if not isinstance(v, dict):
            continue
        vname = v.get("variable")
        if not vname:
            result.error(f"Node '{node_id}': start variable missing 'variable' name")
        vtype = v.get("type")
        if vtype and vtype not in VALID_VARIABLE_TYPES:
            result.warn(f"Node '{node_id}': variable '{vname}' has unknown type '{vtype}'")
        if vtype == "select" and not v.get("options"):
            result.error(f"Node '{node_id}': select variable '{vname}' has empty options")


def _validate_end_node(node_id: str, data: dict, result: ValidationResult):
    outputs = data.get("outputs", [])
    if not isinstance(outputs, list):
        result.error(f"Node '{node_id}': 'outputs' must be an array")
        return
    for o in outputs:
        if not isinstance(o, dict):
            continue
        if not o.get("variable"):
            result.error(f"Node '{node_id}': end output missing 'variable' name")
        vtype = o.get("value_type")
        if vtype and vtype not in VALID_OUTPUT_TYPES:
            result.warn(f"Node '{node_id}': output type '{vtype}' not in known types")
        if not o.get("value_selector"):
            result.error(f"Node '{node_id}': end output '{o.get('variable', '?')}' missing 'value_selector'")


def _validate_answer_node(node_id: str, data: dict, node_map: dict, result: ValidationResult):
    answer = data.get("answer")
    if not answer:
        result.error(f"Node '{node_id}': answer node missing 'answer' template")
        return
    refs = VAR_REF_PATTERN.findall(answer)
    if not refs:
        result.warn(f"Node '{node_id}': answer template has no variable references")


def _validate_llm_node(node_id: str, data: dict, result: ValidationResult):
    model = data.get("model")
    if not isinstance(model, dict):
        result.error(f"Node '{node_id}': LLM node missing 'model' config")
    else:
        if not model.get("provider"):
            result.error(f"Node '{node_id}': LLM model missing 'provider'")
        if not model.get("name"):
            result.error(f"Node '{node_id}': LLM model missing 'name'")

    prompt = data.get("prompt_template")
    if isinstance(prompt, list):
        roles_found = {m.get("role") for m in prompt if isinstance(m, dict)}
        for m in prompt:
            if isinstance(m, dict):
                role = m.get("role")
                if role and role not in VALID_PROMPT_ROLES:
                    result.error(f"Node '{node_id}': invalid prompt role '{role}'")
        if "user" not in roles_found:
            result.warn(f"Node '{node_id}': LLM prompt has no 'user' message")
    elif prompt is not None:
        result.warn(f"Node '{node_id}': 'prompt_template' should be an array for chat mode")


def _validate_code_node(node_id: str, data: dict, result: ValidationResult):
    lang = data.get("code_language")
    if lang and lang not in VALID_CODE_LANGUAGES:
        result.error(f"Node '{node_id}': invalid code_language '{lang}'")
    if not data.get("code"):
        result.error(f"Node '{node_id}': code node has empty 'code' field")
    outputs = data.get("outputs")
    if not isinstance(outputs, dict) or len(outputs) == 0:
        result.warn(f"Node '{node_id}': code node has no declared outputs")


def _validate_if_else_node(node_id: str, data: dict, result: ValidationResult):
    cases = data.get("cases", [])
    if not isinstance(cases, list) or len(cases) == 0:
        result.error(f"Node '{node_id}': if-else node has no cases")
        return
    for case in cases:
        if not isinstance(case, dict):
            continue
        conditions = case.get("conditions", [])
        if not isinstance(conditions, list) or len(conditions) == 0:
            result.warn(f"Node '{node_id}': case '{case.get('case_id', '?')}' has no conditions")
        for cond in conditions:
            if isinstance(cond, dict):
                op = cond.get("comparison_operator")
                if op and op not in VALID_COMPARISON_OPS:
                    result.warn(f"Node '{node_id}': unknown comparison operator '{op}'")


def _validate_http_node(node_id: str, data: dict, result: ValidationResult, strict: bool):
    method = data.get("method")
    if method and method not in VALID_HTTP_METHODS:
        result.error(f"Node '{node_id}': invalid HTTP method '{method}'")
    url = data.get("url", "")
    if not url:
        result.error(f"Node '{node_id}': HTTP node missing 'url'")
    elif strict:
        # Check for hardcoded API keys in URL
        if re.search(r"(api_key|apikey|token|secret|password)=[^{]", url, re.IGNORECASE):
            result.error(f"Node '{node_id}': possible hardcoded secret in URL")


def _validate_iteration_node(node_id: str, data: dict, all_ids: set, all_nodes: list, result: ValidationResult):
    start_id = data.get("start_node_id")
    if not start_id:
        result.error(f"Node '{node_id}': iteration missing 'start_node_id'")
    elif start_id not in all_ids:
        result.error(f"Node '{node_id}': iteration start node '{start_id}' not found")
    iterator_sel = data.get("iterator_selector")
    if iterator_sel is None or (isinstance(iterator_sel, list) and len(iterator_sel) == 0):
        result.error(f"Node '{node_id}': iteration has empty 'iterator_selector' — no input array to iterate")
    output_sel = data.get("output_selector")
    if output_sel is None or (isinstance(output_sel, list) and len(output_sel) == 0):
        result.warn(f"Node '{node_id}': iteration has empty 'output_selector' — no collected output")


def _validate_loop_node(node_id: str, data: dict, all_ids: set, result: ValidationResult):
    """Validate loop container node."""
    start_id = data.get("start_node_id")
    if not start_id:
        result.error(f"Node '{node_id}': loop missing 'start_node_id'")
    elif start_id not in all_ids:
        result.error(f"Node '{node_id}': loop start node '{start_id}' not found")
    break_conditions = data.get("break_conditions")
    if break_conditions is None:
        result.warn(f"Node '{node_id}': loop missing 'break_conditions' — may loop forever")
    elif isinstance(break_conditions, list) and len(break_conditions) == 0:
        result.warn(f"Node '{node_id}': loop has empty 'break_conditions' — will loop forever unless output has exit logic")
    max_count = data.get("max_count") or data.get("loop_count")
    if not max_count:
        result.warn(f"Node '{node_id}': loop has no 'max_count' limit — risk of infinite loop at runtime")


def _validate_knowledge_retrieval_node(node_id: str, data: dict, result: ValidationResult):
    """Validate knowledge-retrieval node."""
    datasets = data.get("dataset_configs") or data.get("datasets") or []
    if not datasets:
        result.warn(f"Node '{node_id}': knowledge-retrieval has no datasets configured")
    query_var = data.get("query_variable_selector")
    if not query_var:
        result.error(f"Node '{node_id}': knowledge-retrieval missing 'query_variable_selector'")
    retrieval_mode = data.get("retrieval_mode", "")
    valid_modes = {"single", "multiple", "hybrid"}
    if retrieval_mode and retrieval_mode not in valid_modes:
        result.warn(f"Node '{node_id}': unexpected retrieval_mode '{retrieval_mode}', expected one of {valid_modes}")


def _validate_question_classifier_node(node_id: str, data: dict, result: ValidationResult):
    """Validate question-classifier node."""
    classes = data.get("classes", [])
    if not isinstance(classes, list) or len(classes) == 0:
        result.error(f"Node '{node_id}': question-classifier has no classes")
    else:
        class_ids = set()
        for cls in classes:
            if isinstance(cls, dict):
                cid = cls.get("id")
                if not cid:
                    result.error(f"Node '{node_id}': classifier class missing 'id'")
                elif cid in class_ids:
                    result.error(f"Node '{node_id}': duplicate classifier class id '{cid}'")
                class_ids.add(cid)
                if not cls.get("name"):
                    result.warn(f"Node '{node_id}': classifier class '{cid}' has no 'name'")
    model = data.get("model")
    if not isinstance(model, dict):
        result.error(f"Node '{node_id}': question-classifier missing 'model' config")
    instruction = data.get("instruction")
    if not instruction:
        result.warn(f"Node '{node_id}': question-classifier has no 'instruction' — classification may be imprecise")


def _validate_parameter_extractor_node(node_id: str, data: dict, result: ValidationResult):
    """Validate parameter-extractor node."""
    parameters = data.get("parameters", [])
    if not isinstance(parameters, list) or len(parameters) == 0:
        result.error(f"Node '{node_id}': parameter-extractor has no parameters defined")
    else:
        for p in parameters:
            if isinstance(p, dict):
                if not p.get("name"):
                    result.error(f"Node '{node_id}': parameter missing 'name'")
                if not p.get("type"):
                    result.warn(f"Node '{node_id}': parameter '{p.get('name', '?')}' missing 'type'")
    model = data.get("model")
    if not isinstance(model, dict):
        result.error(f"Node '{node_id}': parameter-extractor missing 'model' config")
    query_var = data.get("query_variable_selector")
    if not query_var:
        result.error(f"Node '{node_id}': parameter-extractor missing 'query_variable_selector'")
    reasoning_mode = data.get("reasoning_mode", "")
    valid_reasoning = {"prompt", "function_call", ""}
    if reasoning_mode and reasoning_mode not in valid_reasoning:
        result.warn(f"Node '{node_id}': unexpected reasoning_mode '{reasoning_mode}'")


def _validate_variable_aggregator_node(node_id: str, data: dict, result: ValidationResult):
    """Validate variable-aggregator node."""
    variables = data.get("variables", [])
    if not isinstance(variables, list) or len(variables) == 0:
        result.warn(f"Node '{node_id}': variable-aggregator has no input variables — output will always be empty")
    output_type = data.get("output_type", "")
    valid_output_types = {"string", "number", "integer", "boolean", "object", "array[string]", ""}
    if output_type and output_type not in valid_output_types:
        result.warn(f"Node '{node_id}': variable-aggregator unexpected output_type '{output_type}'")


def _validate_template_transform_node(node_id: str, data: dict, result: ValidationResult):
    """Validate template-transform node."""
    template = data.get("template")
    if not template:
        result.error(f"Node '{node_id}': template-transform missing 'template'")
    variables = data.get("variables", [])
    if not isinstance(variables, list) or len(variables) == 0:
        result.warn(f"Node '{node_id}': template-transform has no input variables defined")


def _validate_list_operator_node(node_id: str, data: dict, result: ValidationResult):
    """Validate list-operator node."""
    input_var = data.get("variable")
    if not input_var:
        result.error(f"Node '{node_id}': list-operator missing 'variable' (input list selector)")
    operations = data.get("filter_by") or data.get("order_by") or data.get("extract_by") or data.get("limit")
    if not operations:
        result.warn(f"Node '{node_id}': list-operator has no filter/order/extract/limit configured")


def _validate_agent_node(node_id: str, data: dict, result: ValidationResult):
    """Validate agent node."""
    model = data.get("model")
    if not isinstance(model, dict):
        result.error(f"Node '{node_id}': agent node missing 'model' config")
    tools = data.get("tools", [])
    if not isinstance(tools, list) or len(tools) == 0:
        result.warn(f"Node '{node_id}': agent node has no tools — may behave as plain LLM")
    prompt = data.get("prompt_template") or data.get("system_prompt")
    if not prompt:
        result.warn(f"Node '{node_id}': agent node has no system prompt defined")
    agent_mode = data.get("agent_mode", {})
    if isinstance(agent_mode, dict):
        strategy = agent_mode.get("strategy", "")
        valid_strategies = {"react", "function-call", "tool-call", ""}
        if strategy and strategy not in valid_strategies:
            result.warn(f"Node '{node_id}': unknown agent strategy '{strategy}'")


def validate_edges(edges: list, node_map: dict, result: ValidationResult, nodes: list | None = None):
    """Validate edge completeness and correctness."""
    edge_ids = set()
    targets_reached = set()  # nodes that have at least one incoming edge
    sources_with_output = set()  # nodes that have at least one outgoing edge

    # Build a set of "inner" node IDs (nested inside iteration/loop containers)
    # so they are exempt from the outer-graph reachability check.
    inner_node_ids: set[str] = set()
    if nodes:
        for _n in nodes:
            if not isinstance(_n, dict):
                continue
            _data = _n.get("data", {})
            if not isinstance(_data, dict):
                continue
            if _data.get("isInIteration") or _data.get("isInLoop") or _n.get("parentId"):
                inner_node_ids.add(_n.get("id", ""))

    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            result.error(f"Edge at index {i} is not a mapping")
            continue

        eid = edge.get("id")
        if not eid:
            result.warn(f"Edge at index {i} missing 'id'")
        elif eid in edge_ids:
            result.error(f"Duplicate edge ID: '{eid}'")
        if eid:
            edge_ids.add(eid)

        source = edge.get("source")
        target = edge.get("target")

        if not source:
            result.error(f"Edge '{eid}': missing 'source'")
        elif source not in node_map:
            result.error(f"Edge '{eid}': source node '{source}' not found")
        else:
            sources_with_output.add(source)

        if not target:
            result.error(f"Edge '{eid}': missing 'target'")
        elif target not in node_map:
            result.error(f"Edge '{eid}': target node '{target}' not found")
        else:
            targets_reached.add(target)

        if edge.get("targetHandle") not in ("target", None):
            result.warn(f"Edge '{eid}': targetHandle should be 'target', got '{edge.get('targetHandle')}'")

        if edge.get("type") not in ("custom", None):
            result.warn(f"Edge '{eid}': type should be 'custom', got '{edge.get('type')}'")

        if not edge.get("sourceHandle"):
            result.warn(f"Edge '{eid}': missing 'sourceHandle'")

    # Reachability checks
    container_child_types = {"iteration-start", "loop-start"}
    for nid, ntype in node_map.items():
        if ntype in container_child_types:
            continue  # wired by their container node
        if ntype == "start":
            continue
        if nid in inner_node_ids:
            continue  # nested inside iteration/loop — not wired in outer graph
        if nid not in targets_reached:
            result.error(f"Node '{nid}' ({ntype}) is unreachable — no incoming edge")

    # question-classifier class branch completeness
    if nodes:
        # build source → set[sourceHandle] map from edges
        source_handle_map: dict[str, set] = {}
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            src = edge.get("source")
            sh = edge.get("sourceHandle")
            if src and sh:
                source_handle_map.setdefault(src, set()).add(sh)

        node_data_map = {n.get("id"): n.get("data", {}) for n in nodes if isinstance(n, dict)}
        for nid, ntype in node_map.items():
            if ntype != "question-classifier":
                continue
            nd = node_data_map.get(nid, {})
            classes = nd.get("classes", []) if isinstance(nd, dict) else []
            handled = source_handle_map.get(nid, set())
            for cls in classes:
                if isinstance(cls, dict):
                    cid = cls.get("id")
                    if cid and cid not in handled:
                        result.warn(
                            f"Node '{nid}' (question-classifier): class '{cid}' "
                            f"({cls.get('name', '?')}) has no outgoing edge"
                        )

    return edge_ids


def validate_container_inner_nodes(nodes: list, node_map: dict, result: ValidationResult):
    """Warn about nodes that declare isInIteration/isInLoop but have no parentId."""
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id", "?")
        data = node.get("data", {})
        if not isinstance(data, dict):
            continue
        in_iter = data.get("isInIteration", False)
        in_loop = data.get("isInLoop", False)
        has_parent = bool(node.get("parentId"))
        if (in_iter or in_loop) and not has_parent:
            result.warn(
                f"Node '{nid}' ({data.get('type', '?')}) declares "
                f"isInIteration/isInLoop but has no 'parentId' — "
                f"may be disconnected from its container"
            )


def validate_variable_references(nodes: list, node_map: dict, result: ValidationResult):
    """Check that variable references point to existing upstream nodes."""
    known_sources = set(node_map.keys())
    known_sources.add("sys")
    known_sources.add("conversation")
    known_sources.add("environment")

    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id", "?")
        data = node.get("data", {})
        if not isinstance(data, dict):
            continue

        # Check value_selector fields recursively
        _check_selectors_in_dict(nid, data, known_sources, result)

        # Check template string references
        _check_template_refs_in_dict(nid, data, known_sources, result)


def _check_selectors_in_dict(node_id: str, d: dict, known: set, result: ValidationResult):
    for key, val in d.items():
        if key == "value_selector" and isinstance(val, list) and len(val) >= 2:
            if isinstance(val[0], str) and val[0] not in known:
                result.warn(f"Node '{node_id}': value_selector references unknown node '{val[0]}'")
        elif key == "variables" and isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    vs = item.get("value_selector")
                    if isinstance(vs, list) and len(vs) >= 2:
                        if isinstance(vs[0], str) and vs[0] not in known:
                            result.warn(f"Node '{node_id}': variable selector references unknown node '{vs[0]}'")
        elif isinstance(val, dict):
            _check_selectors_in_dict(node_id, val, known, result)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    _check_selectors_in_dict(node_id, item, known, result)


def _check_template_refs_in_dict(node_id: str, d: dict, known: set, result: ValidationResult):
    for key, val in d.items():
        if isinstance(val, str):
            for ref_node, ref_var in VAR_REF_PATTERN.findall(val):
                if ref_node not in known:
                    result.warn(f"Node '{node_id}': template ref '{{{{#{ref_node}.{ref_var}#}}}}' "
                                f"references unknown node '{ref_node}'")
        elif isinstance(val, dict):
            _check_template_refs_in_dict(node_id, val, known, result)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    _check_template_refs_in_dict(node_id, item, known, result)
                elif isinstance(item, str):
                    for ref_node, ref_var in VAR_REF_PATTERN.findall(item):
                        if ref_node not in known:
                            result.warn(f"Node '{node_id}': template ref references unknown node '{ref_node}'")


def check_secrets(dsl: dict, result: ValidationResult):
    """Scan for hardcoded secrets."""
    yaml_str = yaml.dump(dsl, default_flow_style=False)
    secret_patterns = [
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI-style API key"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
        (r"ghs_[a-zA-Z0-9]{36}", "GitHub server token"),
        (r"xoxb-[0-9]+-[a-zA-Z0-9]+", "Slack bot token"),
        (r"Bearer\s+[a-zA-Z0-9._-]{40,}", "Bearer token"),
    ]
    for pattern, name in secret_patterns:
        if re.search(pattern, yaml_str):
            result.error(f"Possible hardcoded {name} detected in YAML")


def validate_dsl(filepath: str, strict: bool = False) -> ValidationResult:
    """Main validation entry point."""
    result = ValidationResult()

    # Parse YAML
    path = Path(filepath)
    if not path.exists():
        result.error(f"File not found: {filepath}")
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            dsl = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result.error(f"YAML parse error: {e}")
        return result

    if not isinstance(dsl, dict):
        result.error("Top-level YAML must be a mapping")
        return result

    result.note(f"Validating: {filepath}")

    # Top-level structure
    app = validate_top_level(dsl, result)
    if app is None:
        return result

    mode = app.get("mode", "")

    # Workflow structure
    workflow, nodes, edges = validate_workflow_structure(dsl, app, result)
    if nodes is None:
        return result

    # Node validation
    node_map = validate_nodes(nodes, mode, result, strict)

    # Edge validation
    if edges:
        validate_edges(edges, node_map, result, nodes)

    # Container inner-node consistency
    validate_container_inner_nodes(nodes, node_map, result)

    # Variable reference validation
    validate_variable_references(nodes, node_map, result)

    # Secret scanning
    check_secrets(dsl, result)

    # Summary info
    result.note(f"Mode: {mode}")
    result.note(f"Nodes: {len(nodes)}")
    result.note(f"Edges: {len(edges) if edges else 0}")
    result.note(f"Node types: {', '.join(sorted(set(node_map.values())))}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Validate a Dify Workflow DSL YAML file against the v0.6.0 specification."
    )
    parser.add_argument("file", nargs="?", help="Path to the DSL YAML file")
    parser.add_argument("--dir", metavar="DIRECTORY",
                        help="Validate all *.yaml / *.yml files in a directory (recursive)")
    parser.add_argument("--strict", action="store_true",
                        help="Enable strict mode (additional security checks)")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Output results as JSON")
    args = parser.parse_args()

    if args.dir:
        # Batch mode: validate all YAML files in directory
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"ERROR: '{args.dir}' is not a directory", file=sys.stderr)
            sys.exit(2)
        files = sorted(dir_path.rglob("*.yaml")) + sorted(dir_path.rglob("*.yml"))
        if not files:
            print(f"No YAML files found in '{args.dir}'")
            sys.exit(0)

        all_results: list[tuple[Path, ValidationResult]] = []
        for fp in files:
            r = validate_dsl(str(fp), strict=args.strict)
            all_results.append((fp, r))

        if args.json_output:
            import json as _json
            summary = [{"file": str(fp), **_json.loads(r.to_json())} for fp, r in all_results]
            print(_json.dumps(summary, indent=2))
        else:
            # Print compact summary table
            col_w = max(len(str(fp)) for fp, _ in all_results) + 2
            print(f"\n{'FILE':<{col_w}} ERRORS  WARNINGS  STATUS")
            print("-" * (col_w + 28))
            overall_ok = True
            for fp, r in all_results:
                status = "PASS" if r.passed else "FAIL"
                if not r.passed:
                    overall_ok = False
                print(f"{str(fp):<{col_w}} {len(r.errors):<7}  {len(r.warnings):<8}  {status}")
            print("-" * (col_w + 28))
            total_e = sum(len(r.errors) for _, r in all_results)
            total_w = sum(len(r.warnings) for _, r in all_results)
            print(f"{'TOTAL':<{col_w}} {total_e:<7}  {total_w:<8}  "
                  f"{'ALL PASS' if overall_ok else 'FAILURES'}")
            # Print details for failures
            for fp, r in all_results:
                if not r.passed:
                    print()
                    r.print_report()

        sys.exit(0 if all(r.passed for _, r in all_results) else 1)

    elif args.file:
        result = validate_dsl(args.file, strict=args.strict)

        if args.json_output:
            print(result.to_json())
        else:
            result.print_report()

        sys.exit(0 if result.passed else 1)

    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
