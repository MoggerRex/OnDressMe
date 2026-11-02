import React, { useState } from 'react';
import MannequinCanvas from './features/mannequin/MannequinScene';
import { User, Shirt, Sparkles, Smile, Frown, Sliders } from 'lucide-react';

export default function App() {
  const [isHappy, setIsHappy] = useState(true);
  
  // Estado para las medidas del cuerpo (sliders paramétricos estilo Body Visualizer)
  const [bodyScale, setBodyScale] = useState({
    width: 1.0,  // Simula complexión / grosor
    height: 1.0, // Simula altura
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur sticky top-0 z-50 px-6 py-4 flex justify-between items-center">
        <h1 className="text-xl font-bold bg-gradient-to-r from-pink-500 to-violet-500 bg-clip-text text-transparent">
          OnDressMe ✨
        </h1>
        <div className="flex gap-4 text-sm text-slate-400">
          <span className="hover:text-white cursor-pointer">Clóset</span>
          <span className="hover:text-white cursor-pointer">Maniquí</span>
          <span className="hover:text-white cursor-pointer">Perfil</span>
        </div>
      </header>

      {/* Main Content Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        
        {/* COLUMNA 1: Perfil y Controles Corporales (Body Visualizer Style) */}
        <section className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 flex flex-col gap-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <User className="text-pink-500" size={22} />
            <h2 className="font-semibold text-lg">Perfil & Medidas</h2>
          </div>
          
          <div className="text-sm text-slate-300 space-y-2">
            <p><strong>Subtono:</strong> Cálido (Invierno)</p>
            <p><strong>Colorimetría:</strong> Armonía Alta</p>
          </div>

          {/* Sliders de Proporciones Corporales */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-pink-400 mb-2">
              <Sliders size={14} /> Ajuste Paramétrico del Cuerpo
            </div>
            
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Complexión / Grosor</span>
                <span>{bodyScale.width.toFixed(2)}x</span>
              </div>
              <input 
                type="range" 
                min="0.8" 
                max="1.3" 
                step="0.05"
                value={bodyScale.width}
                onChange={(e) => setBodyScale({ ...bodyScale, width: parseFloat(e.target.value) })}
                className="w-full accent-pink-500 cursor-pointer"
              />
            </div>

            <div className="space-y-1">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Estatura / Altura</span>
                <span>{bodyScale.height.toFixed(2)}x</span>
              </div>
              <input 
                type="range" 
                min="0.9" 
                max="1.2" 
                step="0.05"
                value={bodyScale.height}
                onChange={(e) => setBodyScale({ ...bodyScale, height: parseFloat(e.target.value) })}
                className="w-full accent-violet-500 cursor-pointer"
              />
            </div>
          </div>
        </section>

        {/* COLUMNA 2: Visor Central 3D (Maniquí) */}
        <section className="flex flex-col gap-4">
          <div className="flex justify-between items-center bg-slate-900/60 border border-slate-800 px-4 py-3 rounded-xl">
            <span className="text-sm font-medium flex items-center gap-2">
              <Sparkles size={16} className="text-yellow-400" /> Simulador de Outfit
            </span>
            <div className="flex gap-2">
              <button 
                onClick={() => setIsHappy(true)}
                className={`px-3 py-1 text-xs rounded-lg flex items-center gap-1 transition ${isHappy ? 'bg-pink-600 text-white' : 'bg-slate-800 text-slate-400'}`}
              >
                <Smile size={14} /> ¡Funciona!
              </button>
              <button 
                onClick={() => setIsHappy(false)}
                className={`px-3 py-1 text-xs rounded-lg flex items-center gap-1 transition ${!isHappy ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400'}`}
              >
                <Frown size={14} /> No combina
              </button>
            </div>
          </div>

          {/* El Maniquí 3D con estado corporal conectado */}
          <MannequinCanvas isHappy={isHappy} bodyScale={bodyScale} />
        </section>

        {/* COLUMNA 3: Clóset Digital */}
        <section className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 flex flex-col gap-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <Shirt className="text-violet-500" size={22} />
            <h2 className="font-semibold text-lg">Mi Clóset</h2>
          </div>
          <p className="text-xs text-slate-400">Arrastra una prenda hacia el maniquí:</p>
          
          <div className="grid grid-cols-2 gap-3">
            <div className="h-24 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-center text-xs text-slate-500 cursor-grab hover:border-pink-500 transition">
              Camisa Rosa
            </div>
            <div className="h-24 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-center text-xs text-slate-500 cursor-grab hover:border-pink-500 transition">
              Pantalón Oscuro
            </div>
          </div>
        </section>

      </main>
    </div>
  );
}