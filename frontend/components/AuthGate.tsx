"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  onAuthStateChanged,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  type User,
} from "@firebase/auth";
import { ArrowRight, Check, LoaderCircle } from "lucide-react";
import TallyBinder from "./TallyBinder";
import { firebaseAuth, firebaseConfigured } from "@/lib/firebase";

function authMessage(error: unknown) {
  const code =
    typeof error === "object" && error && "code" in error
      ? String(error.code)
      : "";
  const messages: Record<string, string> = {
    "auth/email-already-in-use": "That email already has an account. Sign in instead.",
    "auth/invalid-credential": "The email or password is incorrect.",
    "auth/invalid-email": "Enter a valid email address.",
    "auth/popup-closed-by-user": "Google sign-in was closed before it finished.",
    "auth/weak-password": "Use a password with at least six characters.",
  };
  return messages[code] || "Sign-in didn’t finish. Please try again.";
}

function AuthScreen() {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!firebaseAuth) return;
    setBusy(registering ? "Creating your binder…" : "Opening your binder…");
    setNotice("");
    try {
      if (registering)
        await createUserWithEmailAndPassword(firebaseAuth, email, password);
      else await signInWithEmailAndPassword(firebaseAuth, email, password);
    } catch (error) {
      setNotice(authMessage(error));
      setBusy("");
    }
  }

  async function google() {
    if (!firebaseAuth) return;
    setBusy("Connecting to Google…");
    setNotice("");
    try {
      await signInWithPopup(firebaseAuth, new GoogleAuthProvider());
    } catch (error) {
      setNotice(authMessage(error));
      setBusy("");
    }
  }

  async function reset() {
    if (!firebaseAuth || !email) {
      setNotice("Enter your email first, then request a reset link.");
      return;
    }
    setBusy("Sending reset link…");
    try {
      await sendPasswordResetEmail(firebaseAuth, email);
      setNotice("Password reset email sent.");
    } catch (error) {
      setNotice(authMessage(error));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="auth-shell">
      <main className="auth-main">
        <div className="auth-brand">
          <span className="brand-mark">TB</span>
          <span>TallyBinder</span>
          <span className="beta">EARLY EDITION</span>
        </div>
        <section className="auth-card" aria-labelledby="auth-heading">
          <div className="auth-art" aria-hidden="true">
            <span className="auth-card-back" />
            <span className="auth-card-front">
              <span>TB</span>
            </span>
          </div>
          <span className="eyebrow">YOUR COLLECTION, KEPT PRIVATE</span>
          <h1 id="auth-heading">
            {registering ? "Start your binder." : "Welcome back."}
          </h1>
          <p className="auth-intro">
            {registering
              ? "One account for your cards, photos, pricing and AI reviews."
              : "Sign in to pick up where you left off—on any device."}
          </p>
          <button className="google-button" onClick={() => void google()} disabled={!!busy}>
            <span className="google-mark">G</span>
            Continue with Google
            <ArrowRight size={17} />
          </button>
          <div className="auth-divider"><span>or use email</span></div>
          <form onSubmit={(event) => void submit(event)}>
            <label className="field">
              <span>Email</span>
              <input
                aria-label="Email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Password</span>
              <input
                aria-label="Password"
                type="password"
                autoComplete={registering ? "new-password" : "current-password"}
                minLength={6}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button className="primary full auth-submit" type="submit" disabled={!!busy}>
              {busy ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}
              {busy || (registering ? "Create account" : "Sign in")}
            </button>
          </form>
          {notice && <p className="auth-notice" role="status">{notice}</p>}
          {!registering && (
            <button className="text-button auth-reset" onClick={() => void reset()} disabled={!!busy}>
              Forgot your password?
            </button>
          )}
          <div className="auth-switch">
            <span>{registering ? "Already collecting here?" : "New to TallyBinder?"}</span>
            <button className="text-button" onClick={() => { setRegistering(!registering); setNotice(""); }}>
              {registering ? "Sign in" : "Create an account"}
            </button>
          </div>
        </section>
        <p className="auth-footnote">Each account has its own private binder, photos and AI budget.</p>
      </main>
    </div>
  );
}

export default function AuthGate() {
  const [ready, setReady] = useState(!firebaseConfigured);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!firebaseAuth) return;
    return onAuthStateChanged(firebaseAuth, (next) => {
      setUser(next);
      setReady(true);
    });
  }, []);

  if (!ready)
    return <div className="auth-loading"><LoaderCircle className="spin" /> Opening your binder…</div>;
  if (firebaseConfigured && !user) return <AuthScreen />;
  return <TallyBinder />;
}
