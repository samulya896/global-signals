import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { api, setCsrfToken } from "../lib/api";
import type { AuthUser } from "../lib/api";

export function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (user: AuthUser, csrf: string) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState("");

  const mutation = useMutation({
    mutationFn: async (values: { email: string; password: string }) =>
      api<{ user: AuthUser; csrf_token: string }>(`/api/v1/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: (result) => {
      setCsrfToken(result.csrf_token);
      onAuthenticated(result.user, result.csrf_token);
    },
    onError: (error: Error) => setMessage(error.message),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    mutation.mutate({
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="brand auth-brand">
          <div className="brand-symbol">G<span>.</span></div>
          <div><b>GLOBAL SIGNALS</b><small>SIMULATED MARKET RESEARCH</small></div>
        </div>
        <div className="eyebrow">PAPER TRADING WORKSPACE</div>
        <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p className="muted-copy">
          {mode === "login"
            ? "Sign in to your isolated virtual portfolio."
            : "Create a secure account with a virtual-only trading portfolio."}
        </p>
        <form className="auth-form" onSubmit={submit}>
          <label>
            Email address
            <input type="email" name="email" autoComplete="email" maxLength={254} required />
          </label>
          <label>
            Password
            <input
              type="password"
              name="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={12}
              maxLength={128}
              required
            />
            <small>Use at least 12 characters.</small>
          </label>
          <button className="btn btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
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
          <ShieldCheck size={15} /> Simulation only. No broker credentials are requested or used.
        </div>
        <p className="reset-note">
          Password reset email is unavailable until an authorized email provider is configured.
        </p>
      </div>
    </div>
  );
}
