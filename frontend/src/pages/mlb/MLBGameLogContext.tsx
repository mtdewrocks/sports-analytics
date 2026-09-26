import React from 'react';
import { theme } from '../../theme';
import {
  type NextGame, type VsHand, type NextStart, type LineupStats, type LineupMetric,
  fmtRate, fmtPct, fmtMetric, fmtPrice, ordinal, gameWhen, handWord,
  METRIC_LABELS, METRIC_SHORT, lineupOrder, overColor, flagLabel, HITTER_BENCH,
} from './mlbGameLogContextUtils';

// Upcoming-game context for the MLB Game Log. Data comes from
// backend/app/data/mlb_game_log_context.py, riding along on the existing
// /game-log and /pitcher-game-log responses (`next_game` / `vs_hand` on a
// batter, `next_start` plus per-game `lineup` on a pitcher).

// ---------------------------------------------------------------------------
// Little building blocks
// ---------------------------------------------------------------------------

const cardStyle: React.CSSProperties = {
  background: theme.bgCard, border: `1px solid ${theme.borderStrong}`, borderRadius: 12,
  padding: 20, marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 16,
};
const panelStyle: React.CSSProperties = {
  background: theme.bgPage, border: `1px solid ${theme.border}`, borderRadius: 10, padding: 16,
  display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0,
};
const eyebrow: React.CSSProperties = {
  fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em', color: theme.textSecondary,
};

function Pill({ tone, children }: { tone: 'good' | 'warn' | 'bad' | 'plain'; children: React.ReactNode }) {
  const tones = {
    good: { background: '#0f3d2e', color: '#3fcf9a' },
    warn: { background: '#2d2208', color: theme.warningText },
    bad: { background: 'rgba(244,87,63,0.14)', color: theme.dataRed },
    plain: { background: theme.border, color: theme.textPrimary },
  }[tone];
  return (
    <span style={{ ...tones, padding: '4px 10px', borderRadius: 999, fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>
      {children}
    </span>
  );
}

function Stat({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      <span style={{ fontSize: 12, color: theme.textSecondary }}>{label}</span>
      <span style={{ fontSize: 17, fontWeight: 700, color: color ?? theme.textPrimary }}>{value}</span>
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 14 }}>
      <span style={{ color: theme.textSecondary }}>{label}</span>
      <span style={{ fontWeight: 600, color: color ?? theme.textPrimary, textAlign: 'right' }}>{value}</span>
    </div>
  );
}

function pctColorOf(pct: number): string {
  return pct >= 0.6 ? theme.dataBlue : pct >= 0.4 ? theme.textSecondary : theme.dataRed;
}

// ---------------------------------------------------------------------------
// Batter: Next Game Matchup
// ---------------------------------------------------------------------------

export function BatterNextGameCard({
  next, vsHand, player, statLabel, threshold, isMobile,
}: {
  next: NextGame | null | undefined;
  vsHand: VsHand | null | undefined;
  player: string;
  statLabel: string;
  threshold: number;
  isMobile: boolean;
}) {
  if (!next || next.status === 'no_game') return null;
  const lastName = player.split(' ').slice(-1)[0];
  const status =
    next.status === 'in_lineup' ? <Pill tone="good">Confirmed{next.batting_order ? ` · Batting ${ordinal(next.batting_order)}` : ''}</Pill>
      : next.status === 'out' ? <Pill tone="bad">Not in lineup</Pill>
        : <Pill tone="warn">Lineup not posted yet</Pill>;
  const split = next.pitcher_split;
  const sideWord = next.vs_side === 'L' ? 'left' : next.vs_side === 'R' ? 'right' : null;
  const handAbbr = next.throws === 'L' ? 'LHP' : next.throws === 'R' ? 'RHP' : null;

  return (
    <section style={cardStyle} aria-label="Next game matchup">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 18, color: theme.textPrimary }}>Next Game Matchup</h3>
        {status}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 16 }}>
        <div style={panelStyle}>
          <span style={eyebrow}>Game</span>
          <span style={{ fontSize: 17, fontWeight: 600, color: theme.textPrimary }}>
            {next.is_home == null ? '' : next.is_home ? 'vs ' : '@ '}{next.opponent ?? 'TBD'}
          </span>
          <span style={{ fontSize: 14, color: theme.textSecondary }}>{gameWhen(next.date, next.game_time_utc)}</span>
          {next.status === 'out' && (
            <span style={{ fontSize: 13, color: theme.textSecondary }}>
              His team's lineup is posted and he isn't in it.
            </span>
          )}
        </div>

        <div style={panelStyle}>
          <span style={eyebrow}>Opposing starter</span>
          <span style={{ fontSize: 17, fontWeight: 600, color: theme.textPrimary }}>
            {next.pitcher ? `${next.pitcher}${next.throws ? ` (${next.throws})` : ''}` : 'Not announced'}
          </span>
          {next.pitcher_season && (
            <span style={{ fontSize: 13, color: theme.textSecondary }}>
              {[
                next.pitcher_season.games_started != null ? `${next.pitcher_season.games_started} starts` : null,
                next.pitcher_season.era != null ? `${next.pitcher_season.era.toFixed(2)} ERA` : null,
                next.pitcher_season.ip_per_start != null ? `${next.pitcher_season.ip_per_start} innings per start` : null,
              ].filter(Boolean).join(' · ')}
            </span>
          )}
          {split ? (
            <>
              <span style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
                Against {sideWord}-handed batters{next.vs_side ? ` (${lastName}'s side)` : ''}
              </span>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 8 }}>
                {(['AVG', 'wOBA', 'SLG', 'K%', 'BB%'] as const).map((k) => {
                  const v = split[k];
                  const isPct = k === 'K%' || k === 'BB%';
                  // Red = the pitcher is tough on hitters here (low avg/wOBA/SLG, high K%).
                  const bench = HITTER_BENCH[k];
                  const tough = v == null ? null : k === 'K%' ? v > bench + 1 : k === 'BB%' ? v < bench - 1 : v < bench - 0.01;
                  const easy = v == null ? null : k === 'K%' ? v < bench - 1 : k === 'BB%' ? v > bench + 1 : v > bench + 0.01;
                  return (
                    <Stat key={k} label={k === 'AVG' ? 'Avg' : k === 'K%' ? 'K %' : k === 'BB%' ? 'BB %' : k}
                      value={isPct ? fmtPct(v) : fmtRate(v)}
                      color={tough ? theme.dataRed : easy ? theme.dataBlue : undefined} />
                  );
                })}
              </div>
            </>
          ) : next.pitcher ? (
            <span style={{ fontSize: 13, color: theme.textSecondary }}>
              {next.vs_side ? 'No split on file for this side yet.' : "His batting side isn't known until the lineup posts."}
            </span>
          ) : null}
        </div>

        <div style={panelStyle}>
          <span style={eyebrow}>{lastName} vs {handAbbr ?? 'this starter'}</span>
          {vsHand && vsHand.games > 0 ? (
            <>
              <Row label="Avg / OBP / SLG" value={`${fmtRate(vsHand.avg)} / ${fmtRate(vsHand.obp)} / ${fmtRate(vsHand.slg)}`} />
              <Row label="Strikeout %" value={fmtPct(vsHand.k_pct)} />
              <Row label={`${statLabel} ${threshold}+ vs ${handAbbr}`}
                value={`${vsHand.over} of ${vsHand.total} · ${Math.round(vsHand.pct * 100)}%`}
                color={pctColorOf(vsHand.pct)} />
            </>
          ) : (
            <span style={{ fontSize: 13, color: theme.textSecondary }}>
              {handAbbr ? `No logged games against a ${handWord(next.throws)} starter this season.` : 'Starter not announced yet.'}
            </span>
          )}
          <Row
            label={next.line != null ? `Best price, Over ${next.line} ${statLabel.toLowerCase()}` : 'Best price'}
            value={next.price ? <>{fmtPrice(next.price.price)} <span style={{ fontWeight: 400, color: theme.textSecondary }}>{next.price.books.join(', ')}</span></> : '—'}
          />
        </div>
      </div>
      {vsHand && vsHand.games > 0 && (
        <span style={{ fontSize: 12, color: theme.textSecondary }}>
          vs {handAbbr} numbers are from his box scores in games against {handWord(next.throws)} starters (OBP without hit-by-pitches).
        </span>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Pitcher: Next Start -- opposing lineup averages
// ---------------------------------------------------------------------------

export function PitcherNextStartCard({
  next, pitcher, stat, statLabel, threshold, isMobile,
}: {
  next: NextStart | null | undefined;
  pitcher: string;
  stat: string;
  statLabel: string;
  threshold: number;
  isMobile: boolean;
}) {
  if (!next) return null;
  const order = lineupOrder(stat);
  const key = next.key_metric;
  const handAbbr = next.throws === 'L' ? 'left-handers' : next.throws === 'R' ? 'right-handers' : 'his hand';
  const flagText = flagLabel(next.flag);
  const lastName = pitcher.split(' ').slice(-1)[0];
  const status = next.lineup_status === 'posted' ? <Pill tone="good">Lineup posted</Pill>
    : next.lineup_status === 'projected' ? <Pill tone="warn">Projected lineup</Pill>
      : <Pill tone="plain">Lineup unknown</Pill>;

  // Columns: the key metric, then the standout-hitter count for it, then
  // the rest in this stat's order.
  type Col = { id: string; label: string; metric?: LineupMetric };
  const cols: Col[] = [];
  order.forEach((m, i) => {
    cols.push({ id: m, label: METRIC_LABELS[m], metric: m });
    if (i === 0 && flagText) cols.push({ id: 'flag', label: flagText });
  });
  const bench = next.league ?? {};
  const tonightLabel = next.lineup_status === 'projected'
    ? `${next.opponent ?? 'Opponent'} (projected, season rates)`
    : `Tonight: ${next.opponent ?? 'Opponent'}`;

  const rows: { label: React.ReactNode; vals: LineupStats; flag: React.ReactNode; highlight?: boolean }[] = [
    {
      label: <><span style={{ fontWeight: 600, color: '#3fcf9a' }}>{tonightLabel}</span>
        {next.lineup_status === 'posted' && <span style={{ fontSize: 12, color: theme.textSecondary }}> vs {handAbbr}</span>}</>,
      vals: next.tonight,
      flag: next.flag?.count != null ? `${next.flag.count} of ${next.batters ?? 9}` : '—',
      highlight: true,
    },
    {
      label: <>Lineups he's faced this season <span style={{ fontSize: 12, color: theme.textSecondary }}>(average)</span></>,
      vals: next.faced_avg,
      flag: next.flag?.faced_avg != null ? `${next.flag.faced_avg.toFixed(1)} of 9` : '—',
    },
    {
      label: `League vs ${handAbbr}`,
      vals: next.league ?? {},
      flag: '—',
    },
  ];

  const similarText = next.similar
    ? `vs lineups ${next.similar.side} his average ${METRIC_SHORT[next.similar.metric]}`
    : null;

  return (
    <section style={cardStyle} aria-label="Next start opposing lineup averages">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 18, color: theme.textPrimary }}>Next Start — Opposing Lineup Averages</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 14, color: theme.textSecondary }}>
            {gameWhen(next.date, next.game_time_utc)}{next.opponent ? ` · ${next.is_home ? 'vs' : '@'} ${next.opponent}` : ''}
          </span>
          {status}
        </div>
      </div>

      {isMobile ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
          {cols.map((c) => {
            const v = c.metric ? next.tonight[c.metric] : null;
            const faced = c.metric ? next.faced_avg[c.metric] : next.flag?.faced_avg;
            return (
              <div key={c.id} style={{ ...panelStyle, padding: 12, gap: 2 }}>
                <span style={{ fontSize: 11, color: c.metric === key || c.id === 'flag' ? '#3fcf9a' : theme.textSecondary }}>{c.label}</span>
                <span style={{ fontSize: 17, fontWeight: 700, color: c.metric ? overColor(stat, c.metric, v, bench[c.metric]) : theme.textPrimary }}>
                  {c.metric ? fmtMetric(c.metric, v) : (next.flag?.count != null ? `${next.flag.count} of ${next.batters ?? 9}` : '—')}
                </span>
                <span style={{ fontSize: 11, color: theme.textSecondary }}>
                  faced avg {c.metric ? fmtMetric(c.metric, faced) : faced != null ? faced.toFixed(1) : '—'}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ background: theme.bgCardHover, color: theme.textPrimary }}>
              <th style={{ padding: '10px 14px', textAlign: 'left' }}>Lineup</th>
              {cols.map((c) => (
                <th key={c.id} style={{ padding: '10px 14px', textAlign: 'center', color: c.metric === key || c.id === 'flag' ? '#3fcf9a' : theme.textPrimary }}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${theme.border}`, background: r.highlight ? '#13201b' : 'transparent' }}>
                <td style={{ padding: '10px 14px', color: theme.textPrimary }}>{r.label}</td>
                {cols.map((c) => (
                  <td key={c.id} style={{
                    padding: '10px 14px', textAlign: 'center',
                    fontWeight: r.highlight ? 700 : 400, fontSize: r.highlight ? 15 : 14,
                    color: r.highlight && c.metric ? overColor(stat, c.metric, r.vals[c.metric], bench[c.metric])
                      : r.highlight ? theme.textPrimary : theme.textSecondary,
                  }}>
                    {c.metric ? fmtMetric(c.metric, r.vals[c.metric]) : r.flag}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
        <div style={panelStyle}>
          <span style={{ fontSize: 12, color: theme.textSecondary }}>{statLabel} {threshold}+ {similarText ?? 'vs similar lineups'}</span>
          <span style={{ fontSize: 20, fontWeight: 700, color: next.similar && next.similar.total ? pctColorOf(next.similar.pct) : theme.textPrimary }}>
            {next.similar ? `${next.similar.over} of ${next.similar.total}` : '—'}
          </span>
          <span style={{ fontSize: 12, color: theme.textSecondary }}>tonight's lineup is {next.similar?.side ?? '—'} that average</span>
        </div>
        <div style={panelStyle}>
          <span style={{ fontSize: 12, color: theme.textSecondary }}>{lastName} walk rate vs lineup walk %</span>
          <span style={{ fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>
            {next.walks_per_9 != null ? `${next.walks_per_9} per 9` : '—'} · {fmtPct(next.tonight.bb_pct)}
          </span>
          <span style={{ fontSize: 12, color: theme.textSecondary }}>patient lineups run up his pitch count</span>
        </div>
        <div style={panelStyle}>
          <span style={{ fontSize: 12, color: theme.textSecondary }}>
            Best price{next.line != null ? `, ${statLabel.toLowerCase()} ${next.line}` : ''}
          </span>
          <span style={{ fontSize: 20, fontWeight: 700, color: theme.textPrimary }}>
            {next.prices.over ? `Over ${fmtPrice(next.prices.over.price)}` : 'Over —'}
            {' · '}
            {next.prices.under ? `Under ${fmtPrice(next.prices.under.price)}` : 'Under —'}
          </span>
          <span style={{ fontSize: 12, color: theme.textSecondary }}>
            {[next.prices.over?.books.join(', '), next.prices.under?.books.join(', ')].filter(Boolean).join(' / ') || 'No posted line at this threshold'}
          </span>
        </div>
      </div>

      <span style={{ fontSize: 12, color: theme.textSecondary }}>
        Green headers are the numbers that matter most for {statLabel.toLowerCase()}; blue helps the Over, red hurts it (vs the league).
        {next.lineup_status === 'projected' ? " Projected = the nine hitters with the most plate appearances in their last game." : ''}
        {' '}Past lineups use each hitter's season rates.
      </span>
    </section>
  );
}
