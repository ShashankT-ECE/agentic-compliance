#!/usr/bin/env bash
# =============================================================================
# Agentic Compliance — End-to-End Demo Runner
# =============================================================================
#
# Runs the complete compliance pipeline in-process (no external backend
# server needed).  Uses MockLLMClient with canned responses so the demo
# works reliably without a real LLM API key.
#
# Flow:
#   sample_circular.pdf → Parser → FSM Extractor → HITL Gate
#   → Auto-Approve → Evaluator → Scoreboard → Report → Hash-Chain Verify
#
# Usage:
#   chmod +x scripts/run_demo.sh
#   ./scripts/run_demo.sh
#
# Exit codes:
#   0 — demo completed successfully
#   1 — dependency check failed (missing Python, venv, or fixture)
#   2 — pipeline execution failed
#   3 — hash-chain verification failed
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/backend/.venv/bin/python3"
CIRCULAR_PDF="$PROJECT_DIR/backend/tests/fixtures/sample_circular.pdf"
TELEMETRY_JSON="$PROJECT_DIR/backend/tests/fixtures/sample_telemetry.json"
CIRCULAR_REF="SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/57"

# ---- Colour helpers ---------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Colour

banner()  { echo -e "\n${BOLD}${CYAN}═══ $* ═══${NC}"; }
ok()      { echo -e "  ${GREEN}✓${NC} $*"; }
warn()    { echo -e "  ${YELLOW}⚠${NC} $*"; }
fail()    { echo -e "  ${RED}✗${NC} $*"; }
info()    { echo -e "  ${CYAN}→${NC} $*"; }
detail()  { echo -e "    $*"; }

# =============================================================================
# Phase 0 — Dependency checks
# =============================================================================

banner "Phase 0 — Dependency Checks"
echo ""

# Python venv
if [ ! -f "$VENV_PYTHON" ]; then
    fail "Python virtualenv not found at $VENV_PYTHON"
    info "Run: cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi
ok "Python venv: $VENV_PYTHON"

# Circular PDF fixture
if [ ! -f "$CIRCULAR_PDF" ]; then
    fail "Demo circular PDF not found at $CIRCULAR_PDF"
    exit 1
fi
ok "Circular PDF: $CIRCULAR_PDF"

# Telemetry fixture
if [ ! -f "$TELEMETRY_JSON" ]; then
    fail "Demo telemetry fixture not found at $TELEMETRY_JSON"
    exit 1
fi
ok "Telemetry fixture: $TELEMETRY_JSON"

echo ""
banner "Phase 1 — Pipeline Execution"
echo ""

# =============================================================================
# The demo runs as an inline Python script using the project venv.
# We use a heredoc so the script is self-contained — no extra files needed.
# =============================================================================

"$VENV_PYTHON" - "$PROJECT_DIR" "$CIRCULAR_PDF" "$TELEMETRY_JSON" "$CIRCULAR_REF" << 'PYEOF'
import asyncio, json, os, sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(sys.argv[1])
CIRCULAR_PDF  = sys.argv[2]
TELEMETRY_JSON = sys.argv[3]
CIRCULAR_REF  = sys.argv[4]

sys.path.insert(0, str(PROJECT_DIR / "backend"))

# ── Canned LLM responses (same as integration tests) ─────────────────────

PARSER_RESPONSE = json.dumps([
    {
        "clause_id": "CIRC-2025-057-CL-01",
        "circular_ref": CIRCULAR_REF,
        "clause_text": "The TMs/CMs shall be required to collect margins (except VaR margins and ELM) from their clients by the settlement day.",
        "obligation_type": "timeline",
        "timeline_params": {"offset": 1, "grace_period": 0, "unit": "days"},
        "effective_date": "2025-04-28",
        "applicable_entities": ["trading_member", "clearing_member"],
    },
    {
        "clause_id": "CIRC-2025-057-CL-02",
        "circular_ref": CIRCULAR_REF,
        "clause_text": "The TMs/CMs in cash segment are required to mandatorily collect upfront VaR margins and ELM from their clients in advance of trade.",
        "obligation_type": "timeline",
        "timeline_params": {"offset": 0, "grace_period": 0, "unit": "days"},
        "effective_date": "2025-04-28",
        "applicable_entities": ["trading_member", "clearing_member"],
    },
])

FSM_RESPONSE = json.dumps([
    {
        "obligation_ref": "CIRC-2025-057-CL-01",
        "circular_ref": CIRCULAR_REF,
        "states": [
            {"name": "PENDING", "description": "Trade executed; margin collection window open"},
            {"name": "DUE", "description": "Settlement day approaching"},
            {"name": "COMPLIANT", "description": "Margins collected by settlement day"},
            {"name": "LATE", "description": "Settlement day passed without full margin collection"},
            {"name": "NON_COMPLIANT", "description": "Penalty assessed for non-collection"},
        ],
        "initial_state": "PENDING",
        "transitions": [
            {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "margin_report_filed", "conditions": None},
            {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "trade_executed", "conditions": None},
            {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
            {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "margin_report_filed", "conditions": None},
            {"from_state": "DUE", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
            {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
        ],
        "timeline_rules": [
            {"start_event": "trade_executed", "deadline_offset": 1, "grace_period": 0, "time_unit": "days", "overdue_transition": "LATE"},
        ],
        "metadata": {"clause_text": "...", "obligation_type": "timeline"},
    },
    {
        "obligation_ref": "CIRC-2025-057-CL-02",
        "circular_ref": CIRCULAR_REF,
        "states": [
            {"name": "PENDING", "description": "Margin call issued; VaR/ELM collection required before trade"},
            {"name": "DUE", "description": "Trade imminent; collection window narrowing"},
            {"name": "COMPLIANT", "description": "VaR margins and ELM collected in advance of trade"},
            {"name": "LATE", "description": "Trade executed without upfront VaR/ELM collection"},
            {"name": "NON_COMPLIANT", "description": "Penalty assessed for failure to collect upfront margins"},
        ],
        "initial_state": "PENDING",
        "transitions": [
            {"from_state": "PENDING", "to_state": "COMPLIANT", "trigger_event": "var_margin_collected", "conditions": {"timing": "advance_of_trade"}},
            {"from_state": "PENDING", "to_state": "DUE", "trigger_event": "trade_executed", "conditions": None},
            {"from_state": "PENDING", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
            {"from_state": "DUE", "to_state": "COMPLIANT", "trigger_event": "var_margin_collected", "conditions": {"timing": "advance_of_trade"}},
            {"from_state": "DUE", "to_state": "LATE", "trigger_event": "deadline_elapsed", "conditions": None},
            {"from_state": "LATE", "to_state": "NON_COMPLIANT", "trigger_event": "grace_expired", "conditions": None},
        ],
        "timeline_rules": [
            {"start_event": "trade_executed", "deadline_offset": 0, "grace_period": 0, "time_unit": "days", "overdue_transition": "LATE"},
        ],
        "metadata": {"clause_text": "...", "obligation_type": "timeline"},
    },
])

# ── Multi-response mock LLM ──────────────────────────────────────────────

from app.utils.llm_client import LLMClient

class MultiMockLLMClient(LLMClient):
    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.calls = []

    async def generate(self, system_prompt: str, user_message: str, *, temperature: float = 0.1) -> str:
        if self._idx >= len(self._responses):
            raise RuntimeError(f"Exhausted after {len(self._responses)} calls")
        self.calls.append({"system_prompt": system_prompt[:200], "user_message": user_message[:200]})
        r = self._responses[self._idx]
        self._idx += 1
        return r

# ── Helpers ──────────────────────────────────────────────────────────────

from app.models.fsm import HybridFSM
from app.models.locked_fsm import LockedFSM, LockStatus
from app.models.scoreboard import HashLink
from app.models.telemetry import TelemetryEvent
from app.utils.hash_chain import compute_hash, verify_chain
from app.utils.llm_client import MockLLMClient

_ok = "\033[0;32m✓\033[0m"
_fail = "\033[0;31m✗\033[0m"
_info = "\033[0;36m→\033[0m"

async def main():
    from app.pipeline.runner import PipelineRunner, _set_store
    from app.pipeline.nodes.hitl_gate import load_locked_fsms, _LOCKED_DATA_DIR

    # ── Step 1: Trigger pipeline ────────────────────────────────────────
    print(f"{_info} Triggering pipeline with demo circular PDF ...")
    print(f"    Circular: {CIRCULAR_REF}")
    print(f"    PDF:      {CIRCULAR_PDF}")

    _set_store({})
    llm = MultiMockLLMClient(PARSER_RESPONSE, FSM_RESPONSE)
    runner = PipelineRunner(llm_client=llm)

    # Load telemetry
    telemetry_data = json.loads(Path(TELEMETRY_JSON).read_text())
    telemetry_events = [TelemetryEvent.model_validate(r) for r in telemetry_data["records"]]
    print(f"    Telemetry: {len(telemetry_events)} events loaded")

    state = await runner.start(
        circular_path=CIRCULAR_PDF,
        circular_id=CIRCULAR_REF,
        telemetry_events=telemetry_events,
    )

    run_id = state.run_id
    print(f"\n  {_ok} Pipeline started — run_id: {run_id}")
    print(f"    Status:   {state.status.value}")
    print(f"    Clauses:  {len(state.obligation_clauses)} extracted")
    print(f"    FSMs:     {len(state.extracted_fsms)} extracted")

    # ── Step 2: HITL queue ──────────────────────────────────────────────
    print(f"\n{_info} Loading HITL review queue ...")
    locked = load_locked_fsms(run_id, data_dir=_LOCKED_DATA_DIR)
    print(f"  {_ok} HITL queue: {len(locked)} FSM(s) awaiting review")

    for i, lf in enumerate(locked):
        print(f"    [{i+1}] {lf.locked_fsm_id}")
        print(f"        Obligation: {lf.obligation_ref}")
        print(f"        States:     {len(lf.original_fsm.states)} states, "
              f"{len(lf.original_fsm.transitions)} transitions, "
              f"{len(lf.original_fsm.timeline_rules)} timeline rule(s)")
        print(f"        Status:     {lf.status.value}")

    # ── Step 3: Auto-approve FSMs ───────────────────────────────────────
    print(f"\n{_info} Auto-approving all FSMs at HITL gate ...")

    approved: list[LockedFSM] = []
    for lf in locked:
        fsm = deepcopy(lf)
        fsm.status = LockStatus.APPROVED
        fsm.reviewer = "demo-script"
        fsm.reviewed_at = datetime.now(timezone.utc)
        fsm.review_comments = "Auto-approved for demo — correct as extracted."

        data_hash = compute_hash(fsm.original_fsm.model_dump_json(exclude_none=True))
        fsm.integrity_hash = data_hash
        preimage = f"0{data_hash}{'0' * 64}"
        fsm.hash_link = HashLink(
            index=0, data_hash=data_hash,
            previous_hash="0" * 64, link_hash=compute_hash(preimage),
        )
        approved.append(fsm)
        print(f"  {_ok} Approved {lf.obligation_ref} → integrity_hash={data_hash[:16]}...")

    # ── Step 4: Resume → Evaluator → Scoreboard ─────────────────────────
    print(f"\n{_info} Resuming pipeline — evaluator → scoreboard ...")
    final_state = await runner.resume(run_id, approved)

    print(f"  {_ok} Pipeline status: {final_state.status.value}")

    # ── Step 5: Verdicts ────────────────────────────────────────────────
    verdicts = final_state.compliance_verdicts
    print(f"\n{_info} Compliance Verdicts: {len(verdicts)} generated")

    by_broker: dict[str, list] = {}
    for v in verdicts:
        by_broker.setdefault(v.broker_id, []).append(v)

    for bid, vs in sorted(by_broker.items()):
        compliant = sum(1 for v in vs if str(v.status.value) == "compliant")
        non = sum(1 for v in vs if str(v.status.value) == "non_compliant")
        pending = sum(1 for v in vs if str(v.status.value) == "pending")
        rate = compliant / max(len(vs), 1) * 100
        icon = _ok if rate >= 80 else (_fail if rate < 50 else _info)
        print(f"  {icon} {bid}: {compliant}C / {non}N / {pending}P — {rate:.0f}% compliant")

    # ── Step 6: Scoreboard ──────────────────────────────────────────────
    scoreboard = final_state.scoreboard
    assert scoreboard is not None
    print(f"\n{_info} Scoreboard: {scoreboard.scoreboard_id}")
    print(f"    Circular:     {scoreboard.circular_id}")
    print(f"    Generated:    {scoreboard.generated_at}")
    print(f"    Brokers:      {len(scoreboard.broker_summaries)}")

    for b in scoreboard.broker_summaries:
        pct = b.compliance_rate * 100
        color = "\033[0;32m" if pct >= 80 else ("\033[0;31m" if pct < 50 else "\033[1;33m")
        print(f"    {color}{b.broker_id}: {b.compliant}/{b.total_obligations} "
              f"({pct:.1f}%) → {b.obligation_details[0].evidence_summary if b.obligation_details else '—'}\033[0m")

    # ── Step 7: Hash chain verification ─────────────────────────────────
    chain = scoreboard.hash_chain
    assert chain is not None

    verified = verify_chain(chain)
    if verified:
        print(f"\n  {_ok} Hash chain VERIFIED — {chain.length} link(s), root={chain.root_hash[:16]}...")
    else:
        print(f"\n  {_fail} Hash chain FAILED verification")
        sys.exit(3)

    # Tamper test
    from copy import deepcopy as dc
    tampered = dc(chain)
    if tampered.chain:
        tampered.chain[-1].link_hash = "f" * 64
    tamper_ok = not verify_chain(tampered)
    if tamper_ok:
        print(f"  {_ok} Tamper detection: confirmed (modified chain fails verification)")
    else:
        print(f"  {_fail} Tamper detection: FAILED (modified chain still verifies)")
        sys.exit(3)

    # ── Step 8: Report ──────────────────────────────────────────────────
    from app.pipeline.runner import get_run_state
    from app.api.routes.reports import _set_report_store, _get_report_store
    _set_report_store({})

    # Use the generate-report logic directly
    stored_state = get_run_state(run_id)
    if stored_state is None:
        print(f"\n  {_fail} Cannot generate report: run state not found")
        sys.exit(2)

    from uuid import uuid4
    report_id = f"RPT-{uuid4().hex[:12].upper()}"
    now_ts = datetime.now(timezone.utc)

    compliant_count = sum(1 for v in verdicts if str(v.status.value) == "compliant")
    non_compliant_count = sum(1 for v in verdicts if str(v.status.value) == "non_compliant")
    pending_count = sum(1 for v in verdicts if str(v.status.value) == "pending")
    total = len(verdicts)

    report = {
        "report_id": report_id,
        "run_id": run_id,
        "circular_id": CIRCULAR_REF,
        "generated_at": now_ts.isoformat(),
        "summary": {
            "total_verdicts": total,
            "compliant": compliant_count,
            "non_compliant": non_compliant_count,
            "pending": pending_count,
            "compliance_pct": round(compliant_count / max(total, 1) * 100, 2),
        },
        "scoreboard": scoreboard.model_dump(mode="json", exclude_none=True),
        "verdicts": [v.model_dump(mode="json", exclude_none=True) for v in verdicts],
    }
    _get_report_store()[report_id] = report

    print(f"\n  {_ok} Report generated")
    print(f"    Report ID:     {report_id}")
    print(f"    Total verdicts: {total}")
    print(f"    Compliant:      {compliant_count}")
    print(f"    Non-compliant:  {non_compliant_count}")
    print(f"    Pending:        {pending_count}")
    print(f"    Compliance:     {report['summary']['compliance_pct']}%")

    # ── Done ─────────────────────────────────────────────────────────────
    print(f"\n══════════════════════════════════════════════════════════")
    print(f"  Demo completed successfully.")
    print(f"")
    print(f"  Run ID:     {run_id}")
    print(f"  Report ID:  {report_id}")
    print(f"  Verdicts:   {total}")
    print(f"  Hash chain: VERIFIED ✅")
    print(f"")
    print(f"  View in frontend:  http://localhost:5173/report/{report_id}")
    print(f"  (start frontend:   cd frontend && npm run dev)")
    print(f"══════════════════════════════════════════════════════════")

if __name__ == "__main__":
    asyncio.run(main())
PYEOF

EXIT_CODE=$?

echo ""
banner "Demo Result"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}✓ DEMO PASSED${NC} — Full pipeline executed successfully."
    echo ""
    echo "  What was validated:"
    echo "    • PDF parsing → 2 obligation clauses extracted"
    echo "    • FSM extraction → 2 HybridFSMs generated"
    echo "    • HITL gate → FSMs locked, reviewed, and approved"
    echo "    • Evaluator → compliance verdicts against 10 telemetry events"
    echo "    • Scoreboard → per-broker aggregation with compliance rates"
    echo "    • Hash chain → built, verified, and tamper-resistant"
    echo "    • Report → immutable audit report generated"
    exit 0
elif [ $EXIT_CODE -eq 2 ]; then
    echo -e "  ${RED}${BOLD}✗ DEMO FAILED${NC} — Pipeline execution error."
    exit 2
elif [ $EXIT_CODE -eq 3 ]; then
    echo -e "  ${RED}${BOLD}✗ DEMO FAILED${NC} — Hash-chain verification error."
    exit 3
else
    echo -e "  ${RED}${BOLD}✗ DEMO FAILED${NC} — Exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
