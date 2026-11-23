export const SCAN_NUMBERS = ['max_ads', 'frequency', 'distance', 'min_price', 'max_price'];

/** Un champ numérique vidé (ou non numérique) reprend la dernière valeur connue du serveur (sinon il est retiré) au lieu
 *  d'être enregistré à 0. */
export const sanitizeScanNumbers = (cfg, known) => {
  const clean = { ...cfg };
  for (const key of SCAN_NUMBERS) {
    if (clean[key] === '' || clean[key] == null || !Number.isFinite(Number(clean[key]))) {
      if (known && key in known) clean[key] = known[key];
      else delete clean[key];
    }
  }
  return clean;
};

/** Fusionne une configuration poussée par le serveur sans écraser une saisie non enregistrée : une clé dont la valeur locale
 *  diffère de la dernière valeur connue du serveur (`known`) est conservée. */
export const mergeServerScanConfig = (local, incoming, known) => {
  const merged = { ...local };
  for (const [key, value] of Object.entries(incoming)) {
    if (!known || !(key in known) || local[key] === known[key]) merged[key] = value;
  }
  return merged;
};
