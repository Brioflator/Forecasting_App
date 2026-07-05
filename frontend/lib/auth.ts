// AuthProvider seam, client side (doc 4 §4). Mirrors doc 1's server seam.
//
// Local: return a fixed session immediately; the sign-in routes are skipped —
// zero friction, matching the LocalAuthProvider (doc 1 §6.6). Production swaps
// this for supabase-js sign-in and attaches the JWT as a bearer token; only the
// anon key ships in the client. NEXT_PUBLIC_APP_EDITION selects the impl.

export interface Session {
  token: string | null;
  orgName: string;
}

export function getSession(): Session {
  const edition = process.env.NEXT_PUBLIC_APP_EDITION ?? "local";
  if (edition === "local") {
    // The local api ignores the Authorization header entirely.
    return { token: null, orgName: "Local Organization" };
  }
  // Production auth (Supabase JWT) is MVP+ scope (plan 05 §4).
  throw new Error("production auth not wired in this build");
}

export function authHeaders(): Record<string, string> {
  const { token } = getSession();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
