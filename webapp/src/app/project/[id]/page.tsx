import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Project, Track } from "@/lib/types";
import Editor from "./Editor";

export const dynamic = "force-dynamic";

export default async function ProjectPage({ params }: { params: { id: string } }) {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: project } = await supabase
    .from("projects")
    .select("*")
    .eq("id", params.id)
    .single();
  if (!project) notFound();

  const { data: tracks } = await supabase
    .from("tracks")
    .select("*")
    .eq("project_id", params.id)
    .order("created_at", { ascending: true });

  return (
    <>
      <div className="topbar">
        <Link href="/dashboard" className="btn">← Projets</Link>
        <span className="brand" style={{ marginLeft: 6 }}>{(project as Project).name}</span>
      </div>
      <Editor
        projectId={(project as Project).id}
        userId={user.id}
        initialTracks={(tracks ?? []) as Track[]}
        engineUrl={process.env.NEXT_PUBLIC_ENGINE_URL ?? ""}
      />
    </>
  );
}
