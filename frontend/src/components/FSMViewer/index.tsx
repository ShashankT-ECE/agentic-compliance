/**
 * Compliance Workflow — enterprise SVG diagram + detail tables.
 *
 * Renders a clear linear workflow:
 *
 *           COMPLIANT
 *          ↗         ↗
 *   PENDING → DUE → LATE → NON-COMPLIANT
 *
 * No overlapping arrows.  Transitions and timeline rules appear in
 * detail tables below the diagram.
 */

import type { HybridFSM, FSMTransition, TimelineRule, LockedFSM } from '../../api/client';

// ============================================================================
// Props
// ============================================================================

export interface FSMViewerProps {
  fsm?: HybridFSM | null;
  lockedFsm?: LockedFSM | null;
}

// ============================================================================
// Fixed layout — linear workflow with COMPLIANT branch above
// ============================================================================

const NODE_R = 56;                      // node radius
const SVG_W = 940;                      // viewport width
const SVG_H = 300;                      // viewport height

// Linear row: PENDING, DUE, LATE, NON_COMPLIANT
const BOTTOM_Y = 200;
const DUE_X = 270;
const GAP = 190;
const PENDING_X = DUE_X - GAP;          // 80
const LATE_X = DUE_X + GAP;            // 460
const NON_COMPLIANT_X = LATE_X + GAP;  // 650

// COMPLIANT floats above, between PENDING and DUE
const COMPLIANT_X = DUE_X;             // 270
const COMPLIANT_Y = 78;

/** Resolve a state name to its fixed (x, y). */
function layoutPos(name: string): { x: number; y: number } | undefined {
  const key = name.replace('-', '_');
  return (LAYOUT_MAP as Record<string, { x: number; y: number }>)[key];
}
const LAYOUT_MAP = {
  PENDING:        { x: PENDING_X,       y: BOTTOM_Y },
  DUE:            { x: DUE_X,           y: BOTTOM_Y },
  LATE:           { x: LATE_X,          y: BOTTOM_Y },
  NON_COMPLIANT:  { x: NON_COMPLIANT_X, y: BOTTOM_Y },
  COMPLIANT:      { x: COMPLIANT_X,     y: COMPLIANT_Y },
};

/** Enterprise colour palette per canonical state. */
const STATE_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  PENDING:       { fill: '#fefce8', stroke: '#c88a04', text: '#713f12' },
  DUE:           { fill: '#fff7ed', stroke: '#ea580c', text: '#7c2d12' },
  COMPLIANT:     { fill: '#f0fdf4', stroke: '#15803d', text: '#14532d' },
  LATE:          { fill: '#fef2f2', stroke: '#dc2626', text: '#7f1d1d' },
  NON_COMPLIANT: { fill: '#fef2f2', stroke: '#b91c1c', text: '#450a0a' },
  'NON-COMPLIANT': { fill: '#fef2f2', stroke: '#b91c1c', text: '#450a0a' },
};

const DEFAULT_COLOR = { fill: '#f8fafc', stroke: '#94a3b8', text: '#334155' };

/** Format FSM-XXXX → OBL-XXXX in display text. */
function formatObligationId(id: string): string {
  return id.replace(/^FSM-/, 'OBL-');
}

// ============================================================================
// Component
// ============================================================================

export default function FSMViewer({ fsm, lockedFsm }: FSMViewerProps) {
  const resolved = lockedFsm?.original_fsm ?? fsm ?? null;

  // ── Empty ────────────────────────────────────────────────────────────
  if (!resolved) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">
            <span className="card__title-icon">🔀</span>
            Compliance Workflow
          </h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '16vh' }}>
            <p className="placeholder-page__subtitle">
              Select a compliance obligation to view its workflow diagram.
            </p>
          </div>
        </div>
      </section>
    );
  }

  // ── Populated ────────────────────────────────────────────────────────
  return (
    <div style={{
      background: '#fff',
      border: '1px solid var(--color-slate-200)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: 'var(--space-4) var(--space-5)',
        borderBottom: '1px solid var(--color-slate-150)',
      }}>
        <h3 style={{
          fontSize: 'var(--text-sm)', fontWeight: 600,
          color: 'var(--color-slate-700)', display: 'flex',
          alignItems: 'center', gap: 'var(--space-2)',
        }}>
          🔀 Compliance Workflow
        </h3>
        <span className="badge badge--neutral">{resolved.states.length} states</span>
      </div>

      <div style={{ padding: 'var(--space-5)' }}>
        {/* Metadata row */}
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 'var(--space-6)',
          fontSize: 'var(--text-sm)', color: 'var(--color-slate-600)',
          marginBottom: 'var(--space-4)',
        }}>
          <div>
            <span style={{ fontWeight: 500, color: 'var(--color-slate-500)' }}>
              Obligation ID
            </span>{' '}
            <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--color-slate-700)' }}>
              {formatObligationId(resolved.fsm_id)}
            </code>
          </div>
          <div>
            <span style={{ fontWeight: 500, color: 'var(--color-slate-500)' }}>
              Circular
            </span>{' '}
            <span>{resolved.circular_ref}</span>
          </div>
          <div>
            <span style={{ fontWeight: 500, color: 'var(--color-slate-500)' }}>
              Current Status
            </span>{' '}
            <span className="badge badge--pending">{resolved.initial_state}</span>
          </div>
        </div>

        {/* SVG diagram */}
        <figure style={{
          overflowX: 'auto',
          background: 'var(--color-slate-50)',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--color-slate-200)',
        }}>
          <svg
            viewBox={`0 0 ${SVG_W} ${SVG_H}`}
            style={{ display: 'block', width: '100%', maxWidth: SVG_W, margin: '0 auto' }}
            role="img"
            aria-label={`Compliance workflow for ${resolved.obligation_ref}`}
          >
            <defs>
              <marker id="arrowhead" markerWidth="9" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 9 3.5, 0 7" fill="var(--color-slate-400)" />
              </marker>
              <marker id="arrowhead-thick" markerWidth="9" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 9 3.5, 0 7" fill="var(--color-slate-500)" />
              </marker>
            </defs>

            {/* Straight horizontal arrows (thicker) */}
            <StraightEdge from="PENDING" to="DUE" r={NODE_R} />
            <StraightEdge from="DUE" to="LATE" r={NODE_R} />
            <StraightEdge from="LATE" to="NON_COMPLIANT" r={NODE_R} />

            {/* Branch arrows up to COMPLIANT (thinner, arc) */}
            <BranchEdge from="PENDING" to="COMPLIANT" r={NODE_R} side="left" />
            <BranchEdge from="DUE" to="COMPLIANT" r={NODE_R} side="right" />

            {/* Start marker — small arrow pointing into PENDING */}
            <StartArrow to="PENDING" r={NODE_R} />

            {/* State nodes */}
            {resolved.states.map((s) => {
              const pos = layoutPos(s.name);
              if (!pos) return null;
              const colors = STATE_COLORS[s.name] ?? DEFAULT_COLOR;
              const isTerminal = !resolved.transitions.some((t) => t.from_state === s.name);
              return (
                <StateNode
                  key={s.name}
                  x={pos.x} y={pos.y} r={NODE_R}
                  label={s.name.replace(/_/g, ' ')}
                  isTerminal={isTerminal}
                  colors={colors}
                />
              );
            })}
          </svg>
        </figure>

        {/* Transition table */}
        {resolved.transitions.length > 0 && (
          <div style={{ marginTop: 'var(--space-5)' }}>
            <TableHeading>Transitions ({resolved.transitions.length})</TableHeading>
            <TransitionTable transitions={resolved.transitions} />
          </div>
        )}

        {/* Timeline rules */}
        {resolved.timeline_rules.length > 0 && (
          <div style={{ marginTop: 'var(--space-5)' }}>
            <TableHeading>Timeline Rules ({resolved.timeline_rules.length})</TableHeading>
            <TimelineRulesTable rules={resolved.timeline_rules} />
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// SVG elements
// ============================================================================

function StateNode({ x, y, r, label, isTerminal, colors }: {
  x: number; y: number; r: number; label: string;
  isTerminal: boolean;
  colors: { fill: string; stroke: string; text: string };
}) {
  return (
    <g>
      {isTerminal && (
        <circle cx={x} cy={y} r={r + 5} fill="none" stroke={colors.stroke} strokeWidth={1.5} opacity={0.35} />
      )}
      <circle cx={x} cy={y} r={r} fill={colors.fill} stroke={colors.stroke} strokeWidth={2.5} />
      <text x={x} y={y} textAnchor="middle" dominantBaseline="central"
        fontSize={12} fontWeight={700} fill={colors.text}
        style={{ letterSpacing: '0.02em' }}>
        {label.length > 12 ? (
          <>
            <tspan x={x} dy="-0.5em">{label.slice(0, Math.ceil(label.length / 2))}</tspan>
            <tspan x={x} dy="1.2em">{label.slice(Math.ceil(label.length / 2))}</tspan>
          </>
        ) : label}
      </text>
    </g>
  );
}

/** Straight horizontal arrow between two linear nodes. */
function StraightEdge({ from, to, r }: { from: string; to: string; r: number }) {
  const src = layoutPos(from);
  const dst = layoutPos(to);
  if (!src || !dst) return null;

  const x1 = src.x + r;
  const x2 = dst.x - r - 4;
  const y = src.y;

  return (
    <line x1={x1} y1={y} x2={x2} y2={y}
      stroke="var(--color-slate-500)" strokeWidth={2.5}
      markerEnd="url(#arrowhead-thick)" />
  );
}

/** Curved arc from a bottom node up to COMPLIANT. */
function BranchEdge({ from, to, r, side }: {
  from: string; to: string; r: number; side: 'left' | 'right';
}) {
  const src = layoutPos(from);
  const dst = layoutPos(to);
  if (!src || !dst) return null;

  // Start from top edge of source node
  const sx = src.x;
  const sy = src.y - r;

  // End at bottom edge of target node
  const ex = dst.x;
  const ey = dst.y + r + 4;

  // Control point: horizontal offset depends on side
  const cpx = side === 'left' ? sx + 40 : sx - 40;
  const cpy = (sy + ey) / 2;

  const d = `M ${sx} ${sy} Q ${cpx} ${cpy}, ${ex} ${ey}`;

  return (
    <path d={d} fill="none" stroke="var(--color-slate-400)" strokeWidth={2}
      markerEnd="url(#arrowhead)" />
  );
}

/** Arrow pointing into the PENDING node from the left (start of workflow). */
function StartArrow({ to, r }: { to: string; r: number }) {
  const dst = layoutPos(to);
  if (!dst) return null;
  const x2 = dst.x - r - 2;
  return (
    <g>
      <line x1={dst.x - r - 36} y1={dst.y} x2={x2} y2={dst.y}
        stroke="var(--color-slate-400)" strokeWidth={1.5}
        markerEnd="url(#arrowhead)" />
      <text x={dst.x - r - 40} y={dst.y - 10} textAnchor="end"
        fontSize={11} fill="var(--color-slate-400)" fontWeight={500}>
        start
      </text>
    </g>
  );
}

// ============================================================================
// Tables
// ============================================================================

function TableHeading({ children }: { children: React.ReactNode }) {
  return (
    <h4 style={{
      fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-slate-500)',
      textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 'var(--space-3)',
    }}>
      {children}
    </h4>
  );
}

function TransitionTable({ transitions }: { transitions: FSMTransition[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>From</th>
            <th>To</th>
            <th>Trigger Event</th>
            <th>Conditions</th>
          </tr>
        </thead>
        <tbody>
          {transitions.map((t, i) => (
            <tr key={i}>
              <td><StateBadge name={t.from_state} /></td>
              <td><StateBadge name={t.to_state} /></td>
              <td><code style={{ fontSize: 'var(--text-xs)' }}>{t.trigger_event}</code></td>
              <td>
                {t.conditions ? (
                  <code style={{ fontSize: 'var(--text-2xs)' }}>{JSON.stringify(t.conditions)}</code>
                ) : (
                  <span style={{ color: 'var(--color-slate-400)' }}>—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TimelineRulesTable({ rules }: { rules: TimelineRule[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Start Event</th>
            <th>Deadline</th>
            <th>Grace Period</th>
            <th>Unit</th>
            <th>Overdue →</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r, i) => (
            <tr key={i}>
              <td><code style={{ fontSize: 'var(--text-xs)' }}>{r.start_event}</code></td>
              <td><span style={{ fontWeight: 600 }}>T+{r.deadline_offset}</span></td>
              <td>{r.grace_period > 0 ? `+${r.grace_period}` : '—'}</td>
              <td>{r.time_unit}</td>
              <td><StateBadge name={r.overdue_transition} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StateBadge({ name }: { name: string }) {
  const colors = STATE_COLORS[name] ?? DEFAULT_COLOR;
  return (
    <span style={{
      display: 'inline-block', padding: '0.1em 0.55em',
      fontSize: 'var(--text-2xs)', fontWeight: 600,
      background: colors.fill, color: colors.text,
      border: `1px solid ${colors.stroke}`,
      borderRadius: 'var(--radius-sm)', whiteSpace: 'nowrap',
      textTransform: 'uppercase', letterSpacing: '0.03em',
    }}>
      {name.replace(/_/g, ' ')}
    </span>
  );
}
