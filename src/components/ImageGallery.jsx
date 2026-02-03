import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Guitar, Maximize2, ChevronLeft, ChevronRight, X } from 'lucide-react';

const ImageGallery = ({ images, title }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFullScreen, setIsFullScreen] = useState(false);

  // Gestion du scroll body quand le plein écran est actif
  useEffect(() => {
    if (isFullScreen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isFullScreen]);

  // Gestion des touches clavier
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isFullScreen) return;
      if (e.key === 'Escape') setIsFullScreen(false);
      if (e.key === 'ArrowRight') nextImage(e);
      if (e.key === 'ArrowLeft') prevImage(e);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullScreen, currentIndex, images]);

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
      {isFullScreen && createPortal(
        <div className="fixed inset-0 z-[9999] bg-black/95 flex items-center justify-center animate-in fade-in duration-200" onClick={() => setIsFullScreen(false)}>
            <div className="relative w-full h-full flex items-center justify-center p-4" onClick={(e) => e.stopPropagation()}>
                <img
                    src={images[currentIndex]}
                    className="max-w-full max-h-full object-contain shadow-2xl"
                    alt={`${title} - Fullscreen`}
                />

                {images.length > 1 && (
                    <>
                        <button 
                            onClick={prevImage}
                            className="absolute left-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
                        >
                            <ChevronLeft size={48} />
                        </button>
                        <button 
                            onClick={nextImage}
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
                   setIsFullScreen(false);
                }}
                className="absolute top-4 right-4 z-50 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
            >
                <X size={32} />
            </button>
        </div>,
        document.body
      )}
    </>
  );
};

export default ImageGallery;
