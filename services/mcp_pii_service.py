import time
from typing import Dict, Any, List
from .mcp_base import BaseMCPService, MCPServiceMetadata, MCPToolDefinition, MCPToolParameter, MCPCallResponse
from agents.pii_healer import PIISecurityHealer
from connectors import connector_registry
from observability.phoenix_tracer import phoenix_tracer
from semantics.engine import semantic_engine


class PIISelfHealerMCPService(BaseMCPService):
    """
    MCP Service: mcp-pii-selfhealerservice
    Autonomous PII/PCI Data Privacy and Dynamic Masking microservice.
    Exposes standardized MCP tools for data sensitivity scanning and remediation across all databases.
    """

    def __init__(self):
        self._healer = PIISecurityHealer()
        self._metadata = MCPServiceMetadata(
            service_name="mcp-pii-selfhealerservice",
            description="Autonomous PII/PCI Sensitivity Classification & Cross-Database Dynamic Masking MCP Service",
            category="SECURITY_AND_PRIVACY",
            supported_anomaly_types=["UNCLASSIFIED_PII"],
            tools=[
                MCPToolDefinition(
                    name="evaluate_sensitivity",
                    description="Evaluate column sensitivity against enterprise semantic policies and determine required classification.",
                    parameters=[
                        MCPToolParameter(name="column_name", type="string", description="Name of database column"),
                        MCPToolParameter(name="data_type", type="string", description="SQL data type", required=False, default="VARCHAR"),
                    ]
                ),
                MCPToolDefinition(
                    name="heal_pii_column",
                    description="Remediate sensitive column in Atlan Active Metadata Catalog with security tag and masking.",
                    parameters=[
                        MCPToolParameter(name="column_guid", type="string", description="Atlan Column GUID"),
                        MCPToolParameter(name="column_name", type="string", description="Column name"),
                        MCPToolParameter(name="data_type", type="string", description="SQL data type", required=False, default="VARCHAR"),
                    ]
                ),
                MCPToolDefinition(
                    name="enforce_database_masking",
                    description="Apply dynamic column masking directly on physical database connector (PostgreSQL, MongoDB, ChromaDB).",
                    parameters=[
                        MCPToolParameter(name="connector_id", type="string", description="Connector ID (postgres, mongodb, chroma)"),
                        MCPToolParameter(name="table_name", type="string", description="Table or collection name"),
                        MCPToolParameter(name="column_name", type="string", description="Sensitive column or field name"),
                    ]
                )
            ]
        )

    @property
    def metadata(self) -> MCPServiceMetadata:
        return self._metadata

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPCallResponse:
        start_time = time.time()

        try:
            if tool_name == "evaluate_sensitivity":
                col_name = arguments.get("column_name", "")
                data_type = arguments.get("data_type", "VARCHAR")
                match = semantic_engine.match_sensitivity(col_name, data_type)
                if match:
                    rule, conf = match
                    res = {
                        "is_sensitive": True,
                        "classification": rule.classification.value,
                        "confidence": conf,
                        "enforce_masking": getattr(rule, "enforce_masking", True),
                        "rule_id": rule.rule_id
                    }
                else:
                    res = {"is_sensitive": False, "classification": None, "confidence": 0.0}

            elif tool_name == "heal_pii_column":
                col_guid = arguments.get("column_guid", "")
                col_name = arguments.get("column_name", "")
                data_type = arguments.get("data_type", "VARCHAR")
                res = self._healer.heal_column(column_guid=col_guid, column_name=col_name, data_type=data_type)

            elif tool_name == "enforce_database_masking":
                conn_id = arguments.get("connector_id", "postgres").lower()
                tbl_name = arguments.get("table_name", "")
                col_name = arguments.get("column_name", "")
                conn = connector_registry.get(conn_id)

                if conn and tbl_name and col_name:
                    conn.apply_data_masking(tbl_name, col_name)
                    res = {
                        "status": "HEALED",
                        "action": f"DYNAMIC_MASKING_ENFORCED_{conn_id.upper()}",
                        "connector": conn_id,
                        "table": tbl_name,
                        "column": col_name,
                        "masking_active": True
                    }
                    # Stream OTel span to Phoenix
                    phoenix_tracer.log_agent_trace(
                        agent_name="MCP:mcp-pii-selfhealerservice",
                        task=f"Enforce dynamic masking on {conn_id.upper()}.{tbl_name}.{col_name}",
                        input_data=arguments,
                        output_data=res,
                        tools_called=["enforce_database_masking"],
                        latency_ms=(time.time() - start_time) * 1000 + 40.0
                    )
                else:
                    res = {"status": "ERROR", "error": f"Connector '{conn_id}' or target table/col not found"}

            else:
                return MCPCallResponse(
                    service_name=self.metadata.service_name,
                    tool_name=tool_name,
                    status="ERROR",
                    error_message=f"Tool '{tool_name}' not found on service '{self.metadata.service_name}'"
                )

            latency = round((time.time() - start_time) * 1000, 2)
            return MCPCallResponse(
                service_name=self.metadata.service_name,
                tool_name=tool_name,
                status="SUCCESS" if res.get("status") != "ERROR" else "ERROR",
                result=res,
                latency_ms=latency
            )

        except Exception as e:
            return MCPCallResponse(
                service_name=self.metadata.service_name,
                tool_name=tool_name,
                status="ERROR",
                error_message=str(e),
                latency_ms=round((time.time() - start_time) * 1000, 2)
            )
