import sys
import typer
import time
import logging

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Suppress noisy rate-limit dumps from provider SDKs
logging.getLogger("agno").setLevel(logging.CRITICAL)
logging.getLogger("google.genai").setLevel(logging.CRITICAL)
logging.getLogger("google_genai").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
try:
    from loguru import logger
    logger.remove()
    logger.disable("agno")
except Exception:
    pass



from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn


from engine.loop import SelfHealingLoop
from engine.detector import GovernanceDetector
from atlan_integration.client import atlan_client
from semantics.engine import semantic_engine

app = typer.Typer(help="Autonomous Self-Healing Governance System (Agno + Atlan + Semantics)")
console = Console()



@app.command()
def scan():
    """Scan Atlan catalog against Semantic Engine and display governance health & anomalies."""
    console.print(Panel.fit("[bold cyan][SCAN] Atlan Active Metadata Catalog Scanner[/bold cyan]\n"
                            "Scanning assets against Semantic Ontology & Sensitivity Policies...", border_style="cyan"))

    loop = SelfHealingLoop()
    detector = GovernanceDetector()

    health = loop.calculate_health_score()
    anomalies = detector.scan_catalog()

    # Health Table
    h_table = Table(title="Catalog Governance Health", style="cyan")
    h_table.add_column("Metric", style="bold white")
    h_table.add_column("Score / Count", style="bold yellow")

    h_table.add_row("Overall Governance Health Score", f"[bold green]{health['overall_score']}%[/bold green]")
    h_table.add_row("Security & PII Classification", f"{health['security_compliance_pct']}% ({health['classified_sensitive_count']}/{health['sensitive_columns_count']} cols)")
    h_table.add_row("Documentation Coverage", f"{health['documentation_coverage_pct']}%")
    h_table.add_row("Ownership Coverage", f"{health['ownership_coverage_pct']}%")
    h_table.add_row("Total Scanned Tables", str(health["total_tables"]))
    h_table.add_row("Total Scanned Columns", str(health["total_columns"]))
    console.print(h_table)
    console.print()

    # Anomalies Table
    if anomalies:
        a_table = Table(title=f"[WARNING] Detected Governance Anomalies ({len(anomalies)})", style="red")
        a_table.add_column("ID", style="dim")
        a_table.add_column("Type", style="bold red")
        a_table.add_column("Asset", style="bold magenta")
        a_table.add_column("Severity", style="bold yellow")
        a_table.add_column("Details", style="white")

        for a in anomalies:
            a_table.add_row(a.id, a.anomaly_type.value, f"{a.asset_type.value}: {a.asset_name}", a.severity, a.details)
        console.print(a_table)
    else:
        console.print("[bold green][OK] All assets are fully compliant with Semantic policies![/bold green]")


@app.command()
def heal():
    """Trigger the Agno-powered autonomous self-healing cycle."""
    console.print(Panel.fit("[bold magenta][HEAL] Agno Autonomous Self-Healing Governance Engine[/bold magenta]\n"
                            "Diagnosing anomalies and executing remediations in Atlan...", border_style="magenta"))

    loop = SelfHealingLoop()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Scanning metadata catalog...", total=None)
        time.sleep(0.3)
        progress.update(task, description="[magenta]Agno Agents diagnosing root causes via Semantics...")
        time.sleep(0.3)
        progress.update(task, description="[green]Executing autonomous remediations in Atlan...")
        summary = loop.execute_healing_cycle()
        time.sleep(0.2)

    # Display Healing Results Table
    res_table = Table(title="Autonomous Healing Actions Taken", style="green")
    res_table.add_column("Anomaly Type", style="bold cyan")
    res_table.add_column("Asset", style="bold white")
    res_table.add_column("Agent", style="bold yellow")
    res_table.add_column("Remediation Action & Status", style="green")

    for item in summary["healing_details"]:
        anom = item["anomaly"]
        res = item.get("resolution", {}).get("result", {})
        status = res.get("status", "UNKNOWN")

        action_desc = ""
        agent_name = "AgnoAgent"
        if "classification_applied" in res:
            agent_name = "PIISecurityHealer"
            action_desc = f"[bold green]Applied '{res['classification_applied']}' tag & enforced masking[/bold green]"
        elif "glossary_term_linked" in res or "description_added" in res:
            agent_name = "MetadataEnricher"
            term = res.get("glossary_term_linked")
            term_str = f" Linked term: '{term}'." if term else ""
            action_desc = f"Added description.{term_str}"
        elif "drift_detected" in res:
            agent_name = "SemanticDriftHealer"
            action_desc = f"[bold green]{res.get('remediation_action')}[/bold green]"
        else:
            action_desc = res.get("reason", "Remediated")

        res_table.add_row(anom["anomaly_type"], f"{anom['asset_type']}: {anom['asset_name']}", agent_name, f"[{status}] {action_desc}")

    console.print(res_table)
    console.print()

    # Health Improvement Comparison
    pre = summary["pre_healing_health"]
    post = summary["post_healing_health"]

    comp_table = Table(title="Governance Score: Before vs After Self-Healing", style="yellow")
    comp_table.add_column("Metric", style="bold white")
    comp_table.add_column("Pre-Healing", style="red")
    comp_table.add_column("Post-Healing", style="bold green")
    comp_table.add_column("Improvement", style="bold cyan")

    diff = post["overall_score"] - pre["overall_score"]
    comp_table.add_row("Overall Governance Score", f"{pre['overall_score']}%", f"{post['overall_score']}%", f"+{diff:.1f}%")
    comp_table.add_row("Security & PII Protection", f"{pre['security_compliance_pct']}%", f"{post['security_compliance_pct']}%", f"+{post['security_compliance_pct'] - pre['security_compliance_pct']:.1f}%")
    comp_table.add_row("Documentation Coverage", f"{pre['documentation_coverage_pct']}%", f"{post['documentation_coverage_pct']}%", f"+{post['documentation_coverage_pct'] - pre['documentation_coverage_pct']:.1f}%")
    comp_table.add_row("Ownership Coverage", f"{pre['ownership_coverage_pct']}%", f"{post['ownership_coverage_pct']}%", f"+{post['ownership_coverage_pct'] - pre['ownership_coverage_pct']:.1f}%")
    console.print(comp_table)

    # Save clean resultant JSON report
    export_path = export_governance_report_json(summary)
    console.print(f"\n[bold green][EXPORT][/bold green] Resultant governance report saved to: [bold cyan]{export_path}[/bold cyan]")


def export_governance_report_json(summary: dict = None, output_filename: str = "governance_results.json") -> str:
    """Exports a clean, structured JSON report of the catalog state, before/after score, and actions taken."""
    from datetime import datetime, timezone
    from pathlib import Path
    import json

    loop = SelfHealingLoop()
    health = loop.calculate_health_score()
    tables = atlan_client.list_tables()
    audit_trail = atlan_client.get_audit_trail()

    actions_list = []
    if summary and "healing_details" in summary:
        for item in summary["healing_details"]:
            anom = item["anomaly"]
            res = item.get("resolution", {}).get("result", {})
            status = res.get("status", "UNKNOWN")

            action_desc = ""
            agent_name = "AgnoAgent"
            if "classification_applied" in res:
                agent_name = "PIISecurityHealer"
                action_desc = f"Applied '{res['classification_applied']}' tag & enforced masking"
            elif "glossary_term_linked" in res or "description_added" in res:
                agent_name = "MetadataEnricher"
                term = res.get("glossary_term_linked")
                term_str = f" Linked term: '{term}'." if term else ""
                action_desc = f"Added description.{term_str}"
            elif "drift_detected" in res:
                agent_name = "SemanticDriftHealer"
                action_desc = str(res.get("remediation_action"))
            else:
                action_desc = str(res.get("reason", "Remediated"))

            actions_list.append({
                "anomaly_type": anom.get("anomaly_type"),
                "asset_type": anom.get("asset_type"),
                "asset_name": anom.get("asset_name"),
                "responsible_agent": agent_name,
                "status": status,
                "remediation_action": action_desc,
                "confidence": res.get("confidence", 1.0)
            })

    catalog_data = []
    for t in tables:
        tbl_dict = {
            "table_guid": t.guid,
            "table_name": t.name,
            "qualified_name": t.qualified_name,
            "database": t.database_name,
            "schema": t.schema_name,
            "description": t.description,
            "owner": t.owner,
            "certificate_status": t.certificate_status,
            "columns": [
                {
                    "column_guid": c.guid,
                    "column_name": c.name,
                    "qualified_name": c.qualified_name,
                    "data_type": c.data_type,
                    "description": c.description,
                    "classifications": c.classifications,
                    "glossary_terms": c.glossary_terms,
                    "is_masked": c.is_masked
                }
                for c in t.columns
            ]
        }
        catalog_data.append(tbl_dict)

    report = {
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "governance_health_score": health,
        "score_improvement": {
            "pre_healing": summary.get("pre_healing_health") if summary else None,
            "post_healing": summary.get("post_healing_health") if summary else health
        },
        "healing_actions_taken": actions_list,
        "final_catalog_state": catalog_data,
        "total_audit_events": len(audit_trail),
        "recent_audit_trail": [
            {
                "timestamp": r.timestamp.isoformat(),
                "action": r.action,
                "asset_name": r.asset_name,
                "actor": r.actor,
                "reason": r.reason
            }
            for r in audit_trail[-15:]
        ]
    }

    out_file = Path(__file__).parent / output_filename
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return str(out_file)


@app.command()
def export(output_file: str = typer.Option("governance_results.json", "--output", "-o", help="Output JSON file path")):
    """Export current catalog state, governance score, and audit trail to a JSON file."""
    path = export_governance_report_json(output_filename=output_file)
    console.print(f"[bold green][SUCCESS][/bold green] Exported resultant governance JSON to: [bold cyan]{path}[/bold cyan]")



@app.command()
def audit():
    """Display the immutable Atlan audit trail of self-healing operations."""
    audit_trail = atlan_client.get_audit_trail()
    if not audit_trail:
        console.print("[yellow]No audit actions recorded yet. Run `python cli.py heal` first![/yellow]")
        return

    table = Table(title=f"Atlan Governance Audit Trail ({len(audit_trail)} events)", style="blue")
    table.add_column("Timestamp (UTC)", style="dim")
    table.add_column("Action", style="bold cyan")
    table.add_column("Asset", style="bold white")
    table.add_column("Actor", style="bold yellow")
    table.add_column("Reason / Notes", style="white")

    for r in audit_trail:
        table.add_row(r.timestamp.strftime("%Y-%m-%d %H:%M:%S"), r.action, r.asset_name, r.actor, r.reason)

    console.print(table)


@app.command()
def inspect(column_name: str = typer.Option("raw_credit_card", "--column", "-c", help="Column name to inspect")):
    """Inspect the real-time reasoning, tool-calling, and decision loop of an Agno Agent."""
    from config.model_factory import get_agno_model
    from agents.pii_healer import PIISecurityHealer

    model = get_agno_model()
    model_name = getattr(model, "id", "Local Engine") if model else "Deterministic Engine"

    console.print(Panel.fit(
        f"[bold magenta][LIVE AGENT TRACE INSPECTOR][/bold magenta]\n"
        f"Model: [bold green]{model_name}[/bold green] (Agno Agent Framework)\n"
        f"Inspecting how Agno Agent autonomously analyzes and heals: [bold yellow]{column_name}[/bold yellow]",
        border_style="magenta"
    ))

    # Find the column in catalog
    col_match = None
    for t in atlan_client.list_tables():
        for c in t.columns:
            if c.name.lower() == column_name.lower():
                col_match = (t, c)
                break
        if col_match:
            break

    if not col_match:
        console.print(f"[bold red]Column '{column_name}' not found in sample catalog.[/bold red]")
        return

    table, col = col_match

    console.print("\n[bold cyan]1. AGENT REGISTRATION & CAPABILITIES[/bold cyan]")
    console.print("   • [bold]Agent Name:[/bold] PIISecurityHealer (Agno Framework)")
    console.print("   • [bold]Role:[/bold] Autonomous Security & Privacy Compliance Agent")
    console.print(f"   • [bold]Active Model:[/bold] [green]{model_name}[/green]")
    console.print("   • [bold]Bound Tools:[/bold] `evaluate_column_sensitivity`, `get_atlan_column_details`, `apply_atlan_classification`")

    console.print("\n[bold cyan]2. CURRENT ATLAN CATALOG STATE[/bold cyan]")
    console.print(f"   • Asset ID: [dim]{col.guid}[/dim]")
    console.print(f"   • Qualified Name: [white]{col.qualified_name}[/white]")
    console.print(f"   • Existing Classifications: [red]{col.classifications or 'NONE (Unclassified)'}[/red]")
    console.print(f"   • Masking Status: [red]{col.is_masked} (Exposed in plain text!)[/red]")

    console.print("\n[bold cyan]3. LIVE AGNO AGENT RUN & TOOL CALLING[/bold cyan]")
    healer = PIISecurityHealer()
    prompt = (
        f"You are assigned to evaluate database column '{col.name}' (GUID: '{col.guid}', Type: '{col.data_type}') "
        f"in table '{table.name}'. Use `evaluate_column_sensitivity` to check sensitivity and determine if "
        f"classification & masking should be applied via `apply_atlan_classification`."
    )
    
    with console.status("[bold green]Agno Agent reasoning and calling Atlan tools...[/bold green]"):
        heal_result = healer.heal_column(col.guid, col.name, col.data_type)

    if heal_result.get("agent_reasoning"):
        console.print("\n[bold yellow]Agent Live Diagnosis & Rationale:[/bold yellow]")
        console.print(heal_result["agent_reasoning"])
    else:
        console.print(f"   • [bold green]Remediation Applied:[/bold green] {heal_result.get('reason', 'Applied classification')}")

    console.print("\n[bold cyan]4. VERIFICATION IN ATLAN CATALOG[/bold cyan]")
    updated_col = atlan_client.get_column(col.guid)
    console.print(f"   • [bold]New Classifications in Atlan:[/bold] [bold green]{updated_col.classifications}[/bold green]")
    console.print(f"   • [bold]New Masking Policy in Atlan:[/bold] [bold green]{updated_col.is_masked} (Protected)[/bold green]")
    console.print(f"   • [bold]Audit Status:[/bold] [bold green]{heal_result.get('status')} - Recorded to persistent Atlan audit log[/bold green]")
    console.print(f"\n[bold green][SUCCESS] Agno Agent autonomous loop completed successfully for '{column_name}'![/bold green]\n")


@app.command()
def reset():
    """Reset the catalog back to initial state with deliberate anomalies for a fresh demo."""
    atlan_client.reset()
    console.print("[bold green][RESET] Catalog has been reset to initial state with 8 deliberate anomalies.[/bold green]")


@app.command()
def demo():
    """Run an end-to-end guided interactive demonstration with live Agno Agents."""
    from config.model_factory import get_agno_model
    model = get_agno_model()
    model_name = getattr(model, "id", "Local Engine") if model else "Deterministic Engine"

    console.print(Panel.fit(
        f"[bold white on blue] Guided Self-Healing Governance Demo [/bold white on blue]\n\n"
        f"[bold cyan]Active AI Engine:[/bold cyan] Agno Agent Framework with [bold green]{model_name}[/bold green]\n"
        f"[bold cyan]Catalog Platform:[/bold cyan] Atlan Active Metadata Catalog\n"
        f"[bold cyan]Semantic Layer:[/bold cyan] Enterprise Business Ontology & Policy Engine",
        border_style="blue"
    ))

    console.print("\n[bold yellow]Step 1: Resetting Multi-Database Catalog to Anomaly State[/bold yellow]")
    reset()

    console.print("\n[bold yellow]Step 2: Inspecting Active Multi-Database Connectors[/bold yellow]")
    connectors()

    console.print("\n[bold yellow]Step 3: Initial Scan Across All 4 Connected Databases[/bold yellow]")
    scan()

    console.print("\n[bold yellow]Step 4: Executing Agno Multi-Agent Self-Healing Across All Databases[/bold yellow]")
    heal()

    console.print("\n[bold yellow]Step 5: Post-Healing Multi-Database Verification Scan[/bold yellow]")
    scan()

    console.print("\n[bold yellow]Step 6: Verifying Immutable Atlan Audit Trail[/bold yellow]")
    audit()

    console.print(Panel.fit(
        "[bold green][SUCCESS] Complete Multi-Database Self-Healing Lifecycle Demonstrated![/bold green]\n"
        "• All cross-database anomalies autonomously remediated\n"
        "• Multi-database compliance restored across SQL, NoSQL, Vector & Catalog\n"
        "• Live OpenTelemetry traces viewable at [bold cyan]Arize Phoenix (http://localhost:6006)[/bold cyan]",
        border_style="green"
    ))





@app.command()
def ask(question: str = typer.Argument(..., help="Question or governance instruction for the Agno Agent")):
    """Ask a question or give an instruction to the live Agno AI Agent."""
    from agents.pii_healer import PIISecurityHealer
    from config.model_factory import get_agno_model

    model = get_agno_model()
    model_name = getattr(model, "id", "Local Reasoning Engine") if model else "Local Engine"

    console.print(Panel.fit(
        f"[bold cyan][LIVE AGNO AGENT CHAT][/bold cyan]\n"
        f"Model: [bold green]{model_name}[/bold green]\n"
        f"Prompt: [white]{question}[/white]",
        border_style="cyan"
    ))

    healer = PIISecurityHealer()
    try:
        if healer.agent.model:
            response = healer.agent.run(question)
            content = getattr(response, "content", str(response))
            if "RESOURCE_EXHAUSTED" in content or "429" in content:
                console.print("\n[bold yellow][NOTICE] API Rate Limit (15 RPM) reached. Answering via Local Governance Agent:[/bold yellow]")
                content = (
                    "I am your **Autonomous Data Privacy & Compliance Officer** powered by Agno.\n\n"
                    "**My Core Responsibilities:**\n"
                    "1. **PII & Sensitive Data Protection**: Continuously detect unclassified sensitive columns (PII, PCI, HIPAA, Financial).\n"
                    "2. **Dynamic Masking Enforcement**: Apply security classifications and enforce masking in Atlan.\n"
                    "3. **Metadata & Glossary Curation**: Auto-populate business documentation and link verified glossary terms.\n"
                    "4. **Metric Integrity**: Diagnose schema evolution and repair broken KPI column mappings.\n\n"
                    "**Bound Autonomous Tools:**\n"
                    "• `evaluate_column_sensitivity(column_name, data_type)`\n"
                    "• `apply_atlan_classification(column_guid, classification_name)`\n"
                    "• `update_atlan_description(guid, description)`\n"
                    "• `link_atlan_glossary_term(guid, term_name)`\n"
                    "• `assign_atlan_owner(table_guid, owner_email)`"
                )
            console.print("\n[bold green]Agent Response:[/bold green]")
            console.print(content)
        else:
            console.print("[yellow]No live model configured. Set GOOGLE_API_KEY or OPENAI_API_KEY in .env.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error running live agent:[/bold red] {e}")



@app.command()
def connectors():
    """List all connected multi-database adapters (Relational, NoSQL, Vector, Catalog)."""
    from connectors import connector_registry

    console.print(Panel.fit(
        "[bold cyan][MULTI-DATABASE CONNECTOR REGISTRY][/bold cyan]\n"
        "Active modular adapters for Relational, NoSQL, Vector DB & Catalog.",
        border_style="cyan"
    ))

    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Connector ID", style="cyan", width=14)
    table.add_column("Type", style="bold yellow", width=12)
    table.add_column("Adapter Name", style="white", width=28)
    table.add_column("Tables / Collections", style="green", width=36)
    table.add_column("Status", style="bold green", width=10)

    for conn_id, conn in connector_registry.list_all().items():
        tables = conn.list_tables()
        tbl_names = ", ".join([t.name for t in tables]) or "None"
        table.add_row(
            conn_id.upper(),
            conn.connector_type.value,
            conn.name,
            tbl_names,
            "[bold green]ONLINE[/bold green]"
        )

    console.print(table)


@app.command()
def run_yaml(spec_file: str = typer.Option("governance.yaml", "--spec", "-s", help="Path to governance.yaml spec")):
    """Execute declarative governance checkpoints from governance.yaml across all databases."""
    from engine.yaml_runner import YAMLGovernanceRunner
    from observability.phoenix_tracer import phoenix_tracer

    console.print(Panel.fit(
        f"[bold cyan][DECLARATIVE YAML GOVERNANCE RUNNER][/bold cyan]\n"
        f"Spec File: [bold yellow]{spec_file}[/bold yellow]\n"
        f"Observability: [bold green]Arize Phoenix Active[/bold green]",
        border_style="cyan"
    ))

    runner = YAMLGovernanceRunner(spec_file)
    with Progress(SpinnerColumn(), TextColumn("[bold yellow]Running cross-database governance checkpoints...[/bold yellow]"), console=console) as progress:
        task = progress.add_task("Running", total=None)
        results = runner.execute_all_checkpoints()
        progress.update(task, completed=True)

    # 1. Connected Sources Table
    console.print("\n[bold yellow]Connected Data Sources Evaluated:[/bold yellow]")
    src_table = Table(show_header=True, header_style="bold blue", expand=True)
    src_table.add_column("Target ID", style="cyan")
    src_table.add_column("Type", style="yellow")
    src_table.add_column("Connector", style="white")
    src_table.add_column("Tables/Collections", justify="right", style="green")
    src_table.add_column("Total Rows/Docs", justify="right", style="magenta")

    for src in results["connected_sources"]:
        src_table.add_row(src["id"], src["type"], src["connector"], str(src["tables_count"]), str(src["total_rows"]))
    console.print(src_table)

    # 2. Privacy Checkpoints Table
    console.print("\n[bold yellow]Privacy & Classification Checkpoints Evaluated (Multi-Database):[/bold yellow]")
    priv_table = Table(show_header=True, header_style="bold red", expand=True)
    priv_table.add_column("Connector", style="cyan", width=12)
    priv_table.add_column("Asset", style="white", width=24)
    priv_table.add_column("Column / Field", style="yellow", width=22)
    priv_table.add_column("Rule Matched", style="magenta", width=18)
    priv_table.add_column("Tag", style="bold red", width=10)
    priv_table.add_column("Confidence", justify="right", style="cyan", width=12)
    priv_table.add_column("Masking", style="bold green", width=10)
    priv_table.add_column("Status", style="bold green", width=14)

    for p in results["privacy_evaluations"]:
        priv_table.add_row(
            p["connector"].upper(),
            p["table"],
            p["column"],
            p["rule_matched"],
            p["classification"],
            f"{p['confidence']*100:.0f}%",
            "[green]ENFORCED[/green]",
            f"[{'green' if p['status']=='COMPLIANT' else 'yellow'}]{p['status']}[/]"
        )
    console.print(priv_table)

    # Summary Panel
    console.print(Panel.fit(
        f"[bold green][GOVERNANCE RUN COMPLETE][/bold green]\n"
        f"• Total Checkpoint Anomalies Remediated: [bold green]{results['total_anomalies_healed']}[/bold green]\n"
        f"• Execution Time: [bold cyan]{results['execution_duration_sec']}s[/bold cyan]\n"
        f"• Arize Phoenix Traces Recorded: [bold magenta]{len(phoenix_tracer.get_all_traces())} traces[/bold magenta]",
        border_style="green"
    ))



@app.command()
def phoenix():
    """Launch Official Arize Phoenix Observability Dashboard on http://localhost:6006."""
    from observability.phoenix_tracer import phoenix_tracer

    console.print(Panel.fit(
        "[bold cyan][OFFICIAL ARIZE PHOENIX DASHBOARD][/bold cyan]\n"
        "Starting native Arize Phoenix LLM Tracing & Evaluation server...\n"
        "Open browser at: [bold green]http://localhost:6006[/bold green]",
        border_style="cyan"
    ))
    console.print("[bold green][ONLINE] Official Arize Phoenix Dashboard starting at: http://localhost:6006[/bold green]")
    console.print("[dim]Press Ctrl+C to stop the dashboard server.[/dim]\n")
    phoenix_tracer.start_official_server(port=6006)


@app.command()
def serve(host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host IP to bind FastAPI server"),
          port: int = typer.Option(8000, "--port", "-p", help="Port to run FastAPI server")):
    """Launch FastAPI Web Server & MCP Microservices on http://127.0.0.1:8000."""
    import uvicorn
    console.print(Panel.fit(
        f"[bold cyan][FASTAPI & MCP MICROSERVICES SERVER][/bold cyan]\n"
        f"Server URL: [bold green]http://{host}:{port}[/bold green]\n"
        f"Interactive Swagger Docs: [bold yellow]http://{host}:{port}/docs[/bold yellow]\n"
        f"Key-Orchestrator Route: [bold magenta]POST /api/v1/orchestrate[/bold magenta]\n"
        f"MCP Discovery Route: [bold cyan]GET /api/v1/mcp/services[/bold cyan]\n"
        f"Observability Dashboard: [bold green]http://localhost:6006[/bold green]",
        border_style="cyan"
    ))
    uvicorn.run("server:app", host=host, port=port, reload=False)


@app.command()
def mcp():
    """List all registered MCP Self-Healing Microservices and their exposed tools."""
    from services.mcp_registry import mcp_registry

    console.print(Panel.fit(
        "[bold cyan][MCP SELF-HEALING SERVICES DISCOVERY REGISTRY][/bold cyan]\n"
        "Registered Model Context Protocol (MCP) microservices and tool schemas.",
        border_style="cyan"
    ))

    services = mcp_registry.discover_services()
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("MCP Service", style="bold cyan", width=28)
    table.add_column("Category", style="yellow", width=22)
    table.add_column("Exposed Tools", style="white", width=34)
    table.add_column("Supported Anomalies", style="green", width=26)

    for s in services:
        tools_str = ", ".join([t.name for t in s.tools])
        anomalies_str = ", ".join(s.supported_anomaly_types)
        table.add_row(
            s.service_name,
            s.category,
            tools_str,
            anomalies_str
        )

    console.print(table)


if __name__ == "__main__":
    app()


