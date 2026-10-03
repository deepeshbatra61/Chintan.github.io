import React, { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { compactAge, subscribeMinute } from "../lib/time";

/** Clock + exact age ("13m") for the card footer, styled like the view
 * counter beside it. Re-renders once a minute from one shared timer. */
export default function Age({ iso }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => subscribeMinute(setNow), []);
  const label = compactAge(iso, now);
  if (!label) return null;
  return (
    <span className="flex items-center gap-1" data-testid="card-age">
      <Clock className="w-3 h-3" aria-hidden="true" />
      <time dateTime={iso} aria-label={label === "now" ? "Just now" : `${label} ago`}>{label}</time>
    </span>
  );
}
