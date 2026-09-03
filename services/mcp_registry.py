from typing import Dict, List, Optional, Any
from .mcp_base import BaseMCPService, MCPServiceMetadata, MCPCallResponse, MCPToolDefinition
from .mcp_pii_service import PIISelfHealerMCPService
from .mcp_metadata_service import MetadataEnricherMCPService
from .mcp_drift_service import SemanticDriftMCPService


class MCPServiceRegistry:
    """
    Central Dynamic Discovery & Dispatch Registry for all MCP Self-Healing Services.
    Allows the Key-Orchestrator Agent to discover available microservices and invoke them via standard protocol.
    """

    def __init__(self):
        self._services: Dict[str, BaseMCPService] = {}
        self._anomaly_routing_map: Dict[str, str] = {}
        self._bootstrap_services()

    def _bootstrap_services(self):
        # Register Core MCP Self-Healing Microservices
        pii_service = PIISelfHealerMCPService()
        metadata_service = MetadataEnricherMCPService()
        drift_service = SemanticDriftMCPService()

        self.register_service(pii_service)
        self.register_service(metadata_service)
        self.register_service(drift_service)

    def register_service(self, service: BaseMCPService):
        """Registers an MCP service and indexes its supported anomaly types."""
        name = service.metadata.service_name
        self._services[name] = service

        for anomaly in service.metadata.supported_anomaly_types:
            self._anomaly_routing_map[anomaly] = name

    def get_service(self, service_name: str) -> Optional[BaseMCPService]:
        """Retrieves an MCP service by name."""
        return self._services.get(service_name)

    def discover_services(self) -> List[MCPServiceMetadata]:
        """Discovery endpoint: lists all available MCP services and their tool signatures."""
        return [svc.metadata for svc in self._services.values()]

    def list_all_tools(self) -> List[Dict[str, Any]]:
        """Returns all exposed tools across all MCP services."""
        tools = []
        for svc in self._services.values():
            for t in svc.list_tools():
                tools.append({
                    "service_name": svc.metadata.service_name,
                    "tool": t.model_dump()
                })
        return tools

    def route_for_anomaly(self, anomaly_type: str) -> Optional[BaseMCPService]:
        """Dynamically resolves the appropriate MCP service for a given anomaly type."""
        svc_name = self._anomaly_routing_map.get(anomaly_type)
        if svc_name:
            return self._services.get(svc_name)
        return None

    def execute_tool(self, service_name: str, tool_name: str, arguments: dict) -> MCPCallResponse:
        """Executes a tool on the specified MCP service."""
        svc = self.get_service(service_name)
        if not svc:
            return MCPCallResponse(
                service_name=service_name,
                tool_name=tool_name,
                status="ERROR",
                error_message=f"MCP Service '{service_name}' is not registered."
            )
        return svc.call_tool(tool_name, arguments)


# Global singleton instance
mcp_registry = MCPServiceRegistry()
