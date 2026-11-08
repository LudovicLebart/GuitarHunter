/** Instantané du seul état qu'une demande de ré-analyse modifie de façon optimiste : le statut et le verdict. `null` si
 *  l'annonce n'est pas dans cette table. */
export const snapshotReanalysisState = (entry) => (entry
  ? { status: entry.status, hadAnalysis: entry.aiAnalysis != null, verdict: entry.aiAnalysis?.verdict }
  : null);

/** Remet le statut et le verdict d'avant, sans toucher au reste de l'entrée (mis à jour entre-temps par le temps réel).
 *  Une entrée qui n'avait pas d'`aiAnalysis` n'en reçoit pas. */
export const restoreReanalysisState = (entry, snapshot) => {
  const restored = { ...entry, status: snapshot.status };
  if (snapshot.hadAnalysis) restored.aiAnalysis = { ...entry.aiAnalysis, verdict: snapshot.verdict };
  else if (entry.aiAnalysis) {
    const { verdict: _verdict, ...rest } = entry.aiAnalysis;
    restored.aiAnalysis = rest;
  }
  return restored;
};
