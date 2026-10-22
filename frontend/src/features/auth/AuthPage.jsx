import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { api, setCsrfToken } from "../../lib/api";
export function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [message, setMessage] = useState("");
  const mutation = useMutation({
    mutationFn: async (values) =>
      api(`/api/v1/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: (result) => {
      setCsrfToken(result.csrf_token);
      onAuthenticated(result.user, result.csrf_token);
    },
    onError: (error) => setMessage(error.message),
  });
  function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    mutation.mutate({
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
  }
  return (
    <div className="auth-screen">
      <aside className="auth-product" aria-labelledby="auth-product-title">
        <div className="brand auth-brand">
          <div className="brand-symbol" aria-hidden="true">
            GS
          </div>
          <div className="brand-copy">
            <b>GLOBAL SIGNALS</b>
            <small>MARKET RESEARCH</small>
          </div>
        </div>
        <div className="auth-product-copy">
          <p className="eyebrow">GLOBAL SIGNALS · PAPER ACCOUNT</p>
          <h1 id="auth-product-title">
            Research markets.
            <br />
            Trade in simulation.
          </h1>
          <p className="auth-product-intro">
            A single workspace for provider-sourced market data, virtual
            portfolio accounting and historical strategy research.
          </p>
        </div>
        <div className="auth-product-modules">
          <article className="auth-module">
            <div>
              <span>01</span>
              <h2>Market data</h2>
            </div>
            <p>
              Read provider-attributed quotes and historical open, high, low and
              close prices.
            </p>
          </article>
          <article className="auth-module">
            <div>
              <span>02</span>
              <h2>Paper portfolio</h2>
            </div>
            <p>
              Review virtual INR cash, holdings, simulated fills, fees and
              slippage.
            </p>
          </article>
          <article className="auth-module">
            <div>
              <span>03</span>
              <h2>Strategy research</h2>
            </div>
            <p>
              Configure versioned rules and replay historical datasets without
              placing real orders.
            </p>
          </article>
        </div>
        <p className="auth-sidebar-footer">
          Virtual account · No real order execution
        </p>
      </aside>
      <div className="auth-main">
        <header className="auth-header">
          <div className="brand auth-brand auth-mobile-brand">
            <div className="brand-symbol" aria-hidden="true">
              GS
            </div>
            <div className="brand-copy">
              <b>GLOBAL SIGNALS</b>
              <small>MARKET RESEARCH</small>
            </div>
          </div>
          <span className="auth-header-note">
            <ShieldCheck size={14} /> Secure sign-in
          </span>
        </header>
        <main
          className="auth-form-panel"
          aria-label="Sign in to Global Signals"
        >
          <div className="auth-card">
            <p className="eyebrow">PAPER TRADING WORKSPACE</p>
            <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
            <p className="muted-copy">
              {mode === "login"
                ? "Sign in to your isolated virtual portfolio."
                : "Create a secure account with a virtual-only trading portfolio."}
            </p>
            <form className="auth-form" onSubmit={submit}>
              <label>
                Email address
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  maxLength={254}
                  required
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  name="password"
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  minLength={12}
                  maxLength={128}
                  required
                />
                <small>Use at least 12 characters.</small>
              </label>
              <button className="btn btn-primary" disabled={mutation.isPending}>
                {mutation.isPending
                  ? "Please wait…"
                  : mode === "login"
                    ? "Sign in"
                    : "Create account"}
              </button>
            </form>
            {message && (
              <div className="inline-message error" role="alert">
                {message}
              </div>
            )}
            <button
              className="auth-switch"
              onClick={() => {
                setMessage("");
                setMode(mode === "login" ? "register" : "login");
              }}
            >
              {mode === "login"
                ? "New to Global Signals? Create an account"
                : "Already registered? Sign in"}
            </button>
            <div className="auth-note">
              <ShieldCheck size={15} /> Simulation only. No broker credentials
              are requested or used.
            </div>
            <p className="reset-note">
              Password reset email is unavailable until an authorized email
              provider is configured.
            </p>
          </div>
        </main>
        <footer className="auth-footer">
          <span>Global Signals · Virtual account environment</span>
          <span>No broker connection · No real order execution</span>
        </footer>
      </div>
    </div>
  );
}
