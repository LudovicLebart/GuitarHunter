// Format colonnaire de GET /deals/index?format=columnar (2026-11-04) : `{cols: [...], rows: [[...], ...]}`.
// Les noms de clés (~58 par ligne) ne sont plus répétés à chaque annonce. Cette fonction reconstruit EXACTEMENT
// les objets de l'ancien format, pour que `dealFromRow` et tout l'aval restent inchangés. Elle accepte aussi
// un tableau d'objets (ancien serveur / ancien format), laissé tel quel.
export function decodeIndexRows(payload) {
  if (Array.isArray(payload)) return payload;
  const cols = payload?.cols;
  const rows = payload?.rows;
  if (!Array.isArray(cols) || !Array.isArray(rows)) throw new Error('Réponse /deals/index illisible (format inattendu)');
  const n = cols.length;
  return rows.map((values) => {
    const obj = {};
    for (let i = 0; i < n; i++) obj[cols[i]] = values[i];
    return obj;
  });
}
