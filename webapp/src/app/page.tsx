import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function Home() {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user) redirect("/dashboard");

  return (
    <>
      <div className="topbar">
        <span className="brand">
          Console <span className="a">IA</span> — Studio
        </span>
        <span className="spacer" />
        <Link className="btn" href="/login">
          Se connecter
        </Link>
      </div>

      <main className="wrap" style={{ paddingTop: 90, paddingBottom: 80 }}>
        <p className="eyebrow">Production musicale augmentée par l'IA</p>
        <h1 style={{ fontSize: "2.6rem", maxWidth: 640, margin: "12px 0 18px" }}>
          Mixe, monte et arrange tes morceaux, avec un ingénieur du son IA.
        </h1>
        <p className="muted" style={{ maxWidth: 560, fontSize: "1.1rem" }}>
          Charge tes pistes, édite dans le navigateur, laisse Claude décider le
          mix et le master. Tes projets sont sauvegardés dans ton espace.
        </p>
        <div style={{ marginTop: 28 }}>
          <Link className="btn primary" href="/login">
            Commencer
          </Link>
        </div>
      </main>
    </>
  );
}
