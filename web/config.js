// Supabase connection for the data-collection app.
//
// The key below is the PUBLISHABLE key. It is designed to ship in every client
// and is safe in git -- it grants only what supabase/schema.sql's RLS policies
// allow (insert and select on `attempts`, nothing else).
//
// NEVER put the secret / service_role key in this file. That key bypasses RLS
// completely, and this file is served to every browser that opens the app.
// It belongs in .env, which is gitignored. See .env.example.
//
// Leave SUPABASE_URL empty to run fully offline: every row still gets logged
// to localStorage and can be exported as CSV. Collection is never blocked by
// a missing or broken backend.

export const SUPABASE_URL = "https://rufaacgatrebsyxnyfbq.supabase.co";
export const SUPABASE_ANON_KEY = "sb_publishable_lI3qv5Xk44GAhzL4R7I2GA_4k1aUar-";

// Identifies which machine a row came from, so you can tell the two laptops
// apart in the merged dataset. Auto-generated and remembered per browser.
export const DEVICE_ID_KEY = "braille.device_id";
