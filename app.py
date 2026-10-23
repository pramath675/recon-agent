"""RECON Demo Application (Gradio)
Public interactive demo using bundled offline fixtures.
Terminal-inspired visual theme with neon-lime wordmark and real-time active stage highlighting.
No live Nebius API calls; no API keys required.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading
from typing import Generator, Optional, Tuple

import gradio as gr

from recon.agent import run_recon
from recon.config import Config
from recon.llm import FixtureLLM
from recon.verify import VERIFIED, UNVERIFIED

REPO_ROOT = Path(__file__).resolve().parent
PROJECT_DIR = REPO_ROOT / "examples" / "buggy_shop"
BUG_REPORT_FILE = PROJECT_DIR / "bug_report.md"
PRICING_CODE_FILE = PROJECT_DIR / "shop" / "pricing.py"
GOOD_FIXTURES = REPO_ROOT / "examples" / "fixtures" / "good"
BAD_FIXTURES = REPO_ROOT / "examples" / "fixtures" / "bad"

_RUN_LOCK = threading.Lock()

TERMINAL_CSS = """
/* ================= RECON TERMINAL THEME ================= */
:root {
  --recon-bg: #07090e;
  --recon-surface: #0d121a;
  --recon-surface-2: #121924;
  --recon-border: #1a2332;
  --recon-border-highlight: #28374d;
  --recon-lime: #00ff66;
  --recon-lime-dim: #00cc52;
  --recon-lime-glow: rgba(0, 255, 102, 0.35);
  --recon-red: #ff3344;
  --recon-red-glow: rgba(255, 51, 68, 0.35);
  --recon-text: #e2e8f0;
  --recon-text-dim: #8b9bb4;
  --recon-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Courier New', monospace;
}

body, .gradio-container {
  background-color: var(--recon-bg) !important;
  color: var(--recon-text) !important;
  font-family: var(--recon-mono) !important;
}

/* Header & Animated Wordmark */
.recon-terminal-header {
  background: var(--recon-surface);
  border: 1px solid var(--recon-border);
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.7);
}

.recon-wordmark-wrapper {
  position: relative;
  max-width: 680px;
  margin: 0 auto;
  border-radius: 8px;
  overflow: hidden;
}

.recon-wordmark-wrapper svg {
  display: block;
  width: 100%;
  height: auto;
  animation: reconWordmarkPulse 5s ease-in-out infinite alternate;
}

/* Subtle, restrained terminal scan effect */
.recon-wordmark-wrapper::after {
  content: "";
  position: absolute;
  top: -100%;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    to bottom,
    transparent 0%,
    rgba(0, 255, 102, 0.02) 42%,
    rgba(0, 255, 102, 0.12) 50%,
    rgba(0, 255, 102, 0.02) 58%,
    transparent 100%
  );
  pointer-events: none;
  animation: reconScanline 6s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes reconScanline {
  0% { transform: translateY(0%); }
  100% { transform: translateY(200%); }
}

@keyframes reconWordmarkPulse {
  0% { filter: drop-shadow(0 0 4px rgba(0, 255, 102, 0.15)); }
  100% { filter: drop-shadow(0 0 10px rgba(0, 255, 102, 0.35)); }
}

/* Pipeline Stepper Layout: 4 integrated grid columns */
.recon-pipeline {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
  background: #090e15;
  border: 1px solid var(--recon-border);
  border-radius: 6px;
  padding: 0.85rem;
  margin: 1.25rem 0;
}

@media (max-width: 720px) {
  .recon-pipeline {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.pipe-node {
  border-radius: 4px;
  padding: 0.65rem 0.85rem;
  text-align: left;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1),
              border-color 0.2s ease,
              box-shadow 0.2s ease,
              background 0.2s ease;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

/* Neutral stage (when idle or when other stages run) */
.pipe-node-neutral {
  background: #0d131c !important;
  border: 1px solid #1a2332 !important;
}

.pipe-node-neutral:hover {
  transform: translateY(-2px);
  border-color: #2e3e54 !important;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45) !important;
}

/* Active stage (highlighted ONLY while running) */
.pipe-node-active {
  background: rgba(0, 255, 102, 0.12) !important;
  border: 1px solid #00ff66 !important;
  box-shadow: 0 0 16px rgba(0, 255, 102, 0.35) !important;
  animation: stageGlowPulse 2s ease-in-out infinite;
}

@keyframes stageGlowPulse {
  0%, 100% {
    border-color: #00ff66;
    box-shadow: 0 0 14px rgba(0, 255, 102, 0.3);
  }
  50% {
    border-color: #39ff14;
    box-shadow: 0 0 22px rgba(0, 255, 102, 0.55);
  }
}

.pipe-node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.pipe-step-num {
  font-size: 0.7rem;
  letter-spacing: 0.1em;
}

.pipe-label {
  font-size: 0.95rem;
  letter-spacing: 0.08em;
  margin-top: 2px;
}

.pipe-desc {
  font-size: 0.68rem;
  margin-top: 3px;
  line-height: 1.35;
}

.pipe-arrow-inline {
  color: #3b4c66;
  font-size: 0.95rem;
  font-weight: bold;
}

.pipe-arrow-active {
  font-size: 0.62rem;
  background: #00ff66;
  color: #04080c;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 2px;
  letter-spacing: 0.05em;
  animation: activeIndicatorPulse 1.4s ease-in-out infinite;
}

@keyframes activeIndicatorPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(0.98); }
}

.pipe-final-badge {
  font-size: 0.62rem;
  background: #1e293b;
  color: #8b9bb4;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 2px;
  letter-spacing: 0.05em;
}

/* Status Banners */
.status-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.85rem 1.25rem;
  border-radius: 6px;
  margin: 1rem 0;
  font-family: var(--recon-mono);
  border-width: 1px;
  border-style: solid;
  animation: bannerEntrance 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  transition: border-color 0.25s ease, background 0.25s ease, box-shadow 0.25s ease;
}

@keyframes bannerEntrance {
  from {
    opacity: 0.3;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.status-verified {
  background: rgba(0, 255, 102, 0.08);
  border-color: var(--recon-lime);
  box-shadow: 0 0 16px var(--recon-lime-glow);
  animation: bannerEntrance 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards,
             verifiedSubtlePulse 3.5s ease-in-out infinite;
}

@keyframes verifiedSubtlePulse {
  0%, 100% { box-shadow: 0 0 14px rgba(0, 255, 102, 0.25); }
  50% { box-shadow: 0 0 22px rgba(0, 255, 102, 0.45); }
}

.status-verified .status-title {
  color: var(--recon-lime);
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.status-verified .status-badge-pill {
  background: var(--recon-lime);
  color: #04080c;
  font-weight: 800;
  font-size: 0.72rem;
  padding: 0.2rem 0.55rem;
  border-radius: 3px;
  letter-spacing: 0.08em;
}

.status-unverified {
  background: rgba(255, 51, 68, 0.08);
  border-color: var(--recon-red);
  box-shadow: 0 0 16px var(--recon-red-glow);
  animation: bannerEntrance 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards,
             unverifiedSubtlePulse 3.5s ease-in-out infinite;
}

@keyframes unverifiedSubtlePulse {
  0%, 100% { box-shadow: 0 0 14px rgba(255, 51, 68, 0.25); }
  50% { box-shadow: 0 0 22px rgba(255, 51, 68, 0.45); }
}

.status-unverified .status-title {
  color: var(--recon-red);
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.status-unverified .status-badge-pill {
  background: var(--recon-red);
  color: #ffffff;
  font-weight: 800;
  font-size: 0.72rem;
  padding: 0.2rem 0.55rem;
  border-radius: 3px;
  letter-spacing: 0.08em;
}

.status-running {
  background: rgba(0, 255, 102, 0.05);
  border-color: #00ff66;
  box-shadow: 0 0 14px var(--recon-lime-glow);
  position: relative;
  overflow: hidden;
  animation: bannerEntrance 0.25s ease forwards;
}

.status-running::after {
  content: "";
  position: absolute;
  bottom: 0;
  left: -100%;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, #00ff66, transparent);
  animation: runningProgressBar 1.8s ease-in-out infinite;
}

@keyframes runningProgressBar {
  0% { transform: translateX(0%); }
  100% { transform: translateX(200%); }
}

.status-running .status-title {
  color: #00ff66;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.status-running .status-badge-pill {
  background: #00ff66;
  color: #05090e;
  font-weight: 800;
  font-size: 0.72rem;
  padding: 0.2rem 0.55rem;
  border-radius: 3px;
  letter-spacing: 0.08em;
}

.status-dot-pulse {
  display: inline-block;
  color: #00ff66;
  margin-right: 8px;
  animation: dotPulse 1.2s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.35); opacity: 0.6; }
}

.status-ready {
  background: var(--recon-surface);
  border-color: var(--recon-border);
}

.status-ready .status-title {
  color: var(--recon-text-dim);
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.status-ready .status-badge-pill {
  background: #1e293b;
  color: var(--recon-text-dim);
  font-size: 0.72rem;
  padding: 0.2rem 0.55rem;
  border-radius: 3px;
}

/* Action Buttons with Smooth Hover/Focus Feedback */
.btn-run-good {
  background: var(--recon-lime) !important;
  color: #05090e !important;
  font-weight: 800 !important;
  font-family: var(--recon-mono) !important;
  letter-spacing: 0.04em !important;
  border: 1px solid transparent !important;
  transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1),
              box-shadow 0.18s ease,
              background-color 0.18s ease !important;
  cursor: pointer !important;
}

.btn-run-good:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0, 255, 102, 0.45) !important;
}

.btn-run-good:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(0, 255, 102, 0.3) !important;
}

.btn-run-good:focus-visible {
  outline: 2px solid #00ff66 !important;
  outline-offset: 2px !important;
}

.btn-run-bad {
  background: #161c26 !important;
  color: #ff6677 !important;
  font-weight: 800 !important;
  font-family: var(--recon-mono) !important;
  border: 1px solid var(--recon-red) !important;
  letter-spacing: 0.04em !important;
  transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1),
              box-shadow 0.18s ease,
              background-color 0.18s ease,
              border-color 0.18s ease !important;
  cursor: pointer !important;
}

.btn-run-bad:hover {
  transform: translateY(-2px);
  background: #1f2533 !important;
  box-shadow: 0 4px 18px rgba(255, 51, 68, 0.4) !important;
}

.btn-run-bad:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(255, 51, 68, 0.25) !important;
}

.btn-run-bad:focus-visible {
  outline: 2px solid var(--recon-red) !important;
  outline-offset: 2px !important;
}

/* Code and Form Fields */
pre, code, textarea, input {
  background-color: #090e15 !important;
  color: #e2e8f0 !important;
  border-color: var(--recon-border) !important;
  font-family: var(--recon-mono) !important;
}

/* Accessibility: Respect prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
  .recon-wordmark-wrapper::after,
  .status-running::after {
    display: none !important;
  }
}
"""


def load_file_content(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        return f"Error reading {path.name}: {err}"


def render_pipeline_html(active_stage: Optional[str] = None) -> str:
    stages = [
        ("01", "BASELINE", "Run existing suite (all must pass)"),
        ("02", "REPRODUCE", "Generate test (must fail on original)"),
        ("03", "PATCH", "Apply search/replace to temp copy"),
        ("04", "VERIFY", "Rerun repro + existing (0 regressions)"),
    ]

    nodes_html = []
    for i, (num, label, desc) in enumerate(stages):
        is_active = (active_stage == label)
        is_last = (i == len(stages) - 1)

        if is_active:
            node_class = "pipe-node pipe-node-active"
            num_style = "color: #00ff66; font-weight: 800;"
            label_style = "color: #00ff66; font-weight: 800;"
            desc_style = "color: #e2e8f0;"
            header_right = (
                "<span class='pipe-arrow-active'>● RUNNING</span>"
                if is_last
                else "<span class='pipe-arrow-active'>● RUNNING →</span>"
            )
        else:
            node_class = "pipe-node pipe-node-neutral"
            num_style = "color: #64748b; font-weight: 600;"
            label_style = "color: #94a3b8; font-weight: 700;"
            desc_style = "color: #64748b;"
            header_right = (
                "<span class='pipe-final-badge'>FINAL</span>"
                if is_last
                else "<span class='pipe-arrow-inline'>→</span>"
            )

        node = f"""
        <div class="{node_class}">
          <div class="pipe-node-header">
            <span class="pipe-step-num" style="{num_style}">STAGE {num}</span>
            {header_right}
          </div>
          <div class="pipe-label" style="{label_style}">{label}</div>
          <div class="pipe-desc" style="{desc_style}">{desc}</div>
        </div>
        """
        nodes_html.append(node)

    return f"""
    <div class="recon-pipeline">
      {''.join(nodes_html)}
    </div>
    """


def render_status_html(status: str, extra: str = "") -> str:
    if status == VERIFIED:
        return """
        <div class="status-banner status-verified">
          <div>
            <span style="color:#00ff66; margin-right:8px;">[✔]</span>
            <span class="status-title">STATUS: VERIFIED</span>
          </div>
          <span class="status-badge-pill">EVIDENCE SATISFIED</span>
        </div>
        """
    elif status == UNVERIFIED:
        return """
        <div class="status-banner status-unverified">
          <div>
            <span style="color:#ff3344; margin-right:8px;">[✖]</span>
            <span class="status-title">STATUS: UNVERIFIED</span>
          </div>
          <span class="status-badge-pill">REGRESSION / TAMPERING DETECTED</span>
        </div>
        """
    elif status == "STAGE_RUNNING":
        return f"""
        <div class="status-banner status-running">
          <div>
            <span class="status-dot-pulse">●</span>
            <span class="status-title">{extra}</span>
          </div>
          <span class="status-badge-pill">STAGE ACTIVE</span>
        </div>
        """
    elif status == "BUSY":
        return """
        <div class="status-banner status-ready">
          <div>
            <span style="color:goldenrod; margin-right:8px;">[⏳]</span>
            <span class="status-title">STATUS: BUSY</span>
          </div>
          <span class="status-badge-pill">RUN IN PROGRESS</span>
        </div>
        """
    else:
        return """
        <div class="status-banner status-ready">
          <div>
            <span style="color:#8b9bb4; margin-right:8px;">[○]</span>
            <span class="status-title">STATUS: READY</span>
          </div>
          <span class="status-badge-pill">SELECT A SCENARIO BELOW</span>
        </div>
        """


def run_fixture_demo(
    fixture_type: str,
) -> Generator[Tuple[str, str, str, str, str, str, str], None, None]:
    if not _RUN_LOCK.acquire(blocking=False):
        yield (
            render_pipeline_html(None),
            render_status_html("BUSY"),
            "Another test execution is currently running. Please wait a few seconds and try again.",
            "",
            "",
            "",
            "{}",
        )
        return

    try:
        if fixture_type == "good":
            fixture_dir = GOOD_FIXTURES
            mode_desc = "Good Fixture (replays correct model patch)"
        elif fixture_type == "bad":
            fixture_dir = BAD_FIXTURES
            mode_desc = "Bad Fixture (replays faulty patch to test integrity verification)"
        else:
            yield (
                render_pipeline_html(None),
                render_status_html("ERROR"),
                "Unknown fixture type requested.",
                "",
                "",
                "",
                "{}",
            )
            return

        if not fixture_dir.is_dir():
            yield (
                render_pipeline_html(None),
                render_status_html("ERROR"),
                f"Fixture directory not found: {fixture_dir}",
                "",
                "",
                "",
                "{}",
            )
            return

        out_dir = REPO_ROOT / "demo_output"
        bug_text = load_file_content(BUG_REPORT_FILE)
        cfg = Config(test_timeout=30, repeats=2)
        llm = FixtureLLM(fixture_dir)

        q: queue.Queue = queue.Queue()
        logs: list[str] = [f"Starting RECON demo in offline mode: {mode_desc}"]

        def capture_say(msg: str) -> None:
            q.put(("log", msg))

        def worker() -> None:
            try:
                rep = run_recon(PROJECT_DIR, bug_text, cfg, llm, out_dir, say=capture_say)
                q.put(("done", rep))
            except Exception as exc:
                q.put(("error", exc))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        active_stage = "BASELINE"
        yield (
            render_pipeline_html(active_stage),
            render_status_html("STAGE_RUNNING", "STAGE 01: BASELINE (Preparing & running existing tests...)"),
            "Running verification pipeline...",
            "",
            "",
            "\n".join(logs),
            "{}",
        )

        while True:
            try:
                event_type, payload = q.get(timeout=0.08)
            except queue.Empty:
                if not thread.is_alive():
                    break
                continue

            if event_type == "log":
                msg = payload
                logs.append(msg)
                new_stage = active_stage
                stage_label = ""
                if "[1/5]" in msg or "[2/5]" in msg:
                    new_stage = "BASELINE"
                    stage_label = "STAGE 01: BASELINE (Running existing tests...)"
                elif "[3/5]" in msg:
                    new_stage = "REPRODUCE"
                    stage_label = "STAGE 02: REPRODUCE (Generating & running repro test...)"
                elif "[4/5]" in msg:
                    new_stage = "PATCH"
                    stage_label = "STAGE 03: PATCH (Generating search/replace patch...)"
                elif "[5/5]" in msg:
                    new_stage = "VERIFY"
                    stage_label = "STAGE 04: VERIFY (Testing in temp copy with repro & existing tests...)"

                active_stage = new_stage
                status_text = stage_label or f"STAGE {active_stage} (In progress...)"
                yield (
                    render_pipeline_html(active_stage),
                    render_status_html("STAGE_RUNNING", status_text),
                    "Running verification pipeline...",
                    "",
                    "",
                    "\n".join(logs),
                    "{}",
                )

            elif event_type == "done":
                report = payload
                status = report.get("status", "UNKNOWN")
                reasons = "\n".join(f"- {r}" for r in report.get("reasons", []))
                if not reasons:
                    reasons = "All verification checks passed cleanly." if status == VERIFIED else "No reasons reported."

                diff = report.get("patch", {}).get("diff", "") or "(No patch diff produced)"
                repro_test = report.get("generated_test", "") or "(No reproduction test code produced)"
                json_report = json.dumps(report, indent=2)

                # Return ALL STAGES to neutral upon completion
                yield (
                    render_pipeline_html(None),
                    render_status_html(status),
                    reasons,
                    diff,
                    repro_test,
                    "\n".join(logs),
                    json_report,
                )
                break

            elif event_type == "error":
                exc = payload
                yield (
                    render_pipeline_html(None),
                    render_status_html("ERROR"),
                    f"Internal execution error: {type(exc).__name__}: {exc}",
                    "",
                    "",
                    "\n".join(logs),
                    "{}",
                )
                break

        thread.join(timeout=2.0)

    finally:
        _RUN_LOCK.release()


def create_ui() -> gr.Blocks:
    bug_text = load_file_content(BUG_REPORT_FILE)
    pricing_code = load_file_content(PRICING_CODE_FILE)

    with gr.Blocks(title="RECON: Verification-First Bug Fixing") as demo:
        # Inject custom styling directly
        gr.HTML(f"<style>{TERMINAL_CSS}</style>")

        # Terminal Header with Large Bold Block RECON Wordmark
        wordmark_svg = load_file_content(REPO_ROOT / "docs" / "recon_wordmark.svg")
        gr.HTML(
            f"""
            <div class="recon-terminal-header">
              <div class="recon-wordmark-wrapper">
                {wordmark_svg}
              </div>
              <div style="font-size: 0.8rem; color: #8b9bb4; margin-top: 0.85rem; line-height: 1.5; border-top: 1px solid #141c28; padding-top: 0.75rem; text-align: center;">
                AI coding agents often declare &quot;fixed it!&quot; and move on. RECON does not take their word for it.
                It only reports <span style="color:#00ff66; font-weight:bold;">VERIFIED</span> when real pytest runs prove the bug existed and was resolved without regressions.
              </div>
            </div>
            """
        )

        # Baseline -> Reproduce -> Patch -> Verify Pipeline (Neutral when idle, highlights active stage while running)
        pipeline_output = gr.HTML(value=render_pipeline_html(None))

        with gr.Accordion("📂 Inspect Target: examples/buggy_shop (Read-Only)", open=False):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### Bug Report (`examples/buggy_shop/bug_report.md`)")
                    gr.Markdown(f"```markdown\n{bug_text}\n```")
                with gr.Column():
                    gr.Markdown("#### Flawed Source (`shop/pricing.py`)")
                    gr.Code(value=pricing_code, language="python", interactive=False)

        gr.Markdown("### Interactive Verification Runner")
        gr.Markdown("Execute RECON's verification engine on the bundled target in a clean temporary copy:")

        with gr.Row():
            btn_good = gr.Button(
                "▶ Run Good Fixture (Expected: VERIFIED)",
                elem_classes=["btn-run-good"],
                scale=1,
            )
            btn_bad = gr.Button(
                "▶ Run Bad Fixture (Expected: UNVERIFIED)",
                elem_classes=["btn-run-bad"],
                scale=1,
            )

        status_output = gr.HTML(value=render_status_html("READY"))

        reasons_output = gr.Textbox(
            label="Verification Reasons & Checks",
            placeholder="Checks and verification criteria will be reported here...",
            lines=3,
            interactive=False,
        )

        with gr.Tabs():
            with gr.TabItem("Proposed Patch Diff"):
                diff_output = gr.Code(label="Unified Diff", language=None, interactive=False)
            with gr.TabItem("Generated Repro Test"):
                repro_output = gr.Code(label="Reproduction Test (test_recon_repro.py)", language="python", interactive=False)
            with gr.TabItem("Execution Console Log"):
                logs_output = gr.Code(label="Pipeline Steps [1/5] - [5/5]", language="shell", interactive=False)
            with gr.TabItem("Full JSON Report"):
                json_output = gr.Code(label="recon_report.json", language="json", interactive=False)

        def run_good() -> Generator[Tuple[str, str, str, str, str, str, str], None, None]:
            yield from run_fixture_demo("good")

        def run_bad() -> Generator[Tuple[str, str, str, str, str, str, str], None, None]:
            yield from run_fixture_demo("bad")

        btn_good.click(
            fn=run_good,
            inputs=[],
            outputs=[
                pipeline_output,
                status_output,
                reasons_output,
                diff_output,
                repro_output,
                logs_output,
                json_output,
            ],
        )

        btn_bad.click(
            fn=run_bad,
            inputs=[],
            outputs=[
                pipeline_output,
                status_output,
                reasons_output,
                diff_output,
                repro_output,
                logs_output,
                json_output,
            ],
        )

        gr.HTML(
            """
            <div style="font-size: 0.75rem; color: #64748b; margin-top: 1.5rem; border-top: 1px solid #1a2332; padding-top: 0.75rem;">
              • <strong>Secure Execution</strong>: No live external API calls are made; no API keys required. Live model runs on Nebius Token Factory are shown in the submission video.<br/>
              • <strong>Hosting Notice</strong>: Free Hugging Face Spaces sleep after periods of inactivity. Verify your compute tier in HF account settings.<br/>
              • <em>Passing tests are evidence that the reported behaviour was fixed and existing tests still pass. They are not a mathematical proof of correctness.</em>
            </div>
            """
        )

    return demo


demo = create_ui()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
