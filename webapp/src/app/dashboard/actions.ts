"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

/** Crée un projet pour l'utilisateur courant et l'ouvre. */
export async function createProject(formData: FormData) {
  const name = String(formData.get("name") || "").trim() || "Nouveau projet";
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data, error } = await supabase
    .from("projects")
    .insert({ user_id: user.id, name })
    .select("id")
    .single();

  if (error || !data) throw new Error(error?.message ?? "Création impossible");
  redirect(`/project/${data.id}`);
}

/** Supprime un projet (et ses pistes via cascade). */
export async function deleteProject(formData: FormData) {
  const id = String(formData.get("id") || "");
  const supabase = createClient();
  await supabase.from("projects").delete().eq("id", id);
  revalidatePath("/dashboard");
}
