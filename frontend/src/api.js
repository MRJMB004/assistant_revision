export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
export const AUTH_KEY = "reviser:auth";

const authToken = () => {
  try {
    return JSON.parse(localStorage.getItem(AUTH_KEY))?.access_token ?? null;
  } catch {
    return null;
  }
};

/** Extrait un message lisible d'une erreur FastAPI (detail string ou liste 422). */
function errorMessage(body, status) {
  const d = body?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    return d.map((e) => `${(e.loc || []).slice(1).join(".") || "champ"} : ${e.msg}`).join(" · ");
  }
  return `Erreur ${status}`;
}

export async function api(path, { method = "GET", body } = {}) {
  let res;
  try {
    const token = authToken();
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("API injoignable. Vérifie que le backend tourne sur " + API_BASE);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem(AUTH_KEY);
      window.dispatchEvent(new Event("reviser:auth-expired"));
    }
    const err = new Error(errorMessage(data, res.status));
    err.status = res.status;
    throw err;
  }
  return data;
}

/** N'autorise que les liens http(s) (les ressources peuvent venir d'APIs externes / d'un LLM). */
export function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : "#";
  } catch {
    return "#";
  }
}
