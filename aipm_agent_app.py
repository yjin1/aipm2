from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from planning_scheduling_agent import PlanningSchedulingAgent, write_findings, write_timing_divergences


# What: Local web app for running the AIPM planning/scheduling agent.
# Purpose: Lets users choose strategy/model and run the agent without typing CLI commands.

# What: Available scheduling strategy options.
# Purpose: Keeps the browser form aligned with PlanningSchedulingAgent.generate_schedule().
STRATEGIES = [
    ("baseline", "Baseline forward scheduler"),
    ("reference_learning", "Reference-learning timing"),
    ("field_repair", "Field repair"),
    ("ortools_cp", "OR-Tools CP-SAT"),
    ("ortools_precedence", "OR-Tools + learned precedence"),
    ("reference_replay", "Reference replay/calibration"),
]

# What: Suggested model options.
# Purpose: Gives quick choices while still allowing a custom model string.
MODELS = [
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.5",
]


# What: HTTP request handler for the local app.
# Purpose: Serves the control page, runs the agent, and exposes generated artifacts.
class AIPMAgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "AIPMAgentApp/0.1"

    # What: GET route dispatcher.
    # Purpose: Handles page rendering, report redirects, and static output files.
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_home())
            return
        if parsed.path == "/report":
            self._send_file(Path("outputs/agent_schedule_report.html"), "text/html; charset=utf-8")
            return
        if parsed.path == "/findings":
            self._send_file(Path("outputs/agent_findings.txt"), "text/plain; charset=utf-8")
            return
        if parsed.path == "/divergences":
            self._send_file(Path("outputs/agent_timing_divergences.csv"), "text/csv; charset=utf-8")
            return
        if parsed.path == "/schedule":
            self._send_file(Path("outputs/agent_middle_schedule.csv"), "text/csv; charset=utf-8")
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    # What: POST route dispatcher.
    # Purpose: Runs the agent from submitted form values.
    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/run":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body)
        strategy = _first(form, "strategy", "ortools_cp")
        model = _first(form, "model", "gpt-5.4-mini")
        custom_model = _first(form, "custom_model", "").strip()
        api_key = _first(form, "api_key", "").strip()
        use_openai = bool(api_key)
        selected_model = custom_model or model

        if strategy not in {item[0] for item in STRATEGIES}:
            self._send_html(render_home(error=f"Unknown strategy: {strategy}"))
            return

        try:
            result = run_agent(
                strategy=strategy,
                use_openai=use_openai,
                model=selected_model,
                api_key=api_key or None,
            )
        except Exception as exc:
            self._send_html(render_home(error=str(exc)))
            return

        self._send_html(render_home(result=result, selected_strategy=strategy, selected_model=selected_model))

    # What: HTTP log override.
    # Purpose: Keeps terminal logs short while the app is running.
    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    # What: HTML response helper.
    # Purpose: Sends UTF-8 HTML content with a correct content type.
    def _send_html(self, content: str) -> None:
        encoded = content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    # What: File response helper.
    # Purpose: Serves generated output artifacts through the local app.
    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, f"Missing file: {path}")
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


# What: Agent runner used by the web app.
# Purpose: Executes the selected strategy and writes the standard report artifacts.
def run_agent(
    strategy: str,
    use_openai: bool,
    model: str,
    api_key: str | None = None,
) -> dict[str, object]:
    reasoning_client = None
    if use_openai:
        from openai_reasoning_client import OpenAIReasoningClient

        reasoning_client = OpenAIReasoningClient(api_key=api_key)

    agent = PlanningSchedulingAgent(
        data_dir="data",
        reasoning_client=reasoning_client,
        model=model,
    )
    result = agent.solve(
        strategy=strategy,
        output_path="outputs/agent_middle_schedule.csv",
        report_path="outputs/agent_schedule_report.html",
    )
    write_findings(result, "outputs/agent_findings.txt")
    write_timing_divergences(result.analysis.divergences, "outputs/agent_timing_divergences.csv")

    return {
        "strategy": strategy,
        "model": model if use_openai else "offline",
        "schedule_path": str(result.schedule_path),
        "report_path": str(result.report_path),
        "findings": result.analysis.findings,
        "divergence_count": len(result.analysis.divergences),
    }


# What: Home page renderer.
# Purpose: Builds the strategy/model start box and result links.
def render_home(
    result: dict[str, object] | None = None,
    error: str | None = None,
    selected_strategy: str = "ortools_cp",
    selected_model: str = "gpt-5.4-mini",
) -> str:
    strategy_options = "\n".join(
        f'<option value="{escape(value)}" {"selected" if value == selected_strategy else ""}>{escape(label)}</option>'
        for value, label in STRATEGIES
    )
    model_options = "\n".join(
        f'<option value="{escape(model)}" {"selected" if model == selected_model else ""}>{escape(model)}</option>'
        for model in MODELS
    )
    result_html = render_result(result) if result else ""
    error_html = f'<div class="alert error">{escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIPM Agent Runner</title>
  <style>{app_css()}</style>
</head>
<body>
  <main>
    <section class="runner">
      <p class="eyebrow">AIPM Planning and Scheduling Agent</p>
      <h1>Agent Start Box</h1>
      <form action="/run" method="post" id="agent-form">
        <label>
          <span>Scheduling Strategy</span>
          <select name="strategy">{strategy_options}</select>
        </label>
        <label>
          <span>GPT Model</span>
          <select name="model">{model_options}</select>
        </label>
        <label>
          <span>Custom Model</span>
          <input name="custom_model" placeholder="Optional model name" value="">
        </label>
        <label>
          <span>OpenAI API Key</span>
          <input name="api_key" id="api-key" type="password" autocomplete="off" placeholder="Remembered while this page is open">
          <small>GPT diagnosis runs automatically when a key is present. The key is not written to files.</small>
        </label>
        <button type="submit">Run Agent</button>
      </form>
      {error_html}
      {result_html}
    </section>
    <section class="links">
      <h2>Current Outputs</h2>
      <a href="/report" target="_blank">Open Visual Report</a>
      <a href="/findings" target="_blank">Open Findings</a>
      <a href="/divergences" target="_blank">Download Timing Divergences CSV</a>
      <a href="/schedule" target="_blank">Download Generated Schedule CSV</a>
    </section>
  </main>
  <script>
    const apiKeyInput = document.getElementById('api-key');
    const form = document.getElementById('agent-form');
    let rememberedApiKey = '';
    apiKeyInput.addEventListener('input', () => {{
      rememberedApiKey = apiKeyInput.value;
    }});
    form.addEventListener('submit', () => {{
      if (!apiKeyInput.value && rememberedApiKey) {{
        apiKeyInput.value = rememberedApiKey;
      }}
    }});
  </script>
</body>
</html>"""


# What: Result card renderer.
# Purpose: Shows concise run status and GPT/offline findings after execution.
def render_result(result: dict[str, object]) -> str:
    findings = result.get("findings", [])
    finding_items = "\n".join(f"<li>{escape(item)}</li>" for item in findings[:6])
    return f"""<div class="result">
      <h2>Run Complete</h2>
      <div class="grid">
        <p><span>Strategy</span><strong>{escape(result.get("strategy", ""))}</strong></p>
        <p><span>Diagnosis</span><strong>{escape(result.get("model", ""))}</strong></p>
        <p><span>Divergences</span><strong>{escape(result.get("divergence_count", ""))}</strong></p>
      </div>
      <ul>{finding_items}</ul>
      <a class="primary-link" href="/report" target="_blank">View Updated Report</a>
    </div>"""


# What: App stylesheet.
# Purpose: Makes the start box readable and focused without external CSS.
def app_css() -> str:
    return """
    :root { --ink: #0f172a; --muted: #64748b; --line: #dbe3ef; --bg: #f8fafc; --panel: #fff; --blue: #2563eb; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg); }
    main { max-width: 980px; margin: 0 auto; padding: 40px 24px; }
    .runner, .links { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 24px; }
    .links { margin-top: 16px; }
    .eyebrow { margin: 0 0 8px; font-size: 12px; color: var(--blue); font-weight: 800; text-transform: uppercase; }
    h1 { margin: 0 0 24px; font-size: 30px; letter-spacing: 0; }
    h2 { margin: 0 0 14px; font-size: 18px; }
    form { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 16px; align-items: end; }
    label span { display: block; margin-bottom: 6px; color: #334155; font-size: 13px; font-weight: 700; }
    select, input { width: 100%; height: 42px; border: 1px solid var(--line); border-radius: 8px; padding: 0 12px; font-size: 14px; background: #fff; }
    small { display: block; margin-top: 6px; color: var(--muted); font-size: 12px; line-height: 1.35; }
    button { height: 42px; border: 0; border-radius: 8px; color: #fff; background: var(--blue); font-size: 14px; font-weight: 800; cursor: pointer; }
    button:hover { background: #1d4ed8; }
    .alert { margin-top: 16px; padding: 12px; border-radius: 8px; }
    .error { color: #991b1b; background: #fee2e2; border: 1px solid #fecaca; }
    .result { margin-top: 20px; border-top: 1px solid var(--line); padding-top: 18px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .grid p { margin: 0; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: #f8fafc; }
    .grid span { display: block; color: var(--muted); font-size: 12px; }
    .grid strong { display: block; margin-top: 4px; }
    .result ul { padding-left: 20px; line-height: 1.45; }
    .links a, .primary-link { display: inline-flex; margin: 6px 10px 6px 0; color: var(--blue); font-weight: 700; text-decoration: none; }
    .links a:hover, .primary-link:hover { text-decoration: underline; }
    @media (max-width: 720px) { form, .grid { grid-template-columns: 1fr; } main { padding: 24px 16px; } }
    """


# What: Form value helper.
# Purpose: Extracts the first submitted value with a default fallback.
def _first(form: dict[str, list[str]], key: str, default: str) -> str:
    values = form.get(key, [])
    return values[0] if values else default


# What: HTML escaping helper.
# Purpose: Keeps user-visible values safe in generated HTML.
def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


# What: App entry point.
# Purpose: Starts the local browser-accessible agent runner.
def main() -> int:
    parser = argparse.ArgumentParser(description="Start the local AIPM agent runner web app.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), AIPMAgentRequestHandler)
    print(f"AIPM Agent Runner: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping AIPM Agent Runner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
