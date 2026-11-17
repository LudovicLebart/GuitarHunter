import React, { Suspense } from 'react';

// Suspense + garde-fou pour les vues chargées à la demande : si le fichier du bloc est introuvable
// (nouveau déploiement pendant que l'onglet était ouvert, connexion coupée), on affiche un message
// avec un bouton de nouvel essai au lieu de démonter toute l'application.
class ChunkErrorBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { console.error('Échec de chargement d\'une vue :', error); }
  render() {
    if (!this.state.failed) return this.props.children;
    if (this.props.hidden) return null;   // vue déjà montée puis fermée : rien à afficher
    return (
      <div className={this.props.overlay ? 'fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80' : 'py-20 flex justify-center'}>
        <div className="bg-slate-900 border border-slate-800 rounded-2xl px-6 py-5 text-center max-w-xs">
          <p className="text-slate-300 text-sm font-bold mb-1">Impossible de charger cette vue.</p>
          <p className="text-slate-500 text-xs mb-4">Une nouvelle version est peut-être disponible, ou la connexion est coupée.</p>
          <div className="flex gap-2 justify-center">
            <button onClick={() => window.location.reload()} className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold">Recharger la page</button>
            {this.props.onClose && <button onClick={this.props.onClose} className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs font-bold">Fermer</button>}
          </div>
        </div>
      </div>
    );
  }
}

const InlineFallback = () => <div className="py-20 text-center text-slate-500 text-xs font-bold uppercase tracking-widest">Chargement…</div>;
const OverlayFallback = () => (
  <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/60 text-slate-300 text-xs font-bold uppercase tracking-widest">Chargement…</div>
);

// `overlay` : fenêtre par-dessus la page (retour visuel plein écran pendant le téléchargement).
const LazyBoundary = ({ overlay = false, hidden = false, onClose, children }) => (
  <ChunkErrorBoundary overlay={overlay} hidden={hidden} onClose={onClose}>
    <Suspense fallback={hidden ? null : overlay ? <OverlayFallback /> : <InlineFallback />}>{children}</Suspense>
  </ChunkErrorBoundary>
);

export default LazyBoundary;
