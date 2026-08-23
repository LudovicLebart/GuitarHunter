import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Guitar, Maximize2, ChevronLeft, ChevronRight, X } from 'lucide-react';

// Distance minimale (px) pour qu'un geste tactile horizontal soit interprété comme un swipe
// plutôt qu'un tap — évite de naviguer par erreur sur un simple appui.
const SWIPE_THRESHOLD = 50;

// Visionneuse plein écran (2026-08-22, extraite d'ImageGallery pour être réutilisée ailleurs —
// ex. photos d'une étape du plan de restauration — avec exactement le même comportement :
// navigation précédent/suivant, fermeture au clic sur le fond ou sur la croix, touches clavier
// (Échap/flèches), swipe tactile (2026-08-22), indicateurs. Contrôlée par le parent
// (`currentIndex`/`onNext`/`onPrev`/`onClose`) plutôt que de gérer son propre index, pour
// qu'ImageGallery continue de partager le même état entre vignette et plein écran exactement
// comme avant cette extraction.
export const ImageLightbox = ({ images, currentIndex, title, onNext, onPrev, onClose }) => {
    const touchStartXRef = useRef(null);

    useEffect(() => {
        document.body.style.overflow = 'hidden';
        return () => { document.body.style.overflow = 'unset'; };
    }, []);

    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') onClose();
            if (e.key === 'ArrowRight') onNext(e);
            if (e.key === 'ArrowLeft') onPrev(e);
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onNext, onPrev, onClose]);

    // Swipe horizontal (mobile) — un seul doigt, mesuré entre le début et la fin du toucher plutôt
    // qu'en continu, pour rester simple (pas de suivi visuel du doigt pendant le glissement).
    const handleTouchStart = (e) => {
        touchStartXRef.current = e.touches[0]?.clientX ?? null;
    };
    const handleTouchEnd = (e) => {
        const startX = touchStartXRef.current;
        touchStartXRef.current = null;
        if (startX == null || images.length <= 1) return;
        const deltaX = (e.changedTouches[0]?.clientX ?? startX) - startX;
        if (Math.abs(deltaX) < SWIPE_THRESHOLD) return;
        if (deltaX < 0) onNext(); else onPrev();
    };

    return createPortal(
        <div
            className="fixed inset-0 z-[9999] bg-black/95 flex items-center justify-center animate-in fade-in duration-200"
            onClick={onClose}
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEnd}
        >
            <div className="relative w-full h-full flex items-center justify-center p-4" onClick={(e) => e.stopPropagation()}>
                <img
                    src={images[currentIndex]}
                    className="max-w-full max-h-full object-contain shadow-2xl"
                    alt={`${title || 'Photo'} - Plein écran`}
                />

                {images.length > 1 && (
                    <>
                        <button
                            onClick={onPrev}
                            className="absolute left-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
                        >
                            <ChevronLeft size={48} />
                        </button>
                        <button
                            onClick={onNext}
                            className="absolute right-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
                        >
                            <ChevronRight size={48} />
                        </button>
                        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex gap-2">
                            {images.map((_, idx) => (
                                <div
                                    key={idx}
                                    className={`w-2 h-2 rounded-full transition-all ${idx === currentIndex ? 'bg-white scale-125' : 'bg-white/30'}`}
                                />
                            ))}
                        </div>
                    </>
                )}
            </div>

            <button
                onClick={(e) => {
                    e.stopPropagation();
                    onClose();
                }}
                className="absolute top-4 right-4 z-50 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
            >
                <X size={32} />
            </button>
        </div>,
        document.body
    );
};

const ImageGallery = ({ images, title }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFullScreen, setIsFullScreen] = useState(false);

  if (!images || images.length === 0) {
    return (
      <div className="w-full h-full bg-slate-100 flex items-center justify-center text-slate-400">
        <Guitar size={48} className="opacity-20" />
      </div>
    );
  }

  const nextImage = (e) => {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    setCurrentIndex((prev) => (prev + 1) % images.length);
  };

  const prevImage = (e) => {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    setCurrentIndex((prev) => (prev - 1 + images.length) % images.length);
  };

  const toggleFullScreen = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsFullScreen(!isFullScreen);
  };

  return (
    <>
      {/* Mode Normal */}
      <div className="relative w-full h-full group cursor-pointer" onClick={toggleFullScreen}>
        <img
          src={images[currentIndex]}
          className="w-full h-full object-contain transition-transform duration-700"
          alt={`${title} - ${currentIndex + 1}`}
        />

        {/* Bouton Expand au survol */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/50 text-white p-1.5 rounded-lg">
            <Maximize2 size={16} />
        </div>

        {images.length > 1 && (
          <>
            <button
              onClick={prevImage}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <ChevronLeft size={20} />
            </button>
            <button
              onClick={nextImage}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <ChevronRight size={20} />
            </button>
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
              {images.map((_, idx) => (
                <div
                  key={idx}
                  className={`w-1.5 h-1.5 rounded-full ${idx === currentIndex ? 'bg-white' : 'bg-white/50'}`}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Mode Plein Écran */}
      {isFullScreen && (
        <ImageLightbox
          images={images}
          currentIndex={currentIndex}
          title={title}
          onNext={nextImage}
          onPrev={prevImage}
          onClose={() => setIsFullScreen(false)}
        />
      )}
    </>
  );
};

export default ImageGallery;
