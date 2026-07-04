/**
 * FSMViewer — finite state machine diagram + detail tables.
 *
 * Renders an SVG state diagram (states as nodes, transitions as arrows)
 * along with transition and timeline-rule tables for a single HybridFSM.
 *
 * Accepts both a raw HybridFSM and a LockedFSM (which wraps one).
 *
 * States handled:
 *  - empty:     no FSM provided
 *  - populated: diagram + tables rendered
 */

import { useMemo } from 'react';
import type { HybridFSM, FSMTransition, TimelineRule, LockedFSM } from '../../api/client';

// ============================================================================
// Props
// ============================================================================

export interface FSMViewerProps {
  /** A raw HybridFSM. */
  fsm?: HybridFSM | null;
  /** A LockedFSM (its `original_fsm` is displayed). Takes precedence over `fsm`. */
  lockedFsm?: LockedFSM | null;
}

// ============================================================================
// SVG layout constants
// ============================================================================

const NODE_RADIUS = 44;
const NODE_GAP_X = 160;
const NODE_GAP_Y = 130;
const COLS = 4;
const SVG_PADDING = 48;

/** Colour per canonical state name. */
const STATE_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  PENDING:       { fill: '#fffff0', stroke: '#d69e2e', text: '#975a16' },
  DUE:           { fill: '#fffaf0', stroke: '#dd6b20', text: '#9c4221' },
  COMPLIANT:     { fill: '#f0fff4', stroke: '#38a169', text: '#276749' },
  LATE:          { fill: '#fff5f5', stroke: '#e53e3e', text: '#9b2c2c' },
  NON_COMPLIANT: { fill: '#fff5f5', stroke: '#c53030', text: '#742a2a' },
};

const DEFAULT_COLOR = { fill: '#f7fafc', stroke: '#a0aec0', text: '#4a5568' };

// ============================================================================
// Component
// ============================================================================

export default function FSMViewer({ fsm, lockedFsm }: FSMViewerProps) {
  // Resolve the HybridFSM
  const resolved = lockedFsm?.original_fsm ?? fsm ?? null;

  // Build a lookup of source→target pairs for drawing arrows
  const transitionPairs = useMemo(() => {
    if (!resolved) return [];
    return resolved.transitions.map((t) => ({
      from: t.from_state,
      to: t.to_state,
      trigger: t.trigger_event,
    }));
  }, [resolved]);

  // Position each state in a grid
  const positions = useMemo(() => {
    if (!resolved) return new Map<string, { x: number; y: number }>();
    const map = new Map<string, { x: number; y: number }>();
    resolved.states.forEach((s, i) => {
      const col = i % COLS;
      const row = Math.floor(i / COLS);
      map.set(s.name, {
        x: SVG_PADDING + NODE_RADIUS + col * NODE_GAP_X,
        y: SVG_PADDING + NODE_RADIUS + row * NODE_GAP_Y,
      });
    });
    return map;
  }, [resolved]);

  const rows = resolved
    ? Math.ceil(resolved.states.length / COLS)
    : 0;

  const svgWidth = resolved
    ? SVG_PADDING * 2 + Math.min(resolved.states.length, COLS) * NODE_GAP_X
    : 0;

  const svgHeight = resolved
    ? SVG_PADDING * 2 + rows * NODE_GAP_Y
    : 0;

  // ------------------------------------------------------------------
  // Empty state
  // ------------------------------------------------------------------
  if (!resolved) {
    return (
      <section className="card">
        <div className="card__header">
          <h2 className="card__title">FSM Viewer</h2>
        </div>
        <div className="card__body">
          <div className="placeholder-page" style={{ minHeight: '20vh' }}>
            <div className="placeholder-page__icon" aria-hidden="true">🔀</div>
            <p className="placeholder-page__subtitle">
              Select a circular and run to view extracted finite state machines.
            </p>
          </div>
        </div>
      </section>
    );
  }

  // ------------------------------------------------------------------
  // Populated
  // ------------------------------------------------------------------
  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">
          FSM: {resolved.obligation_ref}
        </h2>
        <span className="badge badge--neutral">
          {resolved.states.length} states
        </span>
      </div>

      <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        {/* Metadata */}
        <MetadataRow fsm={resolved} />

        {/* SVG diagram */}
        <figure
          style={{
            overflowX: 'auto',
            background: 'var(--color-neutral-50)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-neutral-300)',
          }}
        >
          <svg
            viewBox={`0 0 ${svgWidth} ${svgHeight}`}
            style={{ display: 'block', width: '100%', maxWidth: svgWidth, margin: '0 auto' }}
            role="img"
            aria-label={`State diagram for ${resolved.obligation_ref}`}
          >
            {/* Transition arrows */}
            {transitionPairs.map((t, i) => {
              const src = positions.get(t.from);
              const dst = positions.get(t.to);
              if (!src || !dst) return null;
              return (
                <Arrow
                  key={`t-${i}`}
                  x1={src.x}
                  y1={src.y}
                  x2={dst.x}
                  y2={dst.y}
                  label={t.trigger}
                  r={NODE_RADIUS}
                />
              );
            })}

            {/* State nodes */}
            {resolved.states.map((s) => {
              const pos = positions.get(s.name);
              if (!pos) return null;
              const colors = STATE_COLORS[s.name] ?? DEFAULT_COLOR;
              const isInitial = s.name === resolved.initial_state;
              const isTerminal = resolved.states.some(
                (st) =>
                  st.name === s.name &&
                  !resolved.transitions.some((t) => t.from_state === st.name),
              );
              return (
                <StateNode
                  key={s.name}
                  cx={pos.x}
                  cy={pos.y}
                  r={NODE_RADIUS}
                  label={s.name}
                  isInitial={isInitial}
                  isTerminal={isTerminal}
                  colors={colors}
                />
              );
            })}
          </svg>
        </figure>

        {/* Transition table */}
        {resolved.transitions.length > 0 && (
          <TransitionTable transitions={resolved.transitions} />
        )}

        {/* Timeline rules */}
        {resolved.timeline_rules.length > 0 && (
          <TimelineRulesTable rules={resolved.timeline_rules} />
        )}
      </div>
    </section>
  );
}

// ============================================================================
// SVG sub-components
// ============================================================================

function StateNode({
  cx,
  cy,
  r,
  label,
  isInitial,
  isTerminal,
  colors,
}: {
  cx: number;
  cy: number;
  r: number;
  label: string;
  isInitial: boolean;
  isTerminal: boolean;
  colors: { fill: string; stroke: string; text: string };
}) {
  return (
    <g>
      {/* Initial-state arrow */}
      {isInitial && (
        <>
          <line
            x1={cx - r - 24}
            y1={cy}
            x2={cx - r - 2}
            y2={cy}
            stroke="var(--color-neutral-500)"
            strokeWidth={1.5}
            markerEnd="url(#arrowhead)"
          />
          <text x={cx - r - 28} y={cy - 8} textAnchor="end" fontSize={11} fill="var(--color-neutral-500)">
            start
          </text>
        </>
      )}

      {/* Terminal double border */}
      {isTerminal && (
        <circle cx={cx} cy={cy} r={r + 4} fill="none" stroke={colors.stroke} strokeWidth={1.5} opacity={0.5} />
      )}

      {/* Node circle */}
      <circle cx={cx} cy={cy} r={r} fill={colors.fill} stroke={colors.stroke} strokeWidth={2} />

      {/* Label — split across 2 lines if needed */}
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={label.length > 12 ? 10 : 12}
        fontWeight={600}
        fill={colors.text}
      >
        {label.length > 14 ? (
          <>
            <tspan x={cx} dy="-0.5em">{label.slice(0, Math.ceil(label.length / 2))}</tspan>
            <tspan x={cx} dy="1.2em">{label.slice(Math.ceil(label.length / 2))}</tspan>
          </>
        ) : (
          label
        )}
      </text>
    </g>
  );
}

function Arrow({
  x1,
  y1,
  x2,
  y2,
  label,
  r,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  r: number;
}) {
  // Trim line endpoints to the node edge
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len === 0) return null;
  const ux = dx / len;
  const uy = dy / len;

  const sx = x1 + ux * r;
  const sy = y1 + uy * r;
  const ex = x2 - ux * (r + 8);
  const ey = y2 - uy * (r + 8);

  // Curved path via midpoint offset
  const midX = (sx + ex) / 2;
  const midY = (sy + ey) / 2;
  const curve = 28;
  const ctrlX = midX - uy * curve;
  const ctrlY = midY + ux * curve;

  const d = `M ${sx} ${sy} Q ${ctrlX} ${ctrlY} ${ex} ${ey}`;

  return (
    <g>
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="var(--color-neutral-500)" />
        </marker>
      </defs>
      <path d={d} fill="none" stroke="var(--color-neutral-400)" strokeWidth={1.5} markerEnd="url(#arrowhead)" />
      <text
        x={ctrlX}
        y={ctrlY - 6}
        textAnchor="middle"
        fontSize={9}
        fill="var(--color-neutral-500)"
        style={{ fontFamily: 'var(--font-mono)' }}
      >
        {label.length > 18 ? label.slice(0, 18) + '…' : label}
      </text>
    </g>
  );
}

// ============================================================================
// Table sub-components
// ============================================================================

function MetadataRow({ fsm }: { fsm: HybridFSM }) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 'var(--space-6)',
        fontSize: 'var(--text-sm)',
        color: 'var(--color-neutral-600)',
      }}
    >
      <div>
        <strong>FSM ID</strong>{' '}
        <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
          {fsm.fsm_id}
        </code>
      </div>
      <div>
        <strong>Circular</strong> {fsm.circular_ref}
      </div>
      <div>
        <strong>Initial</strong>{' '}
        <span className="badge badge--pending">{fsm.initial_state}</span>
      </div>
    </div>
  );
}

function TransitionTable({ transitions }: { transitions: FSMTransition[] }) {
  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: 'var(--space-3)' }}>
        Transitions ({transitions.length})
      </h3>
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
                <td><code>{t.trigger_event}</code></td>
                <td>
                  {t.conditions ? (
                    <code style={{ fontSize: 'var(--text-xs)' }}>
                      {JSON.stringify(t.conditions)}
                    </code>
                  ) : (
                    <span style={{ color: 'var(--color-neutral-400)' }}>—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TimelineRulesTable({ rules }: { rules: TimelineRule[] }) {
  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: 'var(--space-3)' }}>
        Timeline Rules ({rules.length})
      </h3>
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
                <td><code>{r.start_event}</code></td>
                <td>T+{r.deadline_offset}</td>
                <td>{r.grace_period > 0 ? `+${r.grace_period}` : '—'}</td>
                <td>{r.time_unit}</td>
                <td><StateBadge name={r.overdue_transition} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StateBadge({ name }: { name: string }) {
  const colors = STATE_COLORS[name] ?? DEFAULT_COLOR;
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.1em 0.5em',
        fontSize: 'var(--text-xs)',
        fontWeight: 600,
        backgroundColor: colors.fill,
        color: colors.text,
        border: `1px solid ${colors.stroke}`,
        borderRadius: 'var(--radius-sm)',
        whiteSpace: 'nowrap',
      }}
    >
      {name}
    </span>
  );
}
