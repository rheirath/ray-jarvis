import { useEffect, useRef, useState } from "react";

const cache = new Map<string, Promise<string>>();

function translate(text: string): Promise<string> {
  const existing = cache.get(text);
  if (existing) return existing;
  const pending = fetch("/api/chats/voice-subtitle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }).then(async (response) => {
    if (!response.ok) throw new Error("Subtitle unavailable");
    const result = await response.json() as { text: string; language: string };
    if (!result.text || result.language !== "nl") throw new Error("Invalid subtitle");
    return result.text;
  });
  cache.set(text, pending);
  if (cache.size > 256) cache.delete(cache.keys().next().value!);
  return pending;
}

export function DutchSubtitle({ text, live }: { text: string; live: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [result, setResult] = useState<{ source: string; text: string } | null>(null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    if (live || !ref.current) return;
    let disposed = false;
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      translate(text).then((translated) => {
        if (!disposed) setResult({ source: text, text: translated });
      }).catch(() => {
        if (!disposed) setFailed(text);
      });
    });
    observer.observe(ref.current);
    return () => { disposed = true; observer.disconnect(); };
  }, [text, live]);
  return <span ref={ref} lang={failed === text ? "en" : "nl"}>
    {result?.source === text ? result.text : failed === text ? <>
      <span className="block text-sm text-muted-foreground" lang="nl">Vertaling niet beschikbaar · Engelse tekst</span>
      {text}
    </> : <span className="text-muted-foreground">{live ? "Jarvis antwoordt in het Engels…" : "Nederlandse vertaling laden…"}</span>}
  </span>;
}
