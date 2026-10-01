import { useEffect, useState } from "react";
import { api } from "./api";
import { useApp } from "./AppContext";

/** Charge l'historique complet et declenche les rappels de retention dedupliques. */
export function useRetention(modules) {
  const { toast } = useApp();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (modules.length === 0) {
      setData([]);
      setError("");
      return;
    }
    setLoading(true);
    setError("");
    Promise.all([api("/retention"), api("/retention/notifications/refresh", { method: "POST" })])
      .then(([res]) => !cancelled && setData(res))
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          toast(err.message, true);
        }
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [modules, toast]);

  return { data, loading, error };
}
