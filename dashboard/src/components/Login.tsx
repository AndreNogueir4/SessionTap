import { useState, type FormEvent } from "react";
import { signInWithToken } from "../api";
import { LanguagePicker } from "./LanguagePicker";
import { t, tx } from "../i18n";

export function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await signInWithToken(value)) onSignedIn();
    else setError(true);
  }

  return (
    <div className="login">
      <div className="card">
        <h1>
          <img src="/favicon.svg" alt="" width="24" height="24" /> SessionTap
        </h1>
        <p>{t("login.intro")}</p>
        <pre className="cmd">sessiontap open</pre>
        <p className="muted">{t("login.orPopup")}</p>
        <details>
          <summary>{t("login.withToken")}</summary>
          <form onSubmit={submit}>
            <p className="muted">{tx("login.tokenHelp", { cmd: <code key="cmd">sessiontap token --show</code> })}</p>
            <input
              type="password"
              autoComplete="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              aria-label={t("login.tokenLabel")}
            />
            <button type="submit">{t("login.submit")}</button>
            {error && <p className="error">{t("login.rejected")}</p>}
          </form>
        </details>
        <LanguagePicker />
      </div>
    </div>
  );
}
