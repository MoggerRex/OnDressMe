import React, { useState } from 'react';
import MannequinCanvas from './features/mannequin/MannequinScene';
import { User, Shirt, Sparkles, Smile, Frown } from 'lucide-react';

export default function App() {
  // Estado temporal para probar la reacción del maniquí
  const [isHappy, setIsHappy] = useState(true);

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
        
        {/* COLUMNA 1: Perfil y Colorimetría */}
        <section className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 flex flex-col gap-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <User className="text-pink-500" size={22} />
            <h2 className="font-semibold text-lg">Perfil de Estilo</h2>
          </div>
          <div className="text-sm text-slate-300 space-y-2">
            <p><strong>Subtono:</strong> Cálido (Invierno)</p>
            <p><strong>Complexión:</strong> Atlética</p>
            <p><strong>Estilo favorito:</strong> Casual / Streetwear</p>
          </div>
          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-xs text-slate-400">
            💡 <em>Aquí irán los sliders de peso, altura y proporciones corporales estilo Body Visualizer.</em>
          </div>
        </section>

        {/* COLUMNA 2: Visor Central 3D (Maniquí) */}
        <section className="flex flex-col gap-4">
          <div className="flex justify-between items-center bg-slate-900/60 border border-slate-800 px-4 py-3 rounded-xl">
            <span className="text-sm font-medium flex items-center gap-2">
              <Sparkles size={16} className="text-yellow-400" /> Simulador de Outfit
            </span>
            {/* Botones de prueba temporal para los emotes */}
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

          {/* El Maniquí 3D */}
          <MannequinCanvas isHappy={isHappy} />
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