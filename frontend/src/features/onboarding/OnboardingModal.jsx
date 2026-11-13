import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, ArrowRight, Camera, CheckCircle2, RefreshCw, Sparkles, User } from 'lucide-react';
import { API_BASE_URL } from '../../services/api';

export default function OnboardingModal({ isOpen, onComplete, initialProfile }) {
	const [step, setStep] = useState(1);
	const [profileName, setProfileName] = useState(initialProfile?.name || 'Eva García');
	const [faceFile, setFaceFile] = useState(null);
	const [facePreview, setFacePreview] = useState(null);
	const [bodyFile, setBodyFile] = useState(null);
	const [bodyPreview, setBodyPreview] = useState(null);
	const [analyzing, setAnalyzing] = useState(false);
	const [colorimetryResult, setColorimetryResult] = useState(null);
	const [errorMsg, setErrorMsg] = useState(null);

	useEffect(() => () => {
		if (facePreview) URL.revokeObjectURL(facePreview);
		if (bodyPreview) URL.revokeObjectURL(bodyPreview);
	}, [facePreview, bodyPreview]);

	useEffect(() => {
		if (!isOpen) return undefined;
		const previousOverflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		return () => {
			document.body.style.overflow = previousOverflow;
		};
	}, [isOpen]);

	if (!isOpen) return null;

	async function handleFaceUpload(event) {
		const file = event.target.files?.[0];
		if (!file) return;

		setFaceFile(file);
		setFacePreview(URL.createObjectURL(file));
		setColorimetryResult(null);
		setErrorMsg(null);
		setAnalyzing(true);

		const formData = new FormData();
		formData.append('image', file);
		const profileId = `user_${Date.now()}`;

		try {
			const response = await fetch(`${API_BASE_URL}/api/colorimetry?profile_id=${profileId}`, {
				method: 'POST',
				body: formData,
			});
			const data = await response.json();
			if (!response.ok) throw new Error(data.detail || 'Error al analizar la imagen.');

			setColorimetryResult(data.result);
			try {
				window.localStorage.setItem(`colorimetry_${profileId}`, JSON.stringify(data.result));
			} catch {
				// The result remains available for this onboarding session.
			}
		} catch (error) {
			setErrorMsg(error.message || 'No se pudo conectar con el servidor de colorimetría.');
		} finally {
			setAnalyzing(false);
		}
	}

	function handleBodyUpload(event) {
		const file = event.target.files?.[0];
		if (!file) return;
		setBodyFile(file);
		setBodyPreview(URL.createObjectURL(file));
	}

	function handleFinish() {
		onComplete({
			name: profileName.trim(),
			style: colorimetryResult
				? `${colorimetryResult.season} (${colorimetryResult.undertone})`
				: initialProfile?.style || 'Estilo Personalizado',
			photoName: faceFile?.name || initialProfile?.photoName || 'Sin foto',
			bodyPhoto: bodyFile?.name || initialProfile?.bodyPhoto || null,
		});
	}

	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
			<motion.div
				initial={{ opacity: 0, scale: 0.96, y: 16 }}
				animate={{ opacity: 1, scale: 1, y: 0 }}
				className="flex max-h-[calc(100dvh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-[#3c3c44] bg-[#1c1c20] shadow-2xl"
				role="dialog"
				aria-modal="true"
				aria-labelledby="onboarding-title"
			>
				<header className="flex items-center justify-between border-b border-[#35353d] bg-[#26262b] px-5 py-4 sm:px-6">
					<div className="flex items-center gap-3">
						<span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#863bff]/20 text-[#a9c8e4]">
							<Sparkles size={17} aria-hidden="true" />
						</span>
						<div>
							<span className="text-[10px] font-semibold uppercase tracking-widest text-[#a9c8e4]">Onboarding de estilo</span>
							<h2 id="onboarding-title" className="text-sm font-medium text-white">Personaliza tu experiencia</h2>
						</div>
					</div>
					<span className="text-xs text-[#b8b7bf]">{step} de 2</span>
				</header>

				<div className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-8">
					<AnimatePresence mode="wait">
						{step === 1 ? (
							<motion.section key="colorimetry" initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 16 }} className="space-y-5" aria-labelledby="colorimetry-title">
								<div>
									<p className="text-xs font-semibold uppercase tracking-wider text-[#a7c7e5]">Paso 1 · Colorimetría</p>
									<h3 id="colorimetry-title" className="mt-1 font-['Carrois_Gothic'] text-2xl text-white">Encuentra los tonos que te favorecen</h3>
									<p className="mt-2 text-sm leading-relaxed text-[#b8b7bf]">Añade una foto de rostro para recibir un análisis de color. También puedes continuar sin foto.</p>
								</div>

								<div className="space-y-2 rounded-lg border border-[#393942] bg-[#242429] p-4">
									<strong className="flex items-center gap-2 text-xs uppercase tracking-wider text-white"><Camera size={15} className="text-[#a7c7e5]" /> Consejos para la foto</strong>
									<ul className="list-inside list-disc space-y-1 text-xs text-[#b8b7bf]">
										<li>Usa luz natural y mira de frente.</li>
										<li>Retira gafas, gorros y accesorios que den sombra.</li>
										<li>Evita filtros y maquillaje intenso.</li>
									</ul>
								</div>

								<div>
									<label className="block text-xs font-medium text-[#d0cfd6]" htmlFor="onboarding-name">Tu nombre o apodo</label>
									<input id="onboarding-name" type="text" value={profileName} onChange={(event) => setProfileName(event.target.value)} className="mt-2 w-full rounded-lg border border-[#3c3c46] bg-[#151518] px-4 py-3 text-sm text-white outline-none focus:border-[#a7c7e5]" />
								</div>

								<label className="flex min-h-36 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[#454550] bg-[#17171b] p-5 text-center transition-colors hover:border-[#a7c7e5]">
									<input type="file" accept="image/*" onChange={handleFaceUpload} className="sr-only" />
									{facePreview ? (
										<>
											<img src={facePreview} alt="Vista previa de tu rostro" className="h-20 w-20 rounded-full border-2 border-[#a7c7e5] object-cover" />
											<span className="flex items-center gap-1 text-xs font-medium text-emerald-400"><CheckCircle2 size={14} /> {faceFile?.name}</span>
										</>
									) : (
										<>
											<span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#26262c] text-[#a7c7e5]"><Camera size={21} /></span>
											<strong className="text-sm text-white">Selecciona una foto de tu rostro</strong>
											<span className="text-xs text-[#8e8d96]">JPG o PNG · opcional</span>
										</>
									)}
								</label>

								{analyzing && <p className="flex items-center justify-center gap-2 rounded-lg border border-[#383842] bg-[#22222a] py-3 text-xs text-[#a7c7e5]" role="status"><RefreshCw className="animate-spin" size={15} /> Analizando tu paleta...</p>}
								{errorMsg && <p className="flex items-start gap-2 rounded-lg border border-rose-800/60 bg-rose-950/40 p-3 text-xs text-rose-300" role="alert"><AlertCircle size={15} className="shrink-0" /> {errorMsg}</p>}

								{colorimetryResult && (
									<div className="space-y-2 rounded-lg border border-[#424250] bg-[#23232a] p-4" aria-live="polite">
										<div className="flex flex-wrap items-center justify-between gap-2">
											<strong className="text-xs uppercase tracking-wider text-[#a9c8e4]">Análisis completado</strong>
											<span className="rounded-full bg-[#863bff]/20 px-2.5 py-1 text-xs font-semibold text-[#d8c4ff]">{colorimetryResult.season}</span>
										</div>
										<p className="text-xs leading-relaxed text-[#d1d0d8]">{colorimetryResult.description}</p>
										<p className="text-xs text-[#9b99a4]">Subtono: {colorimetryResult.undertone} · Contraste: {colorimetryResult.contrast}</p>
									</div>
								)}
							</motion.section>
						) : (
							<motion.section key="silhouette" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} className="space-y-5" aria-labelledby="silhouette-title">
								<div>
									<p className="text-xs font-semibold uppercase tracking-wider text-[#a7c7e5]">Paso 2 · Silueta</p>
									<h3 id="silhouette-title" className="mt-1 font-['Carrois_Gothic'] text-2xl text-white">Prepara tu avatar</h3>
									<p className="mt-2 text-sm leading-relaxed text-[#b8b7bf]">La foto es opcional y no se sube; solo guardaremos el nombre del archivo en tu perfil.</p>
								</div>

								<label className="flex min-h-48 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[#454550] bg-[#17171b] p-6 text-center transition-colors hover:border-[#a7c7e5]">
									<input type="file" accept="image/*" onChange={handleBodyUpload} className="sr-only" />
									{bodyPreview ? (
										<>
											<img src={bodyPreview} alt="Vista previa de cuerpo completo" className="h-36 rounded-lg border border-[#a7c7e5] object-cover" />
											<span className="flex items-center gap-1 text-xs font-medium text-emerald-400"><CheckCircle2 size={14} /> {bodyFile?.name}</span>
										</>
									) : (
										<>
											<span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#26262c] text-[#a7c7e5]"><User size={21} /></span>
											<strong className="text-sm text-white">Añade una foto de cuerpo completo</strong>
											<span className="text-xs text-[#8e8d96]">Opcional · permanece en este dispositivo mientras completas el perfil</span>
										</>
									)}
								</label>

								<div className="flex items-start gap-3 rounded-lg border border-[#383842] bg-[#222228] p-4 text-sm text-[#b8b7bf]"><Sparkles size={17} className="mt-0.5 shrink-0 text-[#a7c7e5]" /><p>Tu perfil estará listo para explorar el clóset virtual, combinar prendas y probar recomendaciones de color.</p></div>
							</motion.section>
						)}
					</AnimatePresence>
				</div>

				<footer className="flex items-center justify-between gap-3 border-t border-[#35353d] bg-[#222227] px-5 py-4 sm:px-6">
					{step === 2 ? (
						<button type="button" onClick={() => setStep(1)} className="px-3 py-2 text-xs font-semibold text-[#d0cfd6] transition-colors hover:text-white">Atrás</button>
					) : (
						<button type="button" onClick={handleFinish} className="px-3 py-2 text-xs font-semibold text-[#d0cfd6] transition-colors hover:text-white">Omitir por ahora</button>
					)}
					{step === 1 ? (
						<button type="button" onClick={() => setStep(2)} disabled={analyzing || !profileName.trim()} className="flex items-center gap-2 rounded-lg bg-[#a7c7e5] px-5 py-2.5 text-xs font-bold text-[#151518] shadow-lg transition-colors hover:bg-[#bce0ff] disabled:cursor-not-allowed disabled:opacity-50">Continuar <ArrowRight size={14} /></button>
					) : (
						<button type="button" onClick={handleFinish} className="flex items-center gap-2 rounded-lg bg-[#863bff] px-5 py-2.5 text-xs font-bold text-white shadow-lg transition-opacity hover:opacity-90">Comenzar a explorar <Sparkles size={14} /></button>
					)}
				</footer>
			</motion.div>
		</div>
	);
}