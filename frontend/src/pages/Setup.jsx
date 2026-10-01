import { useState } from "react";
import { BookOpen, LogIn, UserPlus } from "lucide-react";
import { api } from "../api";
import { useApp } from "../AppContext.jsx";

export default function Setup({ onNavigate }) {
  const { setAuth, toast } = useApp();
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const isRegistering = mode === "register";

  const changeMode = (nextMode) => {
    setMode(nextMode);
    setPassword("");
    setConfirmation("");
  };

  const submit = async (event) => {
    event.preventDefault();
    if (isRegistering && password !== confirmation) {
      toast("Les mots de passe ne correspondent pas.", true);
      return;
    }

    setBusy(true);
    try {
      const session = await api(isRegistering ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: isRegistering
          ? { name: name.trim(), email: email.trim(), password }
          : { email: email.trim(), password },
      });
      setAuth(session);
      toast(`Bienvenue, ${session.user.name}.`);
      onNavigate("dashboard");
    } catch (err) {
      toast(err.message, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-intro" aria-label="Réviser">
        <div className="auth-brand"><span><BookOpen size={24} /></span>Réviser</div>
        <p>Organise tes révisions, suis tes progrès et avance à ton rythme.</p>
      </section>

      <form className="auth-card" onSubmit={submit}>
        <div className="auth-card-head">
          <h1>{isRegistering ? "Créer un compte" : "Se connecter"}</h1>
          <p>{isRegistering ? "Commence ton parcours de révision." : "Content de te revoir."}</p>
        </div>
        {isRegistering && <label>Nom<input type="text" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex. Alice Dupont" required /></label>}
        <label>Email<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="alice@exemple.com" required /></label>
        <label>Mot de passe<input type="password" autoComplete={isRegistering ? "new-password" : "current-password"} minLength={isRegistering ? 8 : undefined} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={isRegistering ? "8 caractères minimum" : "Votre mot de passe"} required /></label>
        {isRegistering && <label>Confirmer le mot de passe<input type="password" autoComplete="new-password" minLength="8" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="Retapez votre mot de passe" required /></label>}
        <button type="submit" className="btn-primary auth-submit" disabled={busy}>
          {isRegistering ? <UserPlus size={18} /> : <LogIn size={18} />}
          {busy ? (isRegistering ? "Création..." : "Connexion...") : (isRegistering ? "Créer mon compte" : "Se connecter")}
        </button>
        <div className="auth-switch">
          {isRegistering ? "Déjà un compte ? " : "Pas encore de compte ? "}
          <button type="button" onClick={() => changeMode(isRegistering ? "login" : "register")}>{isRegistering ? "Se connecter" : "Créer un compte"}</button>
        </div>
      </form>
    </main>
  );
}
