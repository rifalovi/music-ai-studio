"use client";

import { useFormStatus } from "react-dom";
import { createProject } from "./actions";

function Submit() {
  const { pending } = useFormStatus();
  return (
    <button className="btn primary" type="submit" disabled={pending}>
      {pending ? "Création…" : "Nouveau projet"}
    </button>
  );
}

export default function NewProject() {
  return (
    <form action={createProject} style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
      <div style={{ flex: 1 }}>
        <label htmlFor="name">Nom du projet</label>
        <input id="name" name="name" placeholder="Mon morceau" />
      </div>
      <Submit />
    </form>
  );
}
