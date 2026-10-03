import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Search } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "./ui/sheet";
import { SUBCATEGORIES, STATE_REGIONS, parseFilter, filterKey } from "../lib/taxonomy";

const API = "https://chintangithubio-production.up.railway.app/api";

// Outlined sub-pills under the active chip (design review direction B):
// drawn 30px tall with a 44px hit area; the active one gets an accent border
// and a 12% accent tint. Announced as a list with the selected state.
function Pill({ label, active, onClick, testid }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      data-testid={testid}
      style={{
        flexShrink: 0, minHeight: 44, padding: "7px 0", background: "none", border: "none", cursor: "pointer",
        display: "flex", alignItems: "center",
      }}
    >
      <span style={{
        display: "inline-flex", alignItems: "center", height: 30, padding: "0 11px", borderRadius: 999,
        fontFamily: "'Manrope', sans-serif", fontSize: 12, whiteSpace: "nowrap",
        border: `1px solid ${active ? "rgba(220,38,38,0.6)" : "rgb(var(--c-fg-rgb) / 0.10)"}`,
        background: active ? "rgba(220,38,38,0.12)" : "transparent",
        color: active ? "var(--c-ink)" : "var(--c-sub)",
      }}>{label}</span>
    </button>
  );
}

export function SubPills({ filter, onChange, homeState, onPickState }) {
  const f = parseFilter(filter);
  const [top, setTop] = useState([]);

  useEffect(() => {
    if (f.top !== "States") return;
    let alive = true;
    axios.get(`${API}/states/top`).then((r) => { if (alive) setTop(r.data.states || []); }).catch(() => {});
    return () => { alive = false; };
  }, [f.top]);

  if (f.top === "All") return null;
  if (f.top === "States") {
    const trending = top.map((t) => t.state).filter((s) => s !== homeState).slice(0, 5);
    return (
      <div className="overflow-x-auto hide-scrollbar" style={{ margin: "-10px 0 8px" }}>
        <div role="list" aria-label="States" style={{ display: "flex", gap: 6 }}>
          {homeState && (
            <span role="listitem" style={{ display: "flex" }}>
              <Pill label={homeState} active={f.state === homeState} onClick={() => onChange(filterKey("States", homeState))} testid="state-home" />
              <button type="button" onClick={onPickState} style={{ background: "none", border: "none", cursor: "pointer", minHeight: 44, padding: "0 6px", color: "var(--c-muted)", fontSize: 11.5 }}>
                · change
              </button>
            </span>
          )}
          {trending.map((s) => (
            <span role="listitem" key={s}>
              <Pill label={s} active={f.state === s} onClick={() => onChange(filterKey("States", s))} testid={`state-${s}`} />
            </span>
          ))}
          <span role="listitem"><Pill label="More states ›" active={false} onClick={onPickState} testid="state-more" /></span>
        </div>
      </div>
    );
  }
  const subs = SUBCATEGORIES[f.top] || [];
  return (
    <div className="overflow-x-auto hide-scrollbar" style={{ margin: "-10px 0 8px" }}>
      <div role="list" aria-label={`${f.top} topics`} style={{ display: "flex", gap: 6 }}>
        <span role="listitem"><Pill label="All" active={!f.sub} onClick={() => onChange(filterKey(f.top))} testid="sub-all" /></span>
        {subs.map((s) => (
          <span role="listitem" key={s}>
            <Pill label={s} active={f.sub === s} onClick={() => onChange(filterKey(f.top, s))} testid={`sub-${s}`} />
          </span>
        ))}
      </div>
    </div>
  );
}

/** Searchable state picker, grouped by region, 44px rows. First-time
 * variant asks "Which state's news do you want first?" with Skip always shown. */
export function StateSheet({ open, firstTime, onPick, onClose }) {
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return Object.entries(STATE_REGIONS)
      .map(([region, states]) => [region, states.filter((s) => s.toLowerCase().includes(needle))])
      .filter(([, states]) => states.length);
  }, [q]);

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto" style={{ background: "var(--c-surface)", borderTopLeftRadius: 20, borderTopRightRadius: 20 }}>
        <SheetTitle style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: 19, color: "var(--c-ink)" }}>
          {firstTime ? "Which state’s news do you want first?" : "Pick a state"}
        </SheetTitle>
        <SheetDescription style={{ color: "var(--c-muted)", fontSize: 13 }}>
          {firstTime ? "We’ll lead the States tab with it. Change it any time." : "Stories from that state, from every outlet we follow."}
        </SheetDescription>
        <label style={{ display: "flex", alignItems: "center", gap: 8, margin: "12px 0 4px", padding: "0 12px", minHeight: 44, borderRadius: 12, border: "1px solid rgb(var(--c-fg-rgb) / 0.12)" }}>
          <Search className="w-4 h-4" aria-hidden="true" style={{ color: "var(--c-muted)" }} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search states" aria-label="Search states"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--c-ink)", fontSize: 15, minHeight: 40 }} />
        </label>
        {groups.length === 0 && <p style={{ color: "var(--c-muted)", padding: "12px 0", fontSize: 14 }}>No state matches &ldquo;{q}&rdquo;.</p>}
        {groups.map(([region, states]) => (
          <section key={region} aria-label={region} style={{ marginTop: 10 }}>
            <h3 style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--c-faint)", margin: "0 0 2px" }}>{region}</h3>
            {states.map((s) => (
              <button key={s} type="button" onClick={() => onPick(s)} data-testid={`pick-${s}`}
                style={{ display: "block", width: "100%", textAlign: "left", minHeight: 44, padding: "10px 0", background: "none", border: "none", borderBottom: "1px solid rgb(var(--c-fg-rgb) / 0.06)", color: "var(--c-ink2)", fontSize: 15, cursor: "pointer" }}>
                {s}
              </button>
            ))}
          </section>
        ))}
        <button type="button" onClick={onClose} style={{ width: "100%", minHeight: 48, marginTop: 14, borderRadius: 999, border: "1px solid rgb(var(--c-fg-rgb) / 0.12)", background: "none", color: "var(--c-sub)", fontWeight: 600, cursor: "pointer" }}>
          {firstTime ? "Skip" : "Close"}
        </button>
      </SheetContent>
    </Sheet>
  );
}
