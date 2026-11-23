import test from 'node:test';
import assert from 'node:assert/strict';
import { snapshotReanalysisState, restoreReanalysisState } from './reanalysisState.js';

test('le retour arrière ne restaure que le statut et le verdict', () => {
  const before = snapshotReanalysisState({ status: 'analyzed', price: 100, aiAnalysis: { verdict: 'PEPITE', deal_score: 8 } });
  // pendant la requête : le temps réel change le prix, la commande optimiste efface le verdict
  const during = { status: 'analyzing', price: 90, aiAnalysis: { verdict: undefined, deal_score: 8 } };
  const out = restoreReanalysisState(during, before);
  assert.equal(out.status, 'analyzed');
  assert.equal(out.aiAnalysis.verdict, 'PEPITE');
  assert.equal(out.price, 90);
  assert.equal(out.aiAnalysis.deal_score, 8);
});

test("une entrée sans analyse n'en reçoit pas", () => {
  const before = snapshotReanalysisState({ status: 'pending' });
  const out = restoreReanalysisState({ status: 'analyzing' }, before);
  assert.equal('aiAnalysis' in out, false);
});

test('un instantané est null pour une annonce absente', () => {
  assert.equal(snapshotReanalysisState(undefined), null);
});
