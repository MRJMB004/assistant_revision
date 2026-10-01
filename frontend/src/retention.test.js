import test from "node:test";
import assert from "node:assert/strict";
import { getRetentionTimeline, getStatus } from "./retention.js";

const NOW = new Date("2026-10-10T12:00:00");

test("un echec apres des reussites remet l'intervalle a un jour", () => {
  const status = getStatus([
    { date: "2026-10-01", score: 100 },
    { date: "2026-10-02", score: 100 },
    { date: "2026-10-05", score: 40 },
  ], NOW);
  assert.equal(status.interval, 1);
  assert.equal(status.reps, 0);
});

test("les reussites successives donnent 1, 3 puis intervalle multiplie par ef", () => {
  const first = getStatus([{ date: "2026-10-01", score: 100 }], NOW);
  const second = getStatus([
    { date: "2026-10-01", score: 100 },
    { date: "2026-10-02", score: 100 },
  ], NOW);
  const third = getStatus([
    { date: "2026-10-01", score: 100 },
    { date: "2026-10-02", score: 100 },
    { date: "2026-10-05", score: 100 },
  ], NOW);
  assert.equal(first.interval, 1);
  assert.equal(second.interval, 3);
  assert.equal(third.interval, 8);
});

test("la retention est de 90 pour cent a la date prevue", () => {
  const status = getStatus([{ date: "2026-10-01", score: 100 }], new Date("2026-10-02T10:00:00"));
  assert.equal(status.retention, 0.9);
});

test("un historique vide reste au statut initial", () => {
  const status = getStatus([], NOW);
  assert.equal(status.reps, 0);
  assert.equal(status.nextDate, null);
  assert.equal(status.retention, null);
});

test("la courbe remonte apres un quiz puis redescend chaque jour", () => {
  const timeline = getRetentionTimeline([
    { date: "2026-10-01", score: 60 },
    { date: "2026-10-03", score: 90 },
  ], new Date("2026-10-03T12:00:00"), 1);
  assert.equal(timeline[0].value, 60);
  assert.ok(timeline[1].value < 60);
  assert.equal(timeline[2].value, 90);
  assert.ok(timeline[3].value < 90);
});
