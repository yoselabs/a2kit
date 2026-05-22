## 1. Decision record

- [x] 1.1 Write an ADR recording the consumer-profile rendering
      decision (Nygard + YAML frontmatter): the `(value, consumer)`
      seam, the `code_mode` build-time regime split, dataclass
      marshalling, and the emit-both-channels call per MCP SEP-1624
- [x] 1.2 Link the ADR to `docs/SPIKE_CODEMODE_MARSHALLING.md` (F1–F7)

## 2. Rendering seam (consumer-aware-rendering)

- [x] 2.1 BDD: specs for `render(value, consumer)` across `llm` /
      `code` / `machine`
- [x] 2.2 Implement the `render` seam and the consumer-profile type
- [x] 2.3 BDD: specs for `build_encoding_plan`, including a flat-array
      field nested inside a larger object and a deeply nested
      non-tabular type
- [x] 2.4 Implement `build_encoding_plan` — recurse `BaseModel` fields,
      call the unchanged `infer_format_hint` per node, cache the plan
      on `ToolDescriptor`
- [x] 2.5 BDD: specs for single-pass encoding straight from typed
      objects (no normalize-then-encode double walk)
- [x] 2.6 Implement single-pass encoders; retire `_normalize_for_encoding`

## 3. MCP surface format routing

- [x] 3.1 BDD: specs — a tabular MCP tool emits TSV/page-tsv in
      `content` and equivalent JSON in `structuredContent`
- [x] 3.2 Implement the outermost MCP wrapper returning a
      `fastmcp.ToolResult`, applying the encoding plan
- [x] 3.3 BDD + impl: regime selection — `code_mode` picks the
      consumer for real tools at `build_mcp_server` time
- [x] 3.4 Update a2kit's existing MCP tests for the new `content` shape

## 4. Code-mode sandbox runtime (code-mode-sandbox-runtime)

- [x] 4.1 BDD: specs — `call_tool` results support attribute access;
      `page.items[0].title` on a nested `Page`
- [x] 4.2 Implement dict→dataclass marshalling driven by
      `ToolDescriptor.return_type`
- [x] 4.3 BDD: specs — stub generation (dataclass mirrors + one
      `Literal` overload of `call_tool` per tool)
- [x] 4.4 Implement stub generation from tool descriptors
- [x] 4.5 BDD: specs — type-check rejects a misnamed field, a wrong
      access pattern, and a hallucinated tool name; one retry on error
- [x] 4.6 Implement the a2kit `SandboxProvider` (generate stubs,
      `type_check=True`, one-retry loop), injected into `A2kitCodeMode`
- [x] 4.7 Author the `execute` description (output contract:
      bare-expression result, attribute access, encourage-flat) and
      override CodeMode's `execute_description`

## 5. `execute` output rendering

- [x] 5.1 BDD: specs — value-driven inference: flat list → TSV,
      nested → JSON, TSV-encode failure → JSON fallback
- [x] 5.2 Implement value-driven inference and render the `execute`
      output for the `llm` consumer

## 6. Eval fixture

- [x] 6.1 Promote `scripts/eval_codemode_correctness.py` into a
      permanent eval fixture under the existing eval system
- [x] 6.2 Expand coverage: real verbose `get_schema` output,
      multi-tool joins, error paths, a wider model panel

## 7. Release

- [x] 7.1 CHANGELOG BREAKING entry — MCP `content` shape change — with
      a migration note
- [x] 7.2 Add the `--compact` operator toggle for non-conformant MCP
      clients (drops `structuredContent`)
- [x] 7.3 Update `OPERATIONAL_CONTRACTS.md` and surface docs
- [x] 7.4 Full gate green: tests, coverage, ruff, ty, markdown, ADR
      index, `openspec validate --changes --strict`
