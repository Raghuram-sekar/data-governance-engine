import abc
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class MCPToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None


class MCPToolDefinition(BaseModel):
    name: str
    description: str
    parameters: List[MCPToolParameter] = Field(default_factory=list)


class MCPCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class MCPCallResponse(BaseModel):
    service_name: str
    tool_name: str
    status: str  # "SUCCESS", "ERROR", "HEALED"
    result: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    error_message: Optional[str] = None


class MCPServiceMetadata(BaseModel):
    service_name: str
    description: str
    category: str
    supported_anomaly_types: List[str] = Field(default_factory=list)
    tools: List[MCPToolDefinition] = Field(default_factory=list)


class BaseMCPService(abc.ABC):
    """
    Abstract Base Class for Model Context Protocol (MCP) Self-Healing Services.
    Enables dynamic tool discovery, standard JSON-RPC/REST invocation, and telemetry emission.
    """

    @property
    @abc.abstractmethod
    def metadata(self) -> MCPServiceMetadata:
        """Returns the metadata and tool definitions for this MCP service."""
        pass

    @abc.abstractmethod
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPCallResponse:
        """Invokes a specific tool on this MCP service with given JSON arguments."""
        pass

    def list_tools(self) -> List[MCPToolDefinition]:
        """Returns list of exposed tools."""
        return self.metadata.tools
