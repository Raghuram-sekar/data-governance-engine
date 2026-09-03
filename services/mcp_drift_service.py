import time
from typing import Dict, Any, List
from .mcp_base import BaseMCPService, MCPServiceMetadata, MCPToolDefinition, MCPToolParameter, MCPCallResponse
from agents.drift_healer import SemanticDriftHealer
from semantics.engine import semantic_engine


class SemanticDriftMCPService(BaseMCPService):
    """
    MCP Service: mcp-drift-selfhealerservice
    Autonomous Metric & Schema Drift Diagnostician microservice.
    Repairs broken downstream metrics and KPI alias mappings when physical database columns mutate.
    """

    def __init__(self):
        self._healer = SemanticDriftHealer()
        self._metadata = MCPServiceMetadata(
            service_name="mcp-drift-selfhealerservice",
            description="Autonomous Semantic Metric & Schema Drift Diagnostic and Healing MCP Service",
            category="SEMANTIC_GOVERNANCE",
            supported_anomaly_types=["SEMANTIC_METRIC_DRIFT"],
            tools=[
                MCPToolDefinition(
                    name="validate_metric_health",
                    description="Evaluate if a table contains all necessary columns for an enterprise KPI formula.",
                    parameters=[
                        MCPToolParameter(name="metric_name", type="string", description="Name of KPI metric (e.g. annual_recurring_revenue)"),
                        MCPToolParameter(name="table_columns", type="array", description="List of physical column names in table"),
                    ]
                ),
                MCPToolDefinition(
                    name="diagnose_and_heal_metric_drift",
                    description="Diagnose schema evolution drift and apply semantic alias mappings to repair KPI integrity.",
                    parameters=[
                        MCPToolParameter(name="metric_name", type="string", description="KPI metric name"),
                        MCPToolParameter(name="table_guid", type="string", description="Table GUID"),
                        MCPToolParameter(name="table_columns", type="array", description="Current physical columns list", required=False),
                    ]
                ),
                MCPToolDefinition(
                    name="register_semantic_alias",
                    description="Register an approved semantic column alias in the enterprise ontology.",
                    parameters=[
                        MCPToolParameter(name="metric_name", type="string", description="Metric identifier"),
                        MCPToolParameter(name="expected_column", type="string", description="Canonical column name"),
                        MCPToolParameter(name="actual_column", type="string", description="Renamed physical column name"),
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
            if tool_name == "validate_metric_health":
                metric_name = arguments.get("metric_name", "annual_recurring_revenue")
                cols = arguments.get("table_columns", [])
                res = semantic_engine.check_metric_health(metric_name, cols)

            elif tool_name == "diagnose_and_heal_metric_drift":
                metric_name = arguments.get("metric_name", "annual_recurring_revenue")
                tbl_guid = arguments.get("table_guid", "")
                cols = arguments.get("table_columns", None)
                res = self._healer.diagnose_and_heal_metric(metric_name=metric_name, table_guid=tbl_guid, table_columns=cols)

            elif tool_name == "register_semantic_alias":
                metric_name = arguments.get("metric_name", "")
                exp = arguments.get("expected_column", "")
                act = arguments.get("actual_column", "")
                semantic_engine.register_metric_alias(metric_name, exp, act)
                res = {
                    "status": "HEALED",
                    "metric": metric_name,
                    "mapping": f"{act} -> {exp}",
                    "message": f"Successfully mapped '{act}' to canonical '{exp}'."
                }

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
