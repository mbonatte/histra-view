#!/usr/bin/env python3
"""Model Context Protocol (MCP) stdio server for authoring and configuring HiStrA .hrx files.

Run:
  .venv/bin/python mcp_server.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from hrx_cli import (
    create_bridge_hrx,
    edit_analysis_hrx,
    edit_material_hrx,
    get_catalog,
    inspect_hrx_bytes,
)

TOOLS = [
    {
        "name": "hrx_catalog",
        "description": (
            "Return the HiStrA .hrx builder catalog: default parametric bridge geometry, "
            "masonry material templates, analysis templates, Advanced mode masonry constitutive law "
            "schemas (Rocking, Shear, Sliding), and analysis enum values."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["all", "geometry", "materials", "analyses", "masonry-schema", "analysis-enums"],
                    "default": "all",
                    "description": "Which catalog section to return.",
                }
            },
        },
    },
    {
        "name": "hrx_create_bridge",
        "description": (
            "Generate a new parametric masonry arch bridge .hrx file from geometry parameters "
            "(spans, piers, abutments, deck strips, backfill elevation, mesh size nl) and write it to disk."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["output_path"],
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": "Path where the generated .hrx file will be written.",
                },
                "spec": {
                    "type": "object",
                    "description": (
                        "Optional bridge geometry dictionary overriding defaults "
                        "(name, nl, strips, spans, piers, left_abutment, right_abutment, elevation)."
                    ),
                },
                "overrides": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional dotted KEY=VALUE overrides, e.g. ['nl=150', 'spans.0.L=800', 'spans.0.circolare=true'].",
                },
            },
        },
    },
    {
        "name": "hrx_inspect",
        "description": (
            "Inspect an existing .hrx file and return structured JSON with model summary counts, "
            "Advanced mode masonry material properties (General, Rocking, Shear, Sliding), "
            "analysis definitions, and load combinations/functions/conditions."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["hrx_path"],
            "properties": {
                "hrx_path": {
                    "type": "string",
                    "description": "Path to the .hrx file to inspect.",
                },
                "section": {
                    "type": "string",
                    "enum": ["all", "summary", "materials", "analyses", "loads"],
                    "default": "all",
                    "description": "Which section of the model inspection to return.",
                },
            },
        },
    },
    {
        "name": "hrx_edit_material",
        "description": (
            "Add, duplicate, delete, or configure a masonry material in Advanced mode "
            "(General, Rocking, Shear, Sliding mechanisms and constitutive laws) inside an .hrx file."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["hrx_path"],
            "properties": {
                "hrx_path": {
                    "type": "string",
                    "description": "Input .hrx file path.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional output .hrx file path (defaults to updating hrx_path in-place).",
                },
                "add_template": {
                    "type": "string",
                    "description": "Template key to add a new masonry material (see hrx_catalog materials).",
                },
                "duplicate_key": {
                    "type": "string",
                    "description": "Existing material key to duplicate.",
                },
                "delete_key": {
                    "type": "string",
                    "description": "Existing unreferenced material key to delete.",
                },
                "key": {
                    "type": "string",
                    "description": "Target material key to edit.",
                },
                "name": {
                    "type": "string",
                    "description": "Target material name to edit (alternative to key).",
                },
                "sliding_law": {
                    "type": "string",
                    "enum": ["Elastic", "ElastoPlastic", "LinearSoftening"],
                    "description": "Convenience toggle for Direction 1 sliding law (sets scorrhor and SlidingFractureEnergy).",
                },
                "orthotropic_rocking": {
                    "type": "boolean",
                    "description": "Set rocking behavior (true = Orthotropic, false = Isotropic).",
                },
                "orthotropic_sliding": {
                    "type": "boolean",
                    "description": "Set sliding behavior (true = Orthotropic, false = Isotropic).",
                },
                "attributes": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "number", "boolean"]},
                    "description": (
                        "Advanced mode masonry attributes to set, e.g. "
                        "{'Name': 'Brick', 'Ehor': '1800', 'Gd': '600', 'FmHor': '3.2', 'FtmHor': '0.15', "
                        "'TensileCurveType': 'LinearSoftening', 'Gt': '0.02', 'ConstitutiveLawMasonryShear': 'ElastoPlasticDuctilityFixed'}."
                    ),
                },
            },
        },
    },
    {
        "name": "hrx_edit_analysis",
        "description": (
            "Add, duplicate, delete, or configure an analysis definition in an .hrx file."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["hrx_path"],
            "properties": {
                "hrx_path": {
                    "type": "string",
                    "description": "Input .hrx file path.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional output .hrx file path (defaults to updating hrx_path in-place).",
                },
                "add_template": {
                    "type": "string",
                    "description": "Analysis template name to add (e.g. 'LiveLoad_1', 'Modal_0'; see hrx_catalog analyses).",
                },
                "duplicate_key": {
                    "type": "string",
                    "description": "Existing analysis key to duplicate.",
                },
                "delete_key": {
                    "type": "string",
                    "description": "Existing unreferenced analysis key to delete.",
                },
                "key": {
                    "type": "string",
                    "description": "Target analysis key to edit.",
                },
                "name": {
                    "type": "string",
                    "description": "Target analysis name to edit (alternative to key).",
                },
                "node_path": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Optional child element index path for nested stage/dynamic settings (default [] = root <Analysis>).",
                },
                "attributes": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "number", "boolean"]},
                    "description": (
                        "Analysis attributes to set, e.g. "
                        "{'Name': 'LiveLoad_Custom', 'MaxIterations': '50', 'ConvergenceTolerance': '0.001', 'NumberOfEigenModes': '12'}."
                    ),
                },
            },
        },
    },
]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "hrx_catalog":
        cat = get_catalog()
        sec = arguments.get("section", "all")
        section_map = {
            "all": cat,
            "geometry": {"geometry_defaults": cat["geometry_defaults"], "geometry_fields": cat["geometry_fields"]},
            "materials": cat["masonry_material_templates"],
            "analyses": cat["analysis_templates"],
            "masonry-schema": cat["masonry_advanced_schema"],
            "analysis-enums": cat["analysis_enums"],
        }
        return section_map.get(sec, cat)

    if name == "hrx_create_bridge":
        out_path = Path(arguments["output_path"])
        hrx_bytes = create_bridge_hrx(
            spec=arguments.get("spec"),
            overrides=arguments.get("overrides"),
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(hrx_bytes)
        info = inspect_hrx_bytes(hrx_bytes, out_path.name, section="summary")
        return {"output": str(out_path), **info}

    if name == "hrx_inspect":
        hrx_path = Path(arguments["hrx_path"])
        sec = arguments.get("section", "all")
        return inspect_hrx_bytes(hrx_path.read_bytes(), hrx_path.name, section=sec)

    if name == "hrx_edit_material":
        in_path = Path(arguments["hrx_path"])
        out_path = Path(arguments.get("output_path") or in_path)
        raw_attrs = arguments.get("attributes") or {}
        str_attrs = {
            str(k): ("true" if v is True else "false" if v is False else str(v))
            for k, v in raw_attrs.items()
        }
        updated_bytes, summary = edit_material_hrx(
            in_path.read_bytes(),
            add_template=arguments.get("add_template"),
            duplicate_key=arguments.get("duplicate_key"),
            delete_key=arguments.get("delete_key"),
            key=arguments.get("key"),
            name=arguments.get("name"),
            attributes=str_attrs,
            sliding_law=arguments.get("sliding_law"),
            orthotropic_rocking=arguments.get("orthotropic_rocking"),
            orthotropic_sliding=arguments.get("orthotropic_sliding"),
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(updated_bytes)
        return {"output": str(out_path), "material": summary}

    if name == "hrx_edit_analysis":
        in_path = Path(arguments["hrx_path"])
        out_path = Path(arguments.get("output_path") or in_path)
        raw_attrs = arguments.get("attributes") or {}
        str_attrs = {
            str(k): ("true" if v is True else "false" if v is False else str(v))
            for k, v in raw_attrs.items()
        }
        updated_bytes, summary = edit_analysis_hrx(
            in_path.read_bytes(),
            add_template=arguments.get("add_template"),
            duplicate_key=arguments.get("duplicate_key"),
            delete_key=arguments.get("delete_key"),
            key=arguments.get("key"),
            name=arguments.get("name"),
            node_path=arguments.get("node_path"),
            attributes=str_attrs,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(updated_bytes)
        return {"output": str(out_path), "analysis": summary}

    raise ValueError(f"Unknown tool: {name}")


def handle_rpc(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    req_id = request.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "histra-hrx-builder", "version": "1.0.0"},
            },
        }
    if method and method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            payload = call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(exc)}, indent=2)}],
                    "isError": True,
                },
            }
    if req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle_rpc(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
