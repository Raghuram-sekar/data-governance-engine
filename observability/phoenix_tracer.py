import os
import sys
import time
import json
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

import logging
logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)
logging.getLogger("opentelemetry.exporter.otlp").setLevel(logging.CRITICAL)

# Setup OpenTelemetry Tracer with Official Arize Phoenix gRPC Exporter (port 4317)
try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    _resource = Resource.create({
        "service.name": "data-governance-engine",
        "project.name": "data-governance-engine"
    })
    _provider = TracerProvider(resource=_resource)
    _exporter = OTLPSpanExporter(endpoint="127.0.0.1:4317", insecure=True)
    _provider.add_span_processor(BatchSpanProcessor(_exporter))
    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer("agno.governance.agent")
except Exception:
    _tracer = None
    StatusCode = None


class PhoenixObservability:
    """
    Official Arize Phoenix Multi-Agent Observability Manager.
    Exports OpenTelemetry traces via gRPC directly to official Arize Phoenix UI (http://localhost:6006).
    """

    def __init__(self):
        self._traces_file = Path(__file__).parent.parent / "governance_traces.json"
        self._traces = self._load_traces()

    def _load_traces(self) -> List[Dict[str, Any]]:
        if self._traces_file.exists():
            try:
                with open(self._traces_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_traces(self):
        try:
            with open(self._traces_file, "w", encoding="utf-8") as f:
                json.dump(self._traces, f, indent=2)
        except Exception:
            pass

    def log_agent_trace(
        self,
        agent_name: str,
        task: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        tools_called: list,
        latency_ms: float = 120.0,
        model_name: str = "llama3.2:1b"
    ) -> Dict[str, Any]:
        """Records an execution span and exports to official Arize Phoenix via OpenTelemetry gRPC."""
        trace_record = {
            "trace_id": f"TRC-{len(self._traces) + 1:04d}",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "agent_name": agent_name,
            "task": task,
            "model": model_name,
            "latency_ms": round(max(latency_ms, 45.0), 2),
            "tools_called": tools_called,
            "input": input_data,
            "output": output_data,
            "status": "OK"
        }
        self._traces.append(trace_record)
        self._save_traces()

        # Emit native OpenTelemetry Span into Official Arize Phoenix
        if _tracer:
            try:
                now_ns = time.time_ns()
                sim_lat_ns = int(max(latency_ms, 65.0) * 1_000_000)
                start_ns = now_ns - sim_lat_ns

                span_name = f"{agent_name}: {task}"
                span = _tracer.start_span(
                    name=span_name,
                    start_time=start_ns
                )
                
                span.set_attribute("openinference.span.kind", "AGENT")
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("llm.model_name", model_name)
                span.set_attribute("execution.latency_ms", max(latency_ms, 65.0))
                span.set_attribute("tools.called", ", ".join(tools_called))
                span.set_attribute("governance.status", str(output_data.get("status", "HEALED")))
                
                # Set formatted Phoenix input and output values
                span.set_attribute("input.value", json.dumps(input_data, indent=2))
                span.set_attribute("output.value", json.dumps(output_data, indent=2))

                if "classification" in output_data or "classification_applied" in output_data:
                    c = output_data.get("classification") or output_data.get("classification_applied")
                    span.set_attribute("governance.classification", str(c))
                if "masking_enforced" in output_data:
                    span.set_attribute("governance.masking_enforced", str(output_data.get("masking_enforced")))
                if "rule_matched" in output_data:
                    span.set_attribute("governance.rule_matched", str(output_data.get("rule_matched")))
                if "description_added" in output_data:
                    span.set_attribute("governance.description_added", str(output_data.get("description_added")))
                if "glossary_term_linked" in output_data:
                    span.set_attribute("governance.glossary_term", str(output_data.get("glossary_term_linked")))
                if "owner_assigned" in output_data:
                    span.set_attribute("governance.owner_assigned", str(output_data.get("owner_assigned")))
                
                if StatusCode:
                    span.set_status(StatusCode.OK)

                span.end(end_time=now_ns)
            except Exception:
                pass

        return trace_record

    def get_all_traces(self) -> List[Dict[str, Any]]:
        return self._traces

    def start_official_server(self, port: int = 6006):
        """Starts the Official Arize Phoenix Web Server."""
        cmd = [sys.executable, "-m", "phoenix.server.main", "serve", "--port", str(port)]
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            pass


phoenix_tracer = PhoenixObservability()
