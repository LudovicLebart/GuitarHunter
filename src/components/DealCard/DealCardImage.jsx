import React from 'react';
import { Ban, Gem } from 'lucide-react';
import ImageGallery from '../ImageGallery';

const DealCardImage = ({ 
    images, 
    title, 
    isSold, 
    vc, 
    isAnalyzing, 
    alsoPepite, 
    interestScore, 
    price, 
    priceDrop 
}) => {
    const VIcon = vc.icon;
    
    return (
        <div className="relative w-full h-[280px] bg-slate-950 overflow-hidden flex items-center justify-center shrink-0">
            <div className="h-full w-full">
                <ImageGallery images={images.length > 0 ? images : ['']} title={title} />
            </div>

            {/* Verdict Badge */}
            <div className="absolute top-3 left-3 flex flex-col items-start gap-1 z-10">
                {isSold && (
                    <div className="bg-slate-950 border border-slate-500 text-slate-200 px-2.5 py-1 rounded-full text-[11px] font-black tracking-wider flex items-center gap-1.5 shadow-lg">
                        <Ban size={12} />
                        Vendu
                    </div>
                )}
                <div className={`${vc.bg} px-2.5 py-1 rounded-full text-[11px] font-black tracking-wider flex items-center gap-1.5 shadow-lg ${vc.text}`}>
                    <VIcon size={12} className={isAnalyzing ? 'animate-spin' : ''} />
                    {isAnalyzing ? 'Analyse...' : vc.label}
                </div>
                {alsoPepite && (
                    <div className="bg-yellow-500 text-yellow-900 px-2 py-0.5 rounded-full text-[10px] font-black tracking-wider flex items-center gap-1 shadow-lg">
                        <Gem size={10} />
                        Aussi Pépite
                    </div>
                )}
                {interestScore != null && (
                    <div className="bg-slate-950/90 backdrop-blur-sm border border-slate-700 text-white px-2 py-0.5 rounded-full text-[10px] font-black tracking-wider shadow-lg">
                        Note {interestScore.toFixed(1)}/10
                    </div>
                )}
            </div>
            {/* Price Badge */}
            {price != null && (
                <div className="absolute top-3 right-3 flex flex-col items-end gap-1 z-10 pointer-events-none">
                    <div className="bg-slate-950/90 backdrop-blur-sm border border-slate-700 text-white px-3 py-1.5 rounded-xl text-base font-black shadow-lg">
                        {price}$
                    </div>
                    {priceDrop > 0 && (
                        <div className="bg-emerald-500/90 backdrop-blur-sm border border-emerald-400 text-emerald-950 px-2.5 py-1 rounded-lg text-xs font-black shadow-lg">
                            Baisse -{priceDrop}$
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default DealCardImage;
