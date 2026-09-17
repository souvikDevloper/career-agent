import { useState, type FormEvent } from "react";
import { confirmSignUp, signIn, signUp, startExampleWorkspace } from "../lib/auth";
import { Link, useRouter } from "../lib/router";
import { BrandMark } from "../components/Shell";
import { Spinner, useToast } from "../components/ui";
import { IBolt } from "../components/Icons";

export function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"form" | "verify">("form");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const { navigate } = useRouter();
  const toast = useToast();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      if (mode === "login") {
        await signIn(email, password);
        navigate("/app");
      } else if (stage === "form") {
        await signUp(email, password);
        setStage("verify");
        toast("We emailed you a 6-digit code.", "success");
      } else {
        await confirmSignUp(email, code);
        await signIn(email, password);
        navigate("/app/profile");
      }
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="card fade-in">
        <Link to="/" className="brand"><BrandMark /> Career Agent</Link>
        <h1>{mode === "login" ? "Welcome back" : stage === "verify" ? "Check your email" : "Create your agent"}</h1>
        <p className="muted small">
          {mode === "login" ? "Sign in to your workspace." : stage === "verify" ? `Enter the code sent to ${email}.` : "Your data stays private to your account. You can delete it anytime."}
        </p>
        <form onSubmit={submit} style={{ marginTop: 22 }}>
          {stage === "form" && (
            <>
              <div className="field">
                <label className="label" htmlFor="email">Email</label>
                <input id="email" className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="field">
                <label className="label" htmlFor="password">Password</label>
                <input id="password" className="input" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} />
                {mode === "signup" && <div className="hint">At least 10 characters with upper, lower case and a number.</div>}
              </div>
            </>
          )}
          {stage === "verify" && (
            <div className="field">
              <label className="label" htmlFor="code">Verification code</label>
              <input id="code" className="input mono" inputMode="numeric" required value={code} onChange={(e) => setCode(e.target.value)} />
            </div>
          )}
          {err && <div className="banner" style={{ marginTop: 14, color: "#fecdd3", borderColor: "rgba(251,113,133,.4)", background: "rgba(251,113,133,.08)" }}>{err}</div>}
          <button className="btn primary lg" style={{ width: "100%", marginTop: 18 }} disabled={busy}>
            {busy && <Spinner />} {mode === "login" ? "Sign in" : stage === "verify" ? "Verify and continue" : "Create account"}
          </button>
        </form>
        <div className="divider" />
        <button
          className="btn"
          style={{ width: "100%" }}
          onClick={async () => {
            setBusy(true);
            try {
              await startExampleWorkspace();
              navigate("/app");
            } catch (e3) {
              setErr((e3 as Error).message);
              setBusy(false);
            }
          }}
        >
          <IBolt size={16} /> Try the example workspace instead
        </button>
        <p className="small muted" style={{ marginTop: 16, textAlign: "center" }}>
          {mode === "login" ? <>New here? <Link to="/signup" className="grad-text">Create an account</Link></> : <>Have an account? <Link to="/login" className="grad-text">Sign in</Link></>}
        </p>
      </div>
    </div>
  );
}
