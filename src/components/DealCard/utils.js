import { Gem, Sparkles, Hammer, Briefcase, Package, AlertTriangle, Ban, RefreshCw } from 'lucide-react';

export const VERDICT_CONFIG = {
    PEPITE: { label: 'Pépite', bg: 'bg-yellow-500', text: 'text-yellow-900', icon: Gem },
    FAST_FLIP: { label: 'Fast Flip', bg: 'bg-emerald-500', text: 'text-emerald-900', icon: Sparkles },
    LUTHIER_PROJ: { label: 'Projet Luthier', bg: 'bg-orange-500', text: 'text-orange-900', icon: Hammer },
    CASE_WIN: { label: 'Case Win', bg: 'bg-sky-500', text: 'text-sky-900', icon: Briefcase },
    COLLECTION: { label: 'Collection', bg: 'bg-blue-500', text: 'text-blue-900', icon: Package },
    BAD_DEAL: { label: 'Trop Cher', bg: 'bg-rose-500', text: 'text-rose-900', icon: AlertTriangle },
    REJECTED_ITEM: { label: 'Rejeté', bg: 'bg-slate-600', text: 'text-slate-200', icon: Ban },
    REJECTED_SERVICE: { label: 'Service', bg: 'bg-slate-600', text: 'text-slate-200', icon: Ban },
    ERROR: { label: 'Erreur', bg: 'bg-red-900', text: 'text-red-200', icon: AlertTriangle },
    DEFAULT: { label: 'Analyse...', bg: 'bg-slate-700', text: 'text-slate-200', icon: RefreshCw },
};

export const toTitleCase = (str = '') =>
    str.toLowerCase().split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

// Format a Firestore timestamp or ISO string to a relative human string
export const formatRelativeDate = (timestamp) => {
    if (!timestamp) return null;
    try {
        const date = timestamp?.toDate ? timestamp.toDate() : new Date(timestamp);
        const diff = Math.floor((Date.now() - date.getTime()) / 1000);
        if (diff < 60) return 'À l\'instant';
        if (diff < 3600) return `Il y a ${Math.floor(diff / 60)} min`;
        if (diff < 86400) return `Il y a ${Math.floor(diff / 3600)}h`;
        return `Il y a ${Math.floor(diff / 86400)}j`;
    } catch {
        return null;
    }
};
