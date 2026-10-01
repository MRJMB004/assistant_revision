const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(value) {
  const date = value instanceof Date ? new Date(value) : new Date(value);
  date.setHours(0, 0, 0, 0);
  return date;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

const dateKey = (date) => {
  const value = startOfDay(date);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
};

function applyScore(state, score) {
  const quality = Math.round((Number(score) / 100) * 5);
  let { ef, reps, interval } = state;
  if (quality < 3) {
    reps = 0;
    interval = 1;
  } else {
    reps += 1;
    if (reps === 1) interval = 1;
    else if (reps === 2) interval = 3;
    else interval = Math.max(1, Math.round(interval * ef));
  }
  const misses = 5 - quality;
  return { ef: Math.max(1.3, ef + 0.1 - misses * (0.08 + misses * 0.02)), reps, interval };
}

/**
 * Rejoue l'historique de scores avec les regles SM-2 simplifiees.
 * Cette fonction est pure afin de pouvoir etre testee et utilisee par l'interface.
 */
export function getStatus(history = [], now = new Date()) {
  if (!history.length) {
    return {
      interval: 1,
      ef: 2.5,
      reps: 0,
      daysSince: null,
      nextDate: null,
      retention: null,
      overdueDays: 0,
    };
  }

  let ef = 2.5;
  let reps = 0;
  let interval = 1;
  const ordered = [...history].sort((left, right) => new Date(left.date) - new Date(right.date));

  for (const item of ordered) {
    const q = Math.round((Number(item.score) / 100) * 5);
    if (q < 3) {
      reps = 0;
      interval = 1;
    } else {
      reps += 1;
      if (reps === 1) interval = 1;
      else if (reps === 2) interval = 3;
      else interval = Math.max(1, Math.round(interval * ef));
    }
    const misses = 5 - q;
    ef = Math.max(1.3, ef + 0.1 - misses * (0.08 + misses * 0.02));
  }

  const lastDate = startOfDay(ordered.at(-1).date);
  const today = startOfDay(now);
  const daysSince = Math.max(0, Math.floor((today - lastDate) / DAY_MS));
  const nextDate = addDays(lastDate, interval);

  return {
    interval,
    ef,
    reps,
    daysSince,
    nextDate,
    retention: Math.pow(0.9, daysSince / interval),
    overdueDays: Math.max(0, daysSince - interval),
  };
}

/**
 * Produit une valeur journaliere : le dernier score remonte la courbe, qui
 * redescend ensuite selon l'intervalle SM-2 actif a cette date.
 */
export function getRetentionTimeline(history = [], now = new Date(), daysAhead = 7) {
  if (!history.length) return [];
  const ordered = [...history].sort((left, right) => new Date(left.date) - new Date(right.date));
  const firstDate = startOfDay(ordered[0].date);
  const endDate = addDays(startOfDay(now), daysAhead);
  const points = [];
  let eventIndex = 0;
  let current = null;
  let state = { ef: 2.5, reps: 0, interval: 1 };

  for (let day = new Date(firstDate); day <= endDate; day = addDays(day, 1)) {
    while (eventIndex < ordered.length && startOfDay(ordered[eventIndex].date) <= day) {
      const item = ordered[eventIndex];
      state = applyScore(state, item.score);
      current = { score: Number(item.score), date: startOfDay(item.date), interval: state.interval };
      eventIndex += 1;
    }
    if (current) {
      const elapsed = Math.max(0, Math.floor((day - current.date) / DAY_MS));
      points.push({ date: new Date(day), value: Math.max(0, Math.min(100, current.score * Math.pow(0.9, elapsed / current.interval))) });
    }
  }
  return points;
}

export function getAverageRetentionTimeline(histories = [], now = new Date(), daysAhead = 7) {
  const timelines = histories.map((history) => getRetentionTimeline(history, now, daysAhead)).filter(Boolean);
  const byDay = new Map();
  for (const timeline of timelines) {
    for (const point of timeline) {
      const key = dateKey(point.date);
      const values = byDay.get(key) ?? { date: point.date, values: [] };
      values.values.push(point.value);
      byDay.set(key, values);
    }
  }
  return [...byDay.values()]
    .sort((left, right) => left.date - right.date)
    .map(({ date, values }) => ({ date, value: values.reduce((sum, value) => sum + value, 0) / values.length }));
}
