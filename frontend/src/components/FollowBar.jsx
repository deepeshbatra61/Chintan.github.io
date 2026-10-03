import React, { useEffect, useState } from "react";
import axios from "axios";
import { Plus, Check, Share2 } from "lucide-react";
import { Share } from "@capacitor/share";
import { toast } from "sonner";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "./ui/sheet";
import { enablePush, permissionState, getAsk } from "../lib/push";

const API = "https://chintangithubio-production.up.railway.app/api";
const SHARE_BASE = "https://chintan.news";

// Sticky "Follow this story" bar on a developing story (design review: story
// direction B). Every case in 2B is handled so nobody follows into silence:
//   guest            → sign-in prompt ("follow")
//   push never asked → soft ask "Get a ping when this story moves"; declining
//                      still follows (it's in the sidebar)
//   OS-denied        → follows, plus "Pings are off in phone settings"
//   pending / error  → spinner, then revert with a toast
export default function FollowBar({ storyId, title, shareArticleId, user, onNeedSignIn, onHeight }) {
  const [following, setFollowing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [ask, setAsk] = useState(false);

  useEffect(() => {
    if (!user) return;
    let alive = true;
    axios.get(`${API}/follows`, { withCredentials: true })
      .then((r) => { if (alive) setFollowing((r.data.follows || []).some((f) => f.story_id === storyId)); })
      .catch(() => {});
    return () => { alive = false; };
  }, [user, storyId]);

  useEffect(() => { onHeight?.(note ? 104 : 84); }, [note, onHeight]);

  async function afterFollow() {
    const perm = await permissionState();
    if (perm === "unsupported") return;                     // web: nothing to ask
    if (perm === "denied") { setNote("Pings are off in phone settings."); return; }
    const a = await getAsk().catch(() => ({}));
    if (perm === "granted" && a?.optedIn) return;           // already set up
    setAsk(true);
  }

  async function toggle() {
    if (!user) { onNeedSignIn(); return; }
    if (busy) return;
    setBusy(true);
    try {
      if (following) {
        await axios.delete(`${API}/follows/${encodeURIComponent(storyId)}`, { withCredentials: true });
        setFollowing(false); setNote("");
      } else {
        await axios.post(`${API}/follows`, { story_id: storyId }, { withCredentials: true });
        setFollowing(true);
        await afterFollow();
      }
    } catch (e) {
      toast.error(e?.response?.status === 404 ? "This story isn’t developing any more." : "Couldn’t follow, try again");
    } finally {
      setBusy(false);
    }
  }

  async function turnOnPings() {
    setAsk(false);
    const { permission } = await enablePush();
    if (permission === "granted") toast("You’ll get a ping when this story moves.");
    else setNote("Following · in your sidebar");
  }

  const share = async () => {
    try { await Share.share({ title, text: title, url: shareArticleId ? `${SHARE_BASE}/article/${shareArticleId}` : SHARE_BASE, dialogTitle: "Share this story" }); }
    catch { /* dismissed */ }
  };

  return (
    <>
      <div
        data-testid="follow-bar"
        style={{
          position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 30,
          padding: "12px 16px calc(14px + var(--sab, 0px))",
          background: "linear-gradient(to top, var(--c-bg) 72%, rgb(var(--c-bg-rgb) / 0))",
        }}
      >
        <div style={{ maxWidth: 640, margin: "0 auto" }}>
          {note && (
            <p role="status" style={{ margin: "0 0 8px", textAlign: "center", fontSize: 12.5, color: "var(--c-muted)" }}>
              {note}
            </p>
          )}
          <div style={{ display: "flex", gap: 10 }}>
            <button
              type="button"
              aria-pressed={following}
              onClick={toggle}
              disabled={busy}
              data-testid="follow-button"
              style={{
                flex: 1, minHeight: 48, borderRadius: 999, display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                fontFamily: "'Manrope', sans-serif", fontWeight: 600, fontSize: 14.5, cursor: busy ? "default" : "pointer",
                border: `1px solid ${following ? "rgba(220,38,38,0.35)" : "rgba(220,38,38,0.55)"}`,
                background: following ? "rgba(220,38,38,0.14)" : "transparent",
                color: following ? "var(--c-accent-ink)" : "var(--c-ink)",
              }}
            >
              {busy ? <span className="animate-spin" style={{ width: 16, height: 16, borderRadius: "50%", border: "2px solid currentColor", borderTopColor: "transparent" }} aria-label="Working" />
                : following ? <><Check className="w-4 h-4" aria-hidden="true" /> Following</>
                : <><Plus className="w-4 h-4" aria-hidden="true" /> Follow this story</>}
            </button>
            <button type="button" onClick={share} aria-label="Share this story"
              style={{ minHeight: 48, minWidth: 48, padding: "0 16px", borderRadius: 999, border: "1px solid rgb(var(--c-fg-rgb) / 0.10)", background: "none", color: "var(--c-sub)", display: "grid", placeItems: "center", cursor: "pointer" }}>
              <Share2 className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      <Sheet open={ask} onOpenChange={(o) => { if (!o) { setAsk(false); setNote("Following · in your sidebar"); } }}>
        <SheetContent side="bottom" style={{ background: "var(--c-surface)", borderTopLeftRadius: 20, borderTopRightRadius: 20 }}>
          <SheetTitle style={{ fontFamily: "'Playfair Display', 'Georgia', serif", fontSize: 20, color: "var(--c-ink)" }}>
            Get a ping when this story moves
          </SheetTitle>
          <SheetDescription style={{ color: "var(--c-muted)", fontSize: 14, lineHeight: 1.5 }}>
            Only when a new outlet reports something new. At most three a day for a story, never at night.
          </SheetDescription>
          <button type="button" onClick={turnOnPings} data-testid="follow-ask-yes"
            style={{ width: "100%", minHeight: 48, marginTop: 16, borderRadius: 999, border: "none", background: "linear-gradient(180deg, #DC2626, #B91C1C)", color: "#fff", fontWeight: 600, cursor: "pointer" }}>
            Turn on pings
          </button>
          <button type="button" onClick={() => { setAsk(false); setNote("Following · in your sidebar"); }}
            style={{ width: "100%", minHeight: 44, marginTop: 8, background: "none", border: "none", color: "var(--c-muted)", cursor: "pointer" }}>
            Not now
          </button>
        </SheetContent>
      </Sheet>
    </>
  );
}
