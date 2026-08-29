export type Project = {
  id: string;
  user_id: string;
  name: string;
  bpm: number | null;
  created_at: string;
  updated_at: string;
};

export type Track = {
  id: string;
  project_id: string;
  name: string;
  kind: "audio" | "stem" | "master" | "generated";
  storage_path: string | null;
  created_at: string;
};
