/**
 * Read a user's minutes sheet for NBA Projections: .xlsx, .csv or .txt with a
 * player column and a minutes column (any order, header optional). Excel is
 * parsed in the browser -- nothing is uploaded to the server.
 */

export interface MinutesRow { player: string; minutes: number }

/** Same normalisation as the backend's match_key: accents, dots, apostrophes and Jr/Sr/II... dropped. */
export function nameKey(name: string): string {
  return String(name)
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/[.'’]/g, '')
    .replace(/\b(jr|sr|ii|iii|iv)\b/g, '')
    .split(/\s+/).filter(Boolean).join(' ');
}

function parseCsv(text: string): unknown[][] {
  const delim = (text.split('\n')[0].match(/\t/) ? '\t' : ',');
  return text.split(/\r?\n/).filter((l) => l.trim()).map((line) => {
    const out: string[] = []; let cur = ''; let q = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"') { if (q && line[i + 1] === '"') { cur += '"'; i++; } else q = !q; }
      else if (c === delim && !q) { out.push(cur); cur = ''; }
      else cur += c;
    }
    out.push(cur);
    return out.map((s) => s.trim());
  });
}

function toRows(grid: unknown[][]): MinutesRow[] {
  const rows = grid.filter((r) => r && r.some((c) => c !== null && c !== ''));
  if (!rows.length) return [];
  const head = rows[0].map((c) => String(c ?? '').toLowerCase());
  let pc = head.findIndex((h) => /player|name/.test(h));
  let mc = head.findIndex((h) => /^min|minutes|mins|mpg/.test(h));
  let body = rows.slice(1);
  if (pc < 0 || mc < 0) {
    // no header: first column that's mostly text, first that's mostly numbers
    body = rows;
    const sample = rows.slice(0, 20);
    const width = Math.max(...sample.map((r) => r.length));
    const isNum = (v: unknown) => v !== '' && v !== null && !isNaN(Number(v));
    const numShare = (i: number) => sample.filter((r) => isNum(r[i])).length / sample.length;
    pc = [...Array(width).keys()].find((i) => numShare(i) < 0.3) ?? 0;
    mc = [...Array(width).keys()].find((i) => i !== pc && numShare(i) > 0.7) ?? 1;
    if (!isNum(rows[0][mc])) body = rows.slice(1);
  }
  return body
    .map((r) => ({ player: String(r[pc] ?? '').trim(), minutes: Number(r[mc]) }))
    .filter((r) => r.player && Number.isFinite(r.minutes))
    .map((r) => ({ ...r, minutes: Math.max(0, Math.min(48, Math.round(r.minutes * 10) / 10)) }));
}

export async function readMinutesFile(file: File): Promise<MinutesRow[]> {
  if (/\.(xlsx|xlsm)$/i.test(file.name)) {
    const { readSheet } = await import('read-excel-file/browser');
    return toRows((await readSheet(file)) as unknown[][]);
  }
  if (/\.xls$/i.test(file.name)) throw new Error('Old .xls files aren’t supported — save it as .xlsx or .csv.');
  return toRows(parseCsv(await file.text()));
}
