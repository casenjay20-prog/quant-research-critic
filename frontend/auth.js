// frontend/auth.js
const SUPABASE_URL = "https://nemtiabuyafncimzybvp.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_pAY6CY508CFM3v_la3TJUw_J6fHmPj6";

const _sb = supabase.createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);

async function getSession() {
  const { data } = await _sb.auth.getSession();
  return data.session ?? null;
}

async function getUser() {
  const session = await getSession();
  return session?.user ?? null;
}

async function sendMagicLink(email) {
  const { error } = await _sb.auth.signInWithOtp({
    email: email.trim().toLowerCase(),
    options: {
      emailRedirectTo: "https://quantcritic.com/app.html",
    },
  });
  if (error) throw error;
  return true;
}

async function signOut() {
  await _sb.auth.signOut();
}

async function getUserTier() {
  const session = await getSession();
  if (!session) return "free";
  try {
    const res = await fetch(
      "https://quant-research-critic-production.up.railway.app/v1/entitlement",
      { headers: { Authorization: `Bearer ${session.access_token}` } }
    );
    if (!res.ok) return "free";
    const data = await res.json();
    return data.tier ?? "free";
  } catch {
    return "free";
  }
}

async function isPro() {
  const tier = await getUserTier();
  return tier === "pro" || tier === "institutional";
}

function onAuthStateChange(callback) {
  _sb.auth.onAuthStateChange((_event, session) => callback(session));
}

async function handleAuthRedirect() {
  await _sb.auth.getSession();
}