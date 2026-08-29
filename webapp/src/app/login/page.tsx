"use client";

import { useFormState, useFormStatus } from "react-dom";
import Link from "next/link";
import { signInWithEmail } from "./actions";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button className="btn primary" type="submit" disabled={pending} style={{ width: "100%" }}>
      {pending ? "Envoi…" : "Recevoir le lien de connexion"}
    </button>
  );
}

export default function LoginPage() {
  const [state, formAction] = useFormState(signInWithEmail, { message: "", ok: false });

  return (
    <>
      <div className="topbar">
        <Link href="/" className="brand" style={{ textDecoration: "none" }}>
          Console <span className="a">IA</span> — Studio
        </Link>
      </div>

      <main className="wrap" style={{ maxWidth: 420, paddingTop: 80 }}>
        <p className="eyebrow">Connexion</p>
        <h1 style={{ fontSize: "1.6rem", margin: "10px 0 20px" }}>Accède à ton studio</h1>

        <form action={formAction} className="card">
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" required placeholder="toi@exemple.com" />
          <div style={{ marginTop: 16 }}>
            <SubmitButton />
          </div>
          {state.message && (
            <p className={state.ok ? "eyebrow" : "notice"} style={{ marginTop: 14 }}>
              {state.message}
            </p>
          )}
        </form>
        <p className="muted" style={{ fontSize: 13, marginTop: 14 }}>
          Connexion sans mot de passe : on t'envoie un lien à usage unique.
        </p>
      </main>
    </>
  );
}
