import { useCallback, useEffect, useState } from "react";
import { api, signedIn, signInFromUrl, type Domain, type Status } from "./api";
import { ApiView } from "./components/ApiView";
import { LiveFeed } from "./components/LiveFeed";
import { Login } from "./components/Login";
import { Requests } from "./components/Requests";
import { SessionView } from "./components/SessionView";
import { Settings } from "./components/Settings";
import { Sidebar } from "./components/Sidebar";
import { t, useLang } from "./i18n";

type Tab = "requests" | "session" | "api";
type View = { kind: "domain"; domain: string; tab: Tab } | { kind: "live" } | { kind: "settings" };

export function App() {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [view, setView] = useState<View>({ kind: "live" });
  const lang = useLang();

  useEffect(() => {
    void signInFromUrl().then((ok) => {
      setAuthed(ok);
      setReady(true);
    });
  }, []);

  const reload = useCallback(async () => {
    try {
      const [d, s] = await Promise.all([api.domains(), api.status()]);
      setDomains(d);
      setStatus(s);
    } catch {
      setAuthed(signedIn());
    }
  }, []);

  useEffect(() => {
    if (!authed) return;
    void reload();
    const timer = setInterval(() => void reload(), 10_000);
    return () => clearInterval(timer);
  }, [authed, reload]);

  if (!ready) return null;
  if (!authed) return <Login key={lang} onSignedIn={() => setAuthed(true)} />;

  const selected = view.kind === "domain" ? view.domain : null;

  return (
    <div className="layout" key={lang}>
      <Sidebar
        domains={domains}
        status={status}
        selected={selected}
        view={view.kind}
        onSelect={(domain) => setView({ kind: "domain", domain, tab: "requests" })}
        onLive={() => setView({ kind: "live" })}
        onSettings={() => setView({ kind: "settings" })}
      />
      <main>
        {view.kind === "live" && <LiveFeed onOpen={(domain) => setView({ kind: "domain", domain, tab: "requests" })} />}
        {view.kind === "settings" && <Settings domains={domains} status={status} onChange={reload} />}
        {view.kind === "domain" && (
          <>
            <header className="page-header">
              <h1>{view.domain}</h1>
              <nav className="tabs" role="tablist">
                {(["requests", "session", "api"] as Tab[]).map((tab) => (
                  <button
                    key={tab}
                    role="tab"
                    aria-selected={view.tab === tab}
                    className={view.tab === tab ? "active" : ""}
                    onClick={() => setView({ ...view, tab })}
                  >
                    {t(`tab.${tab}`)}
                  </button>
                ))}
              </nav>
            </header>
            {view.tab === "requests" && <Requests domain={view.domain} />}
            {view.tab === "session" && <SessionView domain={view.domain} />}
            {view.tab === "api" && <ApiView domain={view.domain} />}
          </>
        )}
      </main>
    </div>
  );
}
