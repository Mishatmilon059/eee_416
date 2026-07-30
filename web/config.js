// Supabase connection for the data-collection app.
//
// Fill these in after creating your Supabase project:
//   Project Settings -> API -> Project URL, and the "anon public" key.
//
// The anon key is designed to be public and ships in every client, so it is
// safe in git. It is NOT the service_role key -- never put that one here.
//
// Leave SUPABASE_URL empty to run fully offline: every row still gets logged
// to localStorage and can be exported as CSV. Collection is never blocked by
// a missing or broken backend.

export const SUPABASE_URL = "";
export const SUPABASE_ANON_KEY = "";

// Identifies which machine a row came from, so you can tell the two laptops
// apart in the merged dataset. Auto-generated and remembered per browser.
export const DEVICE_ID_KEY = "braille.device_id";
