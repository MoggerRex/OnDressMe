import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, ArrowDown, ArrowRight, Check, CheckCircle2, Camera, ImagePlus, RefreshCw, Sparkles, X } from 'lucide-react';
import { API_BASE_URL } from '../../services/api';
import ClosetWorldScene from './ClosetWorldScene.jsx';
import './onboarding.css';

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
	const dialogRef = useRef(null);
	const scrollRef = useRef(null);
	const pointerRef = useRef({ x: 0, y: 0 });
	const journeyProgressRef = useRef(0);
	const [scrollProgress, setScrollProgress] = useState(0);
	const [profileName, setProfileName] = useState(initialProfile?.name || 'Eva Garcia');
	const [profileEmail, setProfileEmail] = useState(initialProfile?.email || '');
	const [emailTouched, setEmailTouched] = useState(false);
	const [faceFile, setFaceFile] = useState(null);
	const [facePreview, setFacePreview] = useState(null);
	const [bodyFile, setBodyFile] = useState(null);
	const [bodyPreview, setBodyPreview] = useState(null);
	const [clothingFile, setClothingFile] = useState(null);
	const [clothingPreview, setClothingPreview] = useState(null);
	const [analyzing, setAnalyzing] = useState(false);
	const [colorimetryResult, setColorimetryResult] = useState(null);
	const [errorMsg, setErrorMsg] = useState(null);

	useEffect(() => () => {
		if (facePreview) URL.revokeObjectURL(facePreview);
		if (bodyPreview) URL.revokeObjectURL(bodyPreview);
		if (clothingPreview) URL.revokeObjectURL(clothingPreview);
	}, [facePreview, bodyPreview, clothingPreview]);

	useEffect(() => {
		if (!isOpen) return undefined;
		const previousOverflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		return () => {
			document.body.style.overflow = previousOverflow;
		};
	}, [isOpen]);

	useEffect(() => {
		if (isOpen) dialogRef.current?.focus();
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

	function handleClothingUpload(event) {
		const file = event.target.files?.[0];
		if (!file) return;
		setClothingFile(file);
		setClothingPreview(URL.createObjectURL(file));
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
			email: profileEmail.trim(),
			style: colorimetryResult
				? `${colorimetryResult.season} (${colorimetryResult.undertone})`
				: initialProfile?.style || 'Personal style',
			photoName: faceFile?.name || initialProfile?.photoName || 'No photo',
			bodyPhoto: bodyFile?.name || initialProfile?.bodyPhoto || null,
			clothingPhoto: clothingFile?.name || initialProfile?.clothingPhoto || null,
		});
	}

	function handleScroll(event) {
		const element = event.currentTarget;
		const distance = element.scrollHeight - element.clientHeight;
		const progress = distance > 0 ? element.scrollTop / distance : 0;
		journeyProgressRef.current = progress;
		setScrollProgress(progress);
	}

	function scrollTo(id) {
		scrollRef.current?.querySelector(`#${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	function handlePointerMove(event) {
		const bounds = event.currentTarget.getBoundingClientRect();
		pointerRef.current = {
			x: ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
			y: ((event.clientY - bounds.top) / bounds.height) * 2 - 1,
		};
	}

	const emailIsValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profileEmail.trim());

	return (
		<div className="closet-onboarding fixed inset-0 z-[300] overflow-hidden" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="onboarding-title" onKeyDown={(event) => { if (event.key === 'Escape') handleFinish(); }} onPointerMove={handlePointerMove} tabIndex={-1}>
			<div className="onboarding-world-backdrop" aria-hidden="true">
				<ClosetWorldScene progress={journeyProgressRef} hasClothing={Boolean(clothingFile)} hasPortrait={Boolean(facePreview)} hasBodyPhoto={Boolean(bodyPreview)} pointer={pointerRef} />
			</div>
			<div className="onboarding-scroll h-full overflow-y-auto overscroll-contain" onScroll={handleScroll} ref={scrollRef}>
				<div className="onboarding-progress" aria-hidden="true"><span style={{ transform: `scaleX(${scrollProgress})` }} /></div>
				<header className="onboarding-header sticky top-0 z-20 flex h-[68px] items-center justify-between px-6 sm:px-10">
					<a className="onboarding-wordmark" href="#onboarding-start" onClick={(event) => { event.preventDefault(); scrollTo('onboarding-start'); }} aria-label="OnDressMe, beginning">ONDRESSME<span> / PERSONAL STYLE STUDIO</span></a>
					<button className="onboarding-skip inline-flex items-center gap-2 px-3 py-2 text-xs" type="button" onClick={handleFinish}>Skip and explore <X size={14} /></button>
				</header>

				<nav className="onboarding-chapter-nav" aria-label="Onboarding chapters">
					{[
						['onboarding-start', 'The closet'],
						['onboarding-mirror', 'Your colors'],
						['onboarding-fitting', 'Your fitting'],
						['onboarding-rail', 'Your wardrobe'],
						['onboarding-profile', 'Your details'],
					].map(([id, label], index) => (
						<button aria-label={`Go to ${label}`} aria-current={Math.min(4, Math.floor(scrollProgress * 5 + 0.25)) === index ? 'step' : undefined} key={id} onClick={() => scrollTo(id)} type="button"><span>{`0${index + 1}`}</span><i /></button>
					))}
				</nav>

				<main>
					<section className="onboarding-chapter onboarding-hero" id="onboarding-start" aria-labelledby="onboarding-title">
						<motion.div className="onboarding-hero-copy" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1, ease: [0.2, 0.7, 0.15, 1] }}>
							<p className="onboarding-kicker">YOUR WORLD, JUST AHEAD</p>
							<h1 id="onboarding-title">Come in.<br /><span>Make it yours.</span></h1>
							<p className="onboarding-intro">A little light. A favorite piece. A different way to see yourself.</p>
						</motion.div>
						<button className="onboarding-scroll-cue" onClick={() => scrollTo('onboarding-mirror')} type="button"><span>Step inside</span><ArrowDown size={15} /></button>
						<span className="onboarding-side-note onboarding-side-note-left" aria-hidden="true">A PERSONAL FITTING ROOM</span>
						<span className="onboarding-side-note onboarding-side-note-right" aria-hidden="true">EST. YOURSELF</span>
					</section>

					<section className="onboarding-chapter onboarding-mirror" id="onboarding-mirror" aria-labelledby="palette-title">
						<div className="onboarding-section-index"><span>01</span><i /> THE MIRROR</div>
						<div className="onboarding-chapter-grid mirror-grid">
							<motion.div className="onboarding-mirror-art" initial={{ opacity: 0, scale: 0.94 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true, amount: 0.25 }} transition={{ duration: 0.8 }}>
								<div className="onboarding-mirror-glass">{facePreview ? <img src={facePreview} alt="Portrait preview" /> : <div><Camera size={30} /><span>YOUR REFLECTION<br />IN NATURAL LIGHT</span></div>}</div>
								<span className="onboarding-mirror-light mirror-light-one" /><span className="onboarding-mirror-light mirror-light-two" />
								<div className="onboarding-mirror-caption">A NEW WAY TO SEE YOURSELF</div>
							</motion.div>
							<div className="onboarding-story-copy">
								<p className="onboarding-kicker">A LITTLE LIGHT CHANGES EVERYTHING</p>
								<h2 id="palette-title">Meet the colors<br />that <em>feel like you.</em></h2>
								<p className="onboarding-body-copy">A natural-light portrait can reveal the tones that bring your features forward. No pressure, just a new way to look at yourself.</p>
								<label className="onboarding-upload-button" htmlFor="onboarding-face-photo"><span className="onboarding-upload-icon"><Camera size={18} /></span><span><strong>{faceFile ? 'Choose another portrait' : 'Add a portrait'}</strong><small>Optional · JPG or PNG</small></span><ArrowRight size={16} /><input accept="image/*" className="sr-only" id="onboarding-face-photo" onChange={handleFaceUpload} type="file" /></label>
								{analyzing && <p className="onboarding-status" role="status"><RefreshCw className="animate-spin" size={15} /> Reading your palette...</p>}
								{errorMsg && <p className="onboarding-error" role="alert"><AlertCircle size={15} />{errorMsg}</p>}
								{colorimetryResult && <motion.div className="onboarding-reading" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} aria-live="polite"><span className="onboarding-reading-label"><CheckCircle2 size={14} /> YOUR COLOR READING</span><strong>{colorimetryResult.season}</strong><p>{colorimetryResult.description}</p><div>{colorimetryResult.undertone} undertone <i /> {colorimetryResult.contrast} contrast</div></motion.div>}
								<p className="onboarding-photo-advice">For the clearest reading: face a window, look toward the camera, and let your skin be in its natural light.</p>
							</div>
						</div>
						<button className="onboarding-next-cue" onClick={() => scrollTo('onboarding-fitting')} type="button">Continue into the fitting room <ArrowDown size={14} /></button>
					</section>

					<section className="onboarding-chapter onboarding-fitting" id="onboarding-fitting" aria-labelledby="fitting-title">
						<div className="onboarding-section-index"><span>02</span><i /> THE FITTING ROOM</div>
						<div className="onboarding-chapter-grid fitting-grid">
							<div className="onboarding-story-copy">
								<p className="onboarding-kicker">A SILHOUETTE, MADE PERSONAL</p>
								<h2 id="fitting-title">Your shape.<br /><em>Your way.</em></h2>
								<p className="onboarding-body-copy">Bring a full-body photo into the room. We will use it as a guide while your 3D mannequin waits for its first look.</p>
								<label className="onboarding-upload-button" htmlFor="onboarding-body-photo"><span className="onboarding-upload-icon"><ImagePlus size={18} /></span><span><strong>{bodyFile ? 'Choose another photo' : 'Add a full-body photo'}</strong><small>Optional · JPG or PNG</small></span><ArrowRight size={16} /><input accept="image/*" className="sr-only" id="onboarding-body-photo" onChange={handleBodyUpload} type="file" /></label>
								<p className="onboarding-photo-advice">Your photo stays in this preview. Only its filename is saved with your profile.</p>
							</div>
							<motion.div className="onboarding-fitting-display" initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.8 }}>
								<div className="onboarding-body-photo">{bodyPreview ? <img src={bodyPreview} alt="Full-body photo preview" /> : <div><ImagePlus size={23} /><span>YOUR PHOTO<br />IN THE FITTING ROOM</span></div>}</div>
								<span className="onboarding-fitting-label">YOUR 3D MANNEQUIN <i /> READY TO STYLE</span>
							</motion.div>
						</div>
						<button className="onboarding-next-cue" onClick={() => scrollTo('onboarding-rail')} type="button">Find your first piece <ArrowDown size={14} /></button>
					</section>

					<section className="onboarding-chapter onboarding-rail" id="onboarding-rail" aria-labelledby="closet-story-title">
						<div className="onboarding-section-index"><span>03</span><i /> THE WARDROBE</div>
						<div className="onboarding-chapter-grid rail-grid">
							<div className="onboarding-story-copy">
								<p className="onboarding-kicker">START WITH SOMETHING YOU LOVE</p>
								<h2 id="closet-story-title">Everyday pieces.<br /><em>New possibilities.</em></h2>
								<p className="onboarding-body-copy">Add a shirt from your closet. Watch it take its place on the rail, ready to meet the rest of your style.</p>
								<p className="onboarding-photo-advice">A clear photo of one item works best. The image is shown here as a local preview.</p>
								<label className="onboarding-upload-button" htmlFor="onboarding-clothing-photo"><span className="onboarding-upload-icon"><ImagePlus size={18} /></span><span><strong>{clothingFile ? 'Add another shirt' : 'Add a shirt'}</strong><small>Optional · a piece you reach for</small></span><ArrowRight size={16} /><input accept="image/*" className="sr-only" id="onboarding-clothing-photo" onChange={handleClothingUpload} type="file" /></label>
							</div>
							<motion.div className={clothingPreview ? 'onboarding-garment-frame has-garment' : 'onboarding-garment-frame'} initial={{ opacity: 0, x: 28 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.7 }}>
								{clothingPreview ? <><img src={clothingPreview} alt="Uploaded clothing item preview" /><span className="onboarding-added-tag"><CheckCircle2 size={13} /> ADDED TO YOUR RAIL</span></> : <div className="onboarding-garment-placeholder"><div className="onboarding-garment-hanger" /><Sparkles size={24} strokeWidth={1.2} /><span>YOUR FIRST PIECE<br />IS WAITING</span></div>}
								<span className="onboarding-frame-caption">A LITTLE OF YOUR WORLD</span>
							</motion.div>
						</div>
						<button className="onboarding-next-cue" onClick={() => scrollTo('onboarding-profile')} type="button">Make it yours <ArrowDown size={14} /></button>
					</section>

					<section className="onboarding-chapter onboarding-profile" id="onboarding-profile" aria-labelledby="identity-title">
						<div className="onboarding-section-index"><span>04</span><i /> THE FINAL DETAIL</div>
						<motion.div className="onboarding-profile-copy" initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.25 }} transition={{ duration: 0.7 }}>
							<p className="onboarding-kicker">A FEW WORDS, THEN YOU ARE IN</p>
							<h2 id="identity-title">What should<br />we call <em>you?</em></h2>
							<div className="onboarding-identity-fields">
								<label className="onboarding-name-field" htmlFor="onboarding-name"><span>Your name or nickname</span><input autoComplete="given-name" id="onboarding-name" maxLength={48} onChange={(event) => setProfileName(event.target.value)} placeholder="Your name" required type="text" value={profileName} /></label>
								<label className="onboarding-name-field" htmlFor="onboarding-email"><span>Your email</span><input aria-describedby="onboarding-email-feedback" aria-invalid={emailTouched && !emailIsValid} autoComplete="email" id="onboarding-email" onBlur={() => setEmailTouched(true)} onChange={(event) => setProfileEmail(event.target.value)} placeholder="you@example.com" required type="email" value={profileEmail} />{emailTouched && !emailIsValid && <small className="onboarding-email-error" id="onboarding-email-feedback" role="alert">Enter a valid email address to continue.</small>}</label>
							</div>
							<p className="onboarding-soft-note">Your fitting room is ready{profileName.trim() ? `, ${profileName.trim()}` : ''}. Your details are saved on this device.</p>
							<button className="onboarding-enter-button" disabled={!profileName.trim() || !emailIsValid} onClick={handleFinish} type="button">Enter your closet <ArrowRight size={17} /></button>
						</motion.div>
					</section>
				</main>

				<footer className="onboarding-footer"><span>ON DRESS ME <i /> YOUR STYLE, IN YOUR OWN WORDS</span><button disabled={!profileName.trim() || !emailIsValid} onClick={handleFinish} type="button">Enter the closet <ArrowRight size={14} /></button></footer>
			</div>
		</div>
	);
}