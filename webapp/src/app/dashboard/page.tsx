import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Project } from "@/lib/types";
import NewProject from "./NewProject";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: projects } = await supabase
    .from("projects")
    .select("*")
    .order("updated_at", { ascending: false });

  const list = (projects ?? []) as Project[];

  return (
    <>
      <div className="topbar">
        <Link href="/dashboard" className="brand" style={{ textDecoration: "none" }}>
          Console <span className="a">IA</span> — Studio
        </Link>
        <span className="spacer" />
        <span className="muted" style={{ fontSize: 13 }}>{user.email}</span>
        <form action="/auth/signout" method="post">
          <button className="btn" type="submit">Déconnexion</button>
        </form>
      </div>

      <main className="wrap" style={{ paddingTop: 32, paddingBottom: 80 }}>
        <div className="card" style={{ marginBottom: 26 }}>
          <NewProject />
        </div>

        <h2 style={{ fontSize: 15, color: "var(--muted)", margin: "0 0 14px" }}>
          Tes projets ({list.length})
        </h2>

        {list.length === 0 ? (
          <p className="muted">Aucun projet pour l'instant. Crée-en un ci-dessus.</p>
        ) : (
          <div className="grid">
            {list.map((p) => (
              <Link key={p.id} href={`/project/${p.id}`} className="card project-card">
                <h3>{p.name}</h3>
                <div className="meta">
                  {new Date(p.updated_at).toLocaleDateString("fr-FR")}
                  {p.bpm ? ` · ${p.bpm} BPM` : ""}
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
