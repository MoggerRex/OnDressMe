import { useEffect, useRef, useState } from 'react';
import {
	ArrowRight,
	Check,
	ChevronLeft,
	ChevronRight,
	Glasses,
	Info,
	Maximize2,
	Menu,
	Moon,
	Plus,
	Shirt,
	Sparkles,
	Sun,
	UserRound,
	X,
} from 'lucide-react';
import { PiBaseballCap, PiCoatHanger, PiPants, PiSneaker } from 'react-icons/pi';
import MannequinCanvas from '../features/mannequin/MannequinScene.jsx';
import '../App.css';

const categories = ['Camisas', 'Pantalones', 'Accesorios', 'Calzado', 'Gorras'];

const wardrobe = [
	{ id: 'sweater-blue', name: 'Suéter azul', category: 'Camisas', type: 'shirt', color: '#36546d', shade: 'Azul tinta' },
	{ id: 'wine-top', name: 'Top vino', category: 'Camisas', type: 'shirt', color: '#773d50', shade: 'Vino' },
	{ id: 'ice-shirt', name: 'Camisa hielo', category: 'Camisas', type: 'shirt', color: '#d8dce2', shade: 'Hielo' },
	{ id: 'onyx-shirt', name: 'Camisa ónix', category: 'Camisas', type: 'shirt', color: '#17181d', shade: 'Ónix' },
	{ id: 'pine-knit', name: 'Suéter pino', category: 'Camisas', type: 'shirt', color: '#315b58', shade: 'Pino' },
	{ id: 'silver-top', name: 'Top plata', category: 'Camisas', type: 'shirt', color: '#aeb6c4', shade: 'Plata' },
	{ id: 'sand-pants', name: 'Pantalón arena', category: 'Pantalones', type: 'pants', color: '#c4a374', shade: 'Arena' },
	{ id: 'charcoal-pants', name: 'Pantalón carbón', category: 'Pantalones', type: 'pants', color: '#34353a', shade: 'Carbón' },
	{ id: 'silver-watch', name: 'Reloj plata', category: 'Accesorios', type: 'accessory', color: '#b7bdc8', shade: 'Plata' },
	{ id: 'black-glasses', name: 'Gafas ónix', category: 'Accesorios', type: 'accessory', color: '#202126', shade: 'Ónix' },
	{ id: 'white-sneakers', name: 'Tenis hielo', category: 'Calzado', type: 'shoes', color: '#e5e7eb', shade: 'Hielo' },
	{ id: 'pine-cap', name: 'Gorra pino', category: 'Gorras', type: 'hat', color: '#315b58', shade: 'Pino' },
];

const defaultSavedLooks = [
	{
		id: 'saved-look-1',
		name: 'Minimal índigo',
		mood: 'Capas moderadas',
		signature: 'sweater-blue|sand-pants|silver-watch|white-sneakers|pine-cap',
		items: { shirt: wardrobe[0], pants: wardrobe[6], accessory: wardrobe[8], shoes: wardrobe[10], hat: wardrobe[11] },
	},
	{
		id: 'saved-look-2',
		name: 'Noche sobria',
		mood: 'Urban chic',
		signature: 'onyx-shirt|charcoal-pants|black-glasses|white-sneakers|pine-cap',
		items: { shirt: wardrobe[3], pants: wardrobe[7], accessory: wardrobe[9], shoes: wardrobe[10], hat: wardrobe[11] },
	},
];

const palette = [
	{ name: 'Tu piel', color: '#cf916c' },
	{ name: 'Ónix', color: '#101115' },
	{ name: 'Azul tinta', color: '#27364b' },
	{ name: 'Vino', color: '#61263a' },
	{ name: 'Pino', color: '#345957' },
	{ name: 'Plata', color: '#b5bcc8' },
	{ name: 'Hielo', color: '#f0e9e5' },
];

const stageColors = {
	Cálido: { top: '#9b603f', middle: '#7b4b37', floor: '#d2a17a' },
	Frío: { top: '#4c7598', middle: '#3d617f', floor: '#9cbed4' },
	Neutro: { top: '#777c83', middle: '#5b6067', floor: '#adb2b8' },
};

const categoryIcons = {
	Camisas: Shirt,
	Pantalones: PiPants,
	Accesorios: Glasses,
	Calzado: PiSneaker,
	Gorras: PiBaseballCap,
};

const metricFields = [
	{ key: 'height', label: 'Altura', min: 140, max: 205, unit: 'cm' },
	{ key: 'weight', label: 'Peso', min: 40, max: 140, unit: 'kg' },
	{ key: 'complexion', label: 'Complexión', min: 0, max: 100 },
	{ key: 'bodyFat', label: 'Grasa corporal', min: 5, max: 50, unit: '%' },
	{ key: 'muscle', label: 'Masa muscular', min: 10, max: 60, unit: '%' },
	{ key: 'shoulders', label: 'Hombros', min: 32, max: 60, unit: 'cm' },
	{ key: 'waist', label: 'Cintura', min: 50, max: 130, unit: 'cm' },
	{ key: 'hips', label: 'Cadera', min: 60, max: 145, unit: 'cm' },
];

function formatMetric(field, value) {
	if (field.key === 'complexion') {
		if (value < 35) return 'Delgada';
		if (value > 65) return 'Robusta';
		return 'Media';
	}
	return `${value} ${field.unit}`;
}

function getLookSignature(items) {
	return Object.values(items).map((item) => item.id).join('|');
}

function CategoryTab({ category, isActive, onClick }) {
	const Icon = categoryIcons[category];

	return (
		<button
			aria-label={category}
			aria-selected={isActive}
			className={isActive ? 'category-tab is-active' : 'category-tab'}
			onClick={onClick}
			role="tab"
			title={category}
			type="button"
		>
			<Icon aria-hidden="true" size={17} strokeWidth={1.7} />
		</button>
	);
}

function SaveLookButton({ saved, onClick }) {
	return (
		<button
			aria-pressed={saved}
			className={saved ? 'outline-button save-look-button is-saved' : 'outline-button save-look-button'}
		onClick={onClick}
		type="button"
	>
			<Check size={15} />{saved ? 'Look guardado' : 'Guardar look'}
		</button>
	);
}

export default function Main() {
	const [activeView, setActiveView] = useState('DressMe');
	const [menuOpen, setMenuOpen] = useState(false);
	const [theme, setTheme] = useState(() => {
		try {
			return window.localStorage.getItem('ondressme-theme') === 'light' ? 'light' : 'dark';
		} catch {
			return 'dark';
		}
	});
	const [activeCategory, setActiveCategory] = useState('Camisas');
	const [profileForm, setProfileForm] = useState(() => {
		try {
			const stored = JSON.parse(window.localStorage.getItem('ondressme-profile') || '{}');
			return {
				name: stored.name || 'Eva García',
				style: stored.style || 'Invierno profundo',
				photoName: stored.photoName || 'Sin foto aún',
			};
		} catch {
			return { name: 'Eva García', style: 'Invierno profundo', photoName: 'Sin foto aún' };
		}
	});
	const [profileModalOpen, setProfileModalOpen] = useState(() => {
		try {
			return !window.localStorage.getItem('ondressme-profile-created');
		} catch {
			return true;
		}
	});
	const closetTrackRef = useRef(null);
	const [selectedItems, setSelectedItems] = useState({
		shirt: wardrobe[0],
		pants: wardrobe[6],
		accessory: wardrobe[8],
		shoes: wardrobe[10],
		hat: wardrobe[11],
	});
	const [undertone, setUndertone] = useState('Neutro');
	const [savedLooks, setSavedLooks] = useState(defaultSavedLooks);
	const [measurementsSaved, setMeasurementsSaved] = useState(false);
	const [bodyMetrics, setBodyMetrics] = useState({
		height: 173,
		weight: 68,
		complexion: 50,
		bodyFat: 22,
		muscle: 36,
		shoulders: 44,
		waist: 78,
		hips: 96,
	});

	const currentLookSignature = getLookSignature(selectedItems);
	const saved = savedLooks.some((look) => look.signature === currentLookSignature);
	const visibleItems = wardrobe.filter((item) => item.category === activeCategory);
	const outfitSlots = [
		{ category: 'Gorras', item: selectedItems.hat },
		{ category: 'Accesorios', item: selectedItems.accessory },
		{ category: 'Camisas', item: selectedItems.shirt },
		{ category: 'Pantalones', item: selectedItems.pants },
		{ category: 'Calzado', item: selectedItems.shoes },
	];

	function previewItem(item) {
		setSelectedItems((current) => ({ ...current, [item.type]: item }));
	}

	function toggleSaveCurrentLook() {
		const signature = currentLookSignature;
		const alreadySaved = savedLooks.some((look) => look.signature === signature);

		if (alreadySaved) {
			setSavedLooks((current) => current.filter((look) => look.signature !== signature));
			return;
		}

		setSavedLooks((current) => [{
			id: `saved-look-${Date.now()}`,
			name: `Look ${current.length + 1}`,
			mood: 'Guardado hoy',
			signature,
			items: { ...selectedItems },
		}, ...current].slice(0, 6));
	}

	function applySavedLook(look) {
		setSelectedItems(look.items);
		setActiveCategory('Camisas');
	}

	function scrollCloset(direction) {
		closetTrackRef.current?.scrollBy({ left: direction * 300, behavior: 'smooth' });
	}

	function toggleTheme() {
		const nextTheme = theme === 'dark' ? 'light' : 'dark';
		setTheme(nextTheme);
		try {
			window.localStorage.setItem('ondressme-theme', nextTheme);
		} catch {
			return;
		}
	}

	function handleProfileChange(field, value) {
		setProfileForm((current) => ({ ...current, [field]: value }));
	}

	function saveProfile() {
		try {
			window.localStorage.setItem('ondressme-profile', JSON.stringify(profileForm));
			window.localStorage.setItem('ondressme-profile-created', 'true');
		} catch {
			return;
		}
		setProfileModalOpen(false);
	}

	useEffect(() => {
		if (!profileModalOpen) {
			try {
				window.localStorage.setItem('ondressme-profile', JSON.stringify(profileForm));
			} catch {
				return;
			}
		}
	}, [profileForm, profileModalOpen]);

	return (
		<div className="dressme-app" data-theme={theme}>
			<header className="topbar">
				<button
					aria-controls="main-navigation"
					aria-expanded={menuOpen}
					aria-label={menuOpen ? 'Cerrar menú' : 'Abrir menú'}
					className="menu-toggle"
					onClick={() => setMenuOpen(!menuOpen)}
					type="button"
				>
					{menuOpen ? <X size={20} /> : <Menu size={20} />}
				</button>
				<a className="brand" href="#inicio" aria-label="OnDressMe, inicio">
					<span className="brand-mark">O</span>
					<span>ONDRESSME</span>
				</a>
				<nav id="main-navigation" className={menuOpen ? 'main-nav is-open' : 'main-nav'} aria-label="Navegación principal">
					<a className={activeView === 'DressMe' ? 'nav-link is-current' : 'nav-link'} href="#simulador" onClick={(event) => { event.preventDefault(); setActiveView('DressMe'); setMenuOpen(false); }}>DressMe</a>
					<a className={activeView === 'Avatar' ? 'nav-link is-current' : 'nav-link'} href="#avatar" onClick={(event) => { event.preventDefault(); setActiveView('Avatar'); setMenuOpen(false); }}>Avatar</a>
					<a className={activeView === 'Closet' ? 'nav-link is-current' : 'nav-link'} href="#closet" onClick={(event) => { event.preventDefault(); setActiveView('Closet'); setMenuOpen(false); }}>Closet</a>
					<a className={activeView === 'Profile' ? 'nav-link is-current' : 'nav-link'} href="#perfil" onClick={(event) => { event.preventDefault(); setActiveView('Profile'); setMenuOpen(false); }}>Perfil</a>
				</nav>
				<div className="header-actions">
					<button
						aria-label={theme === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
						aria-pressed={theme === 'light'}
						className="theme-toggle"
						onClick={toggleTheme}
						title={theme === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
						type="button"
					>
						{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
					</button>
					<button className="profile-menu" type="button" onClick={() => setActiveView('Profile')}>
						<span className="profile-initials">EG</span>
						<span className="profile-copy"><strong>Eva García</strong><small>Invierno profundo</small></span>
						<ArrowRight size={15} aria-hidden="true" />
					</button>
				</div>
			</header>

			<main className="workspace" id="inicio">
				{profileModalOpen && (
					<div className="profile-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="profile-modal-title">
						<div className="profile-modal-card">
							<div className="profile-modal-header">
								<div className="profile-modal-icon"><UserRound size={18} /></div>
								<div>
									<span className="eyebrow">Bienvenida</span>
									<h2 id="profile-modal-title">Crea tu perfil</h2>
								</div>
							</div>
							<label className="profile-field">
								<span>Nombre</span>
								<input
									placeholder="Tu nombre"
									type="text"
									value={profileForm.name}
									onChange={(event) => handleProfileChange('name', event.target.value)}
								/>
							</label>
							<label className="profile-field">
								<span>Estilo</span>
								<input
									placeholder="Ej. Invierno profundo"
									type="text"
									value={profileForm.style}
									onChange={(event) => handleProfileChange('style', event.target.value)}
								/>
							</label>
							<div className="profile-upload-box">
								<div className="profile-upload-copy">
									<strong>Foto de tu rostro</strong>
									<p>Sube una imagen para preparar la colorimetría y la recomendación de paleta.</p>
								</div>
								<label className="profile-upload-trigger">
									<input
										type="file"
										accept="image/*"
										onChange={(event) => {
											const file = event.target.files?.[0];
											if (file) handleProfileChange('photoName', file.name);
										}}
									/>
									<span>Subir foto</span>
								</label>
							</div>
							<div className="profile-upload-note">Archivo actual: {profileForm.photoName}</div>
							<div className="profile-modal-actions">
								<button className="ghost-button" type="button" onClick={() => setProfileModalOpen(false)}>Más tarde</button>
								<button className="action-button" type="button" onClick={saveProfile}>Guardar perfil</button>
							</div>
						</div>
					</div>
				)}
				{activeView === 'Profile' ? (
					<section className="profile-page" aria-labelledby="profile-page-title">
						<div className="profile-page-header">
							<div>
								<span className="eyebrow">Perfil</span>
								<h1 id="profile-page-title">Tu perfil personal</h1>
							</div>
							<button className="outline-button" type="button" onClick={() => setProfileModalOpen(true)}>Editar perfil</button>
						</div>
						<div className="profile-page-grid">
							<div className="profile-summary-card">
								<div className="profile-avatar">
									<span>{profileForm.name.charAt(0).toUpperCase() || 'E'}</span>
								</div>
								<div className="profile-summary-copy">
									<strong>{profileForm.name}</strong>
									<small>{profileForm.style}</small>
								</div>
							</div>
							<div className="profile-guide-card">
								<span className="eyebrow">Colorimetría</span>
								<h2>Cómo preparar la foto</h2>
								<ol>
									<li>Tu rostro tiene que estar descubierto, sin sombreros, gafas ni accesorios que tapen la cara.</li>
									<li>La foto debe tener iluminacion lo más natural posible, idealmente con luz de día suave.</li>
									<li>Haz la foto en una pared neutra y mirando al frente, con la cara completamente visible.</li>
									<li>Sin filtros, sin maquillaje intenso ni sombras bruscas para una lectura más precisa.</li>
								</ol>
								<label className="profile-upload-box compact">
									<div className="profile-upload-copy">
										<strong>Subir foto del rostro</strong>
										<p>{profileForm.photoName}</p>
									</div>
									<input
										type="file"
										accept="image/*"
										onChange={(event) => {
											const file = event.target.files?.[0];
											if (file) handleProfileChange('photoName', file.name);
										}}
									/>
								</label>
							</div>
						</div>
					</section>
				) : activeView === 'Closet' ? (
					<section className="closet-library" id="closet" aria-labelledby="closet-library-title">
						<div className="closet-library-heading">
					
							<div className="closet-library-title-row">
								<h1 id="closet-library-title">Tu clóset</h1>
								<button className="outline-button add-closet-item" type="button"><span className="add-garment-icon" aria-hidden="true"><Shirt size={16} /><Plus size={9} /></span> Añadir prenda</button>
							</div>
						</div>
						<div className="closet-library-toolbar">
							<div className="category-tabs" role="tablist" aria-label="Categorías de prendas">
								{categories.map((category) => (
									<CategoryTab
										category={category}
										isActive={activeCategory === category}
										key={category}
										onClick={() => setActiveCategory(category)}
									/>
								))}
							</div>
							<div className="closet-carousel-controls" aria-label="Recorrer prendas">
								<button className="icon-button" onClick={() => scrollCloset(-1)} type="button" aria-label="Prendas anteriores"><ChevronLeft size={18} /></button>
								<button className="icon-button" onClick={() => scrollCloset(1)} type="button" aria-label="Prendas siguientes"><ChevronRight size={18} /></button>
							</div>
						</div>
						<div className="closet-carousel">
							<div className="closet-ruler" aria-hidden="true"><span /><i /><span /></div>
							<div className="closet-card-track" ref={closetTrackRef}>
								{visibleItems.map((item, index) => {
									const ItemIcon = categoryIcons[item.category];
									const isSelected = selectedItems[item.type].id === item.id;
									return (
										<button
											aria-label={item.name}
											aria-pressed={isSelected}
											className={isSelected ? 'closet-look-card is-selected' : 'closet-look-card'}
											key={item.id}
											onClick={() => previewItem(item)}
											style={{ '--item-index': index, '--garment-color': item.color }}
											type="button"
										>
											<span className="closet-card-hanger"><PiCoatHanger size={22} /></span>
											<span className="closet-card-visual"><ItemIcon className="closet-card-garment" size={150} strokeWidth={1.1} />{isSelected && <span className="closet-card-check"><Check size={12} /></span>}</span>
											<span className="closet-card-color" />
										</button>
									);
								})}
							</div>
						</div>
						<div className="closet-library-footer"><span>{visibleItems.length} prendas en {activeCategory.toLowerCase()}</span><button type="button" onClick={() => setActiveView('DressMe')}>Volver al simulador <ArrowRight size={15} /></button></div>
						<section className="saved-looks-panel" aria-labelledby="saved-looks-title-library">
							<div className="saved-looks-header">
								<div>
									<span className="eyebrow">Looks guardados</span>
									<h2 id="saved-looks-title-library">Tu selección favorita</h2>
								</div>
								<span className="saved-looks-count">{savedLooks.length} looks</span>
							</div>
							<div className="saved-looks-list">
								{savedLooks.length === 0 ? (
									<div className="saved-look-empty">Aún no tienes looks guardados. Guarda el look actual para volverlo a usar más tarde.</div>
								) : (
									savedLooks.map((look) => (
										<article className="saved-look-card" key={look.id}>
											<div className="saved-look-summary">
												<div className="saved-look-swatches" aria-label={`Colores de ${look.name}`}>
													{Object.values(look.items).map((item) => (
														<span key={`${look.id}-${item.id}`} style={{ backgroundColor: item.color }} title={item.name} />
													))}
												</div>
												<div className="saved-look-copy">
													<strong>{look.name}</strong>
													<small>{look.mood}</small>
												</div>
											</div>
											<div className="saved-look-actions">
												<button className="action-button" type="button" onClick={() => applySavedLook(look)}>Aplicar look</button>
												<button className="ghost-button" type="button" onClick={() => setSavedLooks((current) => current.filter((savedLook) => savedLook.id !== look.id))}>Quitar</button>
											</div>
										</article>
									))
								)}
							</div>
						</section>
					</section>
				) : (
				<>
				<div className="workspace-grid">
					<section className="simulator-panel" id="simulador" aria-labelledby="simulator-title">
						<div className="panel-heading">
							<div>
								<span className="eyebrow">Simulador</span>
								<h1 id="simulator-title">{activeView === 'Avatar' ? 'Tu avatar' : 'Tu maniquí'}</h1>
							</div>
							<button className="icon-button" type="button" title="Ampliar visor" aria-label="Ampliar visor">
								<Maximize2 size={17} />
							</button>
						</div>
						<div className="simulator-stage-row">
						<div
							className={activeView === 'DressMe' ? 'avatar-stage has-outfit-slots' : 'avatar-stage'}
							id="avatar"
							style={{
								'--stage-top': stageColors[undertone].top,
								'--stage-middle': stageColors[undertone].middle,
								'--stage-floor': stageColors[undertone].floor,
							}}
						>
							{activeView === 'DressMe' && (
								<aside className="outfit-slots" aria-label="Prendas elegidas para el avatar">
									<div className="outfit-slot-list">
										{outfitSlots.map(({ category, item }) => {
											const SlotIcon = categoryIcons[category];
											return (
												<button
													aria-label={`${category}: ${item.name}`}
													aria-pressed={activeCategory === category}
													className={activeCategory === category ? 'outfit-slot is-active' : 'outfit-slot'}
													key={category}
													onClick={() => setActiveCategory(category)}
													title={`${category}: ${item.name}`}
													type="button"
												>
													<span className="outfit-slot-visual" style={{ '--garment-color': item.color }}>
														<SlotIcon size={34} strokeWidth={1.5} />
													</span>
												</button>
											);
										})}
									</div>
								</aside>
							)}
							<div className="height-markers" aria-hidden="true">
								<span>190</span><i /><span>175</span><i /><span>155</span><i />
							</div>
							<div className="undertone-controls" aria-label="Subtono de piel">
								{[
									['Cálido', '#f08225'],
									['Frío', '#a8d7e8'],
									['Neutro', '#aeb1b5'],
								].map(([label, color]) => (
									<button
										className={undertone === label ? 'undertone-option is-selected' : 'undertone-option'}
										key={label}
										onClick={() => setUndertone(label)}
										type="button"
									>
										<span style={{ backgroundColor: color }} />{label}
									</button>
								))}
							</div>
							<MannequinCanvas
								shirtColor={selectedItems.shirt.color}
								pantsColor={selectedItems.pants.color}
								accessoryColor={selectedItems.accessory.color}
								shoesColor={selectedItems.shoes.color}
								hatColor={selectedItems.hat.color}
								bodyMetrics={bodyMetrics}
							/>
							<div className="rotate-hint"><span>↔</span> Arrastra para rotar</div>
						</div>
						</div>
						<div className={activeView === 'Avatar' ? 'look-score' : 'look-score is-hidden'} id="perfil">
							{activeView === 'Avatar' && <SaveLookButton saved={saved} onClick={toggleSaveCurrentLook} />}
						</div>
					</section>

					{activeView === 'Avatar' ? (
						<aside className="metrics-panel" id="avatar-metrics" aria-labelledby="metrics-title">
							<div className="metrics-heading">
								<div className="closet-icon"><UserRound size={18} /></div>
								<div><span className="eyebrow">Métricas corporales</span><h2 id="metrics-title">Define tu cuerpo</h2></div>
							</div>
							<div className="metric-summary">
								<div className="metric-card"><small>Altura</small><strong>{bodyMetrics.height}<span> cm</span></strong></div>
								<div className="metric-card"><small>Peso</small><strong>{bodyMetrics.weight}<span> kg</span></strong></div>
							</div>
							<div className="measurements-title">
								<strong>Proporciones generales</strong>
								<small>Los cambios se reflejan en el avatar</small>
							</div>
							<div className="measurement-grid">
								{metricFields.map((field) => (
									<label className="measure-control" key={field.key}>
										<span className="measure-label"><span>{field.label}</span><strong>{formatMetric(field, bodyMetrics[field.key])}</strong></span>
										<input
											aria-label={field.label}
											max={field.max}
											min={field.min}
											onChange={(event) => {
												setBodyMetrics((current) => ({ ...current, [field.key]: Number(event.target.value) }));
												setMeasurementsSaved(false);
											}}
											step="1"
											type="range"
											value={bodyMetrics[field.key]}
										/>
									</label>
								))}
							</div>
							<div className="measurements-footer">
								<span><Info size={13} /> Tus medidas se guardan en este dispositivo.</span>
								<button className={measurementsSaved ? 'outline-button is-saved' : 'outline-button'} onClick={() => setMeasurementsSaved(true)} type="button">
									<Check size={14} />{measurementsSaved ? 'Medidas guardadas' : 'Guardar medidas'}
								</button>
							</div>
						</aside>
					) : (
					<aside className="closet-panel" id="closet" aria-labelledby="closet-title">
						<div className="closet-heading">
							<div className="closet-icon"><Shirt size={18} /></div>
							<div><span className="eyebrow">Clóset digital</span><h2 id="closet-title">Tu ropa</h2></div>
							{activeView === 'DressMe' && <SaveLookButton saved={saved} onClick={toggleSaveCurrentLook} />}
						</div>
						<div className="category-tabs" role="tablist" aria-label="Categorías de prendas">
							{categories.map((category) => (
								<CategoryTab
									category={category}
									isActive={activeCategory === category}
									key={category}
									onClick={() => setActiveCategory(category)}
								/>
							))}
						</div>
						<h3 className="items-heading">{activeCategory}<span>{visibleItems.length} prendas</span></h3>
						<div className="wardrobe-grid">
							{visibleItems.map((item, index) => {
								const ItemIcon = categoryIcons[item.category];
								const isSelected = selectedItems[item.type].id === item.id;
								return (
									<button
										aria-label={item.name}
										aria-pressed={isSelected}
										className={isSelected ? 'wardrobe-item is-selected' : 'wardrobe-item'}
										key={item.id}
										onClick={() => previewItem(item)}
										style={{ '--item-index': index }}
										type="button"
									>
										<span className="garment-preview" style={{ '--garment-color': item.color }}>
											<ItemIcon size={42} strokeWidth={1.35} />
											{isSelected && <span className="garment-check"><Check size={12} strokeWidth={2.5} /></span>}
										</span>
										<span className="wardrobe-item-name">{item.name}</span>
									</button>
								);
							})}
						</div>
						<div className="closet-actions">
							<button className="action-button" type="button"><span className="add-garment-icon" aria-hidden="true"><Shirt size={16} /><Plus size={9} /></span> Añadir prenda</button>
							<button className="action-button" onClick={() => setActiveView('Closet')} type="button">Ver clóset completo <PiCoatHanger size={15} /></button>
						</div>
						<div className="outfit-palette">
							<div className="palette-title"><span className="eyebrow">Paleta del outfit</span><Sparkles size={14} /></div>
							<div className="selected-swatches" aria-label="Colores del outfit">
								{[selectedItems.shirt, selectedItems.pants, selectedItems.accessory].map((item) => (
									<span key={item.type} title={item.shade} style={{ backgroundColor: item.color }} />
								))}
							</div>
						</div>
						{activeView === 'DressMe' && (
							<section className="recommendation-panel closet-palette-panel" aria-labelledby="recommendation-title">
								<div className="recommendation-copy">
									<span className="eyebrow">Recomendación</span>
									<h2 id="recommendation-title">Tu paleta hoy</h2>
									<p>Combina bases profundas con acentos fríos y luminosos.</p>
								</div>
								<div className="season-palette">
									{palette.map((color) => (
										<div className="season-color" key={color.name}>
											<span style={{ backgroundColor: color.color }} />
											<small>{color.name}</small>
										</div>
									))}
								</div>
								<button className="guide-button" type="button">Ver guía completa <ArrowRight size={16} /></button>
							</section>
						)}
						</aside>
					)}
				</div>
				</>
				)}
			</main>
			<footer className="page-footer" aria-hidden="true" />
		</div>
	);
}
