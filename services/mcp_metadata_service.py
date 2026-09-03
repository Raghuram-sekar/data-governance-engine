import time
from typing import Dict, Any, List
from .mcp_base import BaseMCPService, MCPServiceMetadata, MCPToolDefinition, MCPToolParameter, MCPCallResponse
from agents.metadata_enricher import MetadataEnricher
from semantics.engine import semantic_engine


class MetadataEnricherMCPService(BaseMCPService):
    """
    MCP Service: mcp-metadata-selfhealerservice
    Autonomous Metadata Enrichment, Business Glossary Curation & Stewardship microservice.
    """

    def __init__(self):
        self._enricher = MetadataEnricher()
        self._metadata = MCPServiceMetadata(
            service_name="mcp-metadata-selfhealerservice",
            description="Autonomous Business Documentation, Glossary Linking & Stewardship MCP Service",
            category="METADATA_CURATION",
            supported_anomaly_types=["MISSING_DESCRIPTION", "MISSING_OWNER", "UNLINKED_GLOSSARY"],
            tools=[
                MCPToolDefinition(
                    name="lookup_glossary_definition",
                    description="Find canonical enterprise glossary term, business definition, and sensitivity.",
                    parameters=[
                        MCPToolParameter(name="term_query", type="string", description="Name or synonym of term"),
                    ]
                ),
                MCPToolDefinition(
                    name="heal_table_metadata",
                    description="Auto-generate table documentation and assign domain data steward in Atlan.",
                    parameters=[
                        MCPToolParameter(name="table_guid", type="string", description="Table GUID"),
                        MCPToolParameter(name="table_name", type="string", description="Table name"),
                        MCPToolParameter(name="schema_name", type="string", description="Schema name", required=False, default="public"),
                    ]
                ),
                MCPToolDefinition(
                    name="heal_column_metadata",
                    description="Auto-populate column business description and link verified glossary term in Atlan.",
                    parameters=[
                        MCPToolParameter(name="column_guid", type="string", description="Column GUID"),
                        MCPToolParameter(name="column_name", type="string", description="Column name"),
                        MCPToolParameter(name="table_name", type="string", description="Parent table name", required=False, default=""),
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
            if tool_name == "lookup_glossary_definition":
                query = arguments.get("term_query", "")
                term = semantic_engine.lookup_glossary_term(query)
                if term:
                    res = {
                        "found": True,
                        "name": term.name,
                        "definition": term.definition,
                        "domain": term.domain,
                        "sensitivity": term.sensitivity.value
                    }
                else:
                    res = {"found": False, "query": query}

            elif tool_name == "heal_table_metadata":
                tbl_guid = arguments.get("table_guid", "")
                tbl_name = arguments.get("table_name", "")
                schema = arguments.get("schema_name", "public")
                res = self._enricher.heal_table_metadata(table_guid=tbl_guid, table_name=tbl_name, schema_name=schema)

            elif tool_name == "heal_column_metadata":
                col_guid = arguments.get("column_guid", "")
                col_name = arguments.get("column_name", "")
                tbl_name = arguments.get("table_name", "")
                res = self._enricher.heal_column_metadata(column_guid=col_guid, column_name=col_name, table_name=tbl_name)

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
