"use server";

import { headers } from "next/headers";
import { createClient } from "@/lib/supabase/server";

/** Envoie un lien magique de connexion à l'adresse fournie. */
export async function signInWithEmail(
  _prev: { message: string; ok: boolean },
  formData: FormData,
): Promise<{ message: string; ok: boolean }> {
  const email = String(formData.get("email") || "").trim();
  if (!email) return { message: "Renseigne ton email.", ok: false };

  const origin = headers().get("origin") ?? "";
  const supabase = createClient();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: `${origin}/auth/callback` },
  });

  if (error) return { message: error.message, ok: false };
  return { message: "Lien de connexion envoyé — regarde ta boîte mail.", ok: true };
}
