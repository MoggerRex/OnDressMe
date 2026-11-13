import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, ArrowRight, Camera, CheckCircle2, RefreshCw, Sparkles, User } from 'lucide-react';
import { API_BASE_URL } from '../../services/api';

const colorimetryTranslations = {
	seasons: { Otoño: 'Autumn', Primavera: 'Spring', Invierno: 'Winter', Verano: 'Summer' },
	undertones: { Cálido: 'Warm', Frío: 'Cool' },
	contrasts: { Alto: 'High', 'Suave / Bajo': 'Soft / Low' },
	descriptions: {
		Otoño: 'Deep, warm tones suit you best. Try earthy colors like terracotta, olive green, mustard, and warm browns.',
		Primavera: 'Bright, warm tones suit you best. Try vibrant, light colors like peach, coral, apple green, and ivory.',
		Invierno: 'Cool tones with high contrast suit you best. Try vivid colors like black, pure white, cherry red, and royal blue.',
		Verano: 'Soft, cool tones suit you best. Try muted pastels, soft blue, dusty rose, and pearl gray.',
	},
};

function localizeColorimetryResult(result) {
	const season = colorimetryTranslations.seasons[result.season] || result.season;
	return {
		...result,
		season,
		undertone: colorimetryTranslations.undertones[result.undertone] || result.undertone,
		contrast: colorimetryTranslations.contrasts[result.contrast] || result.contrast,
		description: colorimetryTranslations.descriptions[result.season] || result.description,
	};
}

function localizeColorimetryError(message) {
	const translations = {
		'No se pudo decodificar la imagen.': 'The image could not be decoded.',
		'La foto está muy alejada. Acércate más a la cámara.': 'The photo is too far away. Move closer to the camera.',
	};
	if (translations[message]) return translations[message];
	if (message.startsWith('No se detectó un rostro claro')) {
		return 'No clear face was detected. Upload a well-lit close-up of your face without obstructions.';
	}
	if (message.startsWith('Error procesando la imagen para colorimetría:')) {
		return 'There was an error processing the image for color analysis.';
	}
	return message;
}

export default function OnboardingModal({ isOpen, onComplete, initialProfile }) {
	const [step, setStep] = useState(1);
	const [profileName, setProfileName] = useState(initialProfile?.name || 'Eva Garcia');
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
			if (!response.ok) throw new Error(localizeColorimetryError(data.detail || 'Unable to analyze the image.'));

			setColorimetryResult(localizeColorimetryResult(data.result));
			try {
				window.localStorage.setItem(`colorimetry_${profileId}`, JSON.stringify(data.result));
			} catch {
				// The result remains available for this onboarding session.
			}
		} catch (error) {
			setErrorMsg(error.message || 'Could not connect to the color analysis server.');
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
			photoName: faceFile?.name || initialProfile?.photoName || 'No photo',
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
							<span className="text-[10px] font-semibold uppercase tracking-widest text-[#a9c8e4]">Style setup</span>
							<h2 id="onboarding-title" className="text-sm font-medium text-white">Personalize your experience</h2>
						</div>
					</div>
					<span className="text-xs text-[#b8b7bf]">Step {step} of 2</span>
				</header>

				<div className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-8">
					<AnimatePresence mode="wait">
						{step === 1 ? (
							<motion.section key="colorimetry" initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 16 }} className="space-y-5" aria-labelledby="colorimetry-title">
								<div>
									<p className="text-xs font-semibold uppercase tracking-wider text-[#a7c7e5]">Step 1 · Color analysis</p>
									<h3 id="colorimetry-title" className="mt-1 font-['Carrois_Gothic'] text-2xl text-white">Find the colors that suit you</h3>
									<p className="mt-2 text-sm leading-relaxed text-[#b8b7bf]">Add a face photo to receive a color analysis. You can also continue without a photo.</p>
								</div>

								<div className="space-y-2 rounded-lg border border-[#393942] bg-[#242429] p-4">
									<strong className="flex items-center gap-2 text-xs uppercase tracking-wider text-white"><Camera size={15} className="text-[#a7c7e5]" /> Photo tips</strong>
									<ul className="list-inside list-disc space-y-1 text-xs text-[#b8b7bf]">
										<li>Use natural light and look straight ahead.</li>
										<li>Remove glasses, hats, and accessories that cast shadows.</li>
										<li>Avoid filters and heavy makeup.</li>
									</ul>
								</div>

								<div>
									<label className="block text-xs font-medium text-[#d0cfd6]" htmlFor="onboarding-name">Your name or nickname</label>
									<input id="onboarding-name" type="text" value={profileName} onChange={(event) => setProfileName(event.target.value)} className="mt-2 w-full rounded-lg border border-[#3c3c46] bg-[#151518] px-4 py-3 text-sm text-white outline-none focus:border-[#a7c7e5]" />
								</div>

								<label className="flex min-h-36 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[#454550] bg-[#17171b] p-5 text-center transition-colors hover:border-[#a7c7e5]">
									<input type="file" accept="image/*" onChange={handleFaceUpload} className="sr-only" />
									{facePreview ? (
										<>
											<img src={facePreview} alt="Face photo preview" className="h-20 w-20 rounded-full border-2 border-[#a7c7e5] object-cover" />
											<span className="flex items-center gap-1 text-xs font-medium text-emerald-400"><CheckCircle2 size={14} /> {faceFile?.name}</span>
										</>
									) : (
										<>
											<span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#26262c] text-[#a7c7e5]"><Camera size={21} /></span>
											<strong className="text-sm text-white">Choose a face photo</strong>
											<span className="text-xs text-[#8e8d96]">JPG or PNG · optional</span>
										</>
									)}
								</label>

								{analyzing && <p className="flex items-center justify-center gap-2 rounded-lg border border-[#383842] bg-[#22222a] py-3 text-xs text-[#a7c7e5]" role="status"><RefreshCw className="animate-spin" size={15} /> Analyzing your color palette...</p>}
								{errorMsg && <p className="flex items-start gap-2 rounded-lg border border-rose-800/60 bg-rose-950/40 p-3 text-xs text-rose-300" role="alert"><AlertCircle size={15} className="shrink-0" /> {errorMsg}</p>}

								{colorimetryResult && (
									<div className="space-y-2 rounded-lg border border-[#424250] bg-[#23232a] p-4" aria-live="polite">
										<div className="flex flex-wrap items-center justify-between gap-2">
											<strong className="text-xs uppercase tracking-wider text-[#a9c8e4]">Analysis complete</strong>
											<span className="rounded-full bg-[#863bff]/20 px-2.5 py-1 text-xs font-semibold text-[#d8c4ff]">{colorimetryResult.season}</span>
										</div>
										<p className="text-xs leading-relaxed text-[#d1d0d8]">{colorimetryResult.description}</p>
										<p className="text-xs text-[#9b99a4]">Undertone: {colorimetryResult.undertone} · Contrast: {colorimetryResult.contrast}</p>
									</div>
								)}
							</motion.section>
						) : (
							<motion.section key="silhouette" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} className="space-y-5" aria-labelledby="silhouette-title">
								<div>
									<p className="text-xs font-semibold uppercase tracking-wider text-[#a7c7e5]">Step 2 · Body shape</p>
									<h3 id="silhouette-title" className="mt-1 font-['Carrois_Gothic'] text-2xl text-white">Set up your avatar</h3>
									<p className="mt-2 text-sm leading-relaxed text-[#b8b7bf]">The photo is optional and is not uploaded; only its filename will be saved to your profile.</p>
								</div>

								<label className="flex min-h-48 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[#454550] bg-[#17171b] p-6 text-center transition-colors hover:border-[#a7c7e5]">
									<input type="file" accept="image/*" onChange={handleBodyUpload} className="sr-only" />
									{bodyPreview ? (
										<>
											<img src={bodyPreview} alt="Full-body photo preview" className="h-36 rounded-lg border border-[#a7c7e5] object-cover" />
											<span className="flex items-center gap-1 text-xs font-medium text-emerald-400"><CheckCircle2 size={14} /> {bodyFile?.name}</span>
										</>
									) : (
										<>
											<span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#26262c] text-[#a7c7e5]"><User size={21} /></span>
											<strong className="text-sm text-white">Add a full-body photo</strong>
											<span className="text-xs text-[#8e8d96]">Optional · stays on this device while you complete your profile</span>
										</>
									)}
								</label>

								<div className="flex items-start gap-3 rounded-lg border border-[#383842] bg-[#222228] p-4 text-sm text-[#b8b7bf]"><Sparkles size={17} className="mt-0.5 shrink-0 text-[#a7c7e5]" /><p>Your profile will be ready to explore the virtual closet, mix and match clothes, and try color recommendations.</p></div>
							</motion.section>
						)}
					</AnimatePresence>
				</div>

				<footer className="flex items-center justify-between gap-3 border-t border-[#35353d] bg-[#222227] px-5 py-4 sm:px-6">
					{step === 2 ? (
						<button type="button" onClick={() => setStep(1)} className="px-3 py-2 text-xs font-semibold text-[#d0cfd6] transition-colors hover:text-white">Back</button>
					) : (
						<button type="button" onClick={handleFinish} className="px-3 py-2 text-xs font-semibold text-[#d0cfd6] transition-colors hover:text-white">Skip for now</button>
					)}
					{step === 1 ? (
						<button type="button" onClick={() => setStep(2)} disabled={analyzing || !profileName.trim()} className="flex items-center gap-2 rounded-lg bg-[#a7c7e5] px-5 py-2.5 text-xs font-bold text-[#151518] shadow-lg transition-colors hover:bg-[#bce0ff] disabled:cursor-not-allowed disabled:opacity-50">Continue <ArrowRight size={14} /></button>
					) : (
						<button type="button" onClick={handleFinish} className="flex items-center gap-2 rounded-lg bg-[#863bff] px-5 py-2.5 text-xs font-bold text-white shadow-lg transition-opacity hover:opacity-90">Start exploring <Sparkles size={14} /></button>
					)}
				</footer>
			</motion.div>
		</div>
	);
}