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
	Plus,
	Shirt,
	Sparkles,
	UserRound,
	X,
} from 'lucide-react';
import { PiBaseballCap, PiCoatHanger, PiPants, PiSneaker } from 'react-icons/pi';
import MannequinCanvas from '../features/mannequin/MannequinScene.jsx';
import OnboardingModal from '../features/onboarding/OnboardingModal.jsx';
import '../App.css';

const categories = ['Tops', 'Bottoms', 'Accessories', 'Shoes', 'Hats'];
const themeOptions = [
	{ value: 'noir', label: 'Noir' },
	{ value: 'light', label: 'Porcelain' },
	{ value: 'amethyst', label: 'Amethyst' },
	{ value: 'ocean', label: 'Ocean' },
	{ value: 'forest', label: 'Forest' },
	{ value: 'rose', label: 'Rose' },
	{ value: 'amber', label: 'Amber' },
	{ value: 'mint', label: 'Mint' },
	{ value: 'sakura', label: 'Sakura' },
	{ value: 'slate', label: 'Slate' },
	{ value: 'terracotta', label: 'Terracota' },
	{ value: 'cobalt', label: 'Cobalt' },
];

const wardrobe = [
	{ id: 'sweater-blue', name: 'Blue sweater', category: 'Tops', type: 'shirt', color: '#36546d', shade: 'Ink blue' },
	{ id: 'wine-top', name: 'Wine top', category: 'Tops', type: 'shirt', color: '#773d50', shade: 'Wine' },
	{ id: 'ice-shirt', name: 'Ice shirt', category: 'Tops', type: 'shirt', color: '#d8dce2', shade: 'Ice' },
	{ id: 'onyx-shirt', name: 'Onyx shirt', category: 'Tops', type: 'shirt', color: '#17181d', shade: 'Onyx' },
	{ id: 'pine-knit', name: 'Pine sweater', category: 'Tops', type: 'shirt', color: '#315b58', shade: 'Pine' },
	{ id: 'silver-top', name: 'Silver top', category: 'Tops', type: 'shirt', color: '#aeb6c4', shade: 'Silver' },
	{ id: 'sand-pants', name: 'Sand trousers', category: 'Bottoms', type: 'pants', color: '#c4a374', shade: 'Sand' },
	{ id: 'charcoal-pants', name: 'Charcoal trousers', category: 'Bottoms', type: 'pants', color: '#34353a', shade: 'Charcoal' },
	{ id: 'silver-watch', name: 'Silver watch', category: 'Accessories', type: 'accessory', color: '#b7bdc8', shade: 'Silver' },
	{ id: 'black-glasses', name: 'Onyx glasses', category: 'Accessories', type: 'accessory', color: '#202126', shade: 'Onyx' },
	{ id: 'white-sneakers', name: 'Ice sneakers', category: 'Shoes', type: 'shoes', color: '#e5e7eb', shade: 'Ice' },
	{ id: 'pine-cap', name: 'Pine cap', category: 'Hats', type: 'hat', color: '#315b58', shade: 'Pine' },
];

const defaultSavedLooks = [
	{
		id: 'saved-look-1',
		name: 'Minimal indigo',
		mood: 'Light layers',
		signature: 'sweater-blue|sand-pants|silver-watch|white-sneakers|pine-cap',
		items: { shirt: wardrobe[0], pants: wardrobe[6], accessory: wardrobe[8], shoes: wardrobe[10], hat: wardrobe[11] },
	},
	{
		id: 'saved-look-2',
		name: 'Understated evening',
		mood: 'Urban chic',
		signature: 'onyx-shirt|charcoal-pants|black-glasses|white-sneakers|pine-cap',
		items: { shirt: wardrobe[3], pants: wardrobe[7], accessory: wardrobe[9], shoes: wardrobe[10], hat: wardrobe[11] },
	},
];

const stageColors = {
	Warm: { top: '#9b603f', middle: '#7b4b37', floor: '#d2a17a' },
	Cool: { top: '#4c7598', middle: '#3d617f', floor: '#9cbed4' },
	Neutral: { top: '#777c83', middle: '#5b6067', floor: '#adb2b8' },
};

const categoryIcons = {
	Tops: Shirt,
	Bottoms: PiPants,
	Accessories: Glasses,
	Shoes: PiSneaker,
	Hats: PiBaseballCap,
};

const metricFields = [
	{ key: 'height', label: 'Height', min: 140, max: 205, unit: 'cm' },
	{ key: 'weight', label: 'Weight', min: 40, max: 140, unit: 'kg' },
	{ key: 'complexion', label: 'Build', min: 0, max: 100 },
	{ key: 'bodyFat', label: 'Body fat', min: 5, max: 50, unit: '%' },
	{ key: 'muscle', label: 'Muscle mass', min: 10, max: 60, unit: '%' },
	{ key: 'shoulders', label: 'Shoulders', min: 32, max: 60, unit: 'cm' },
	{ key: 'waist', label: 'Waist', min: 50, max: 130, unit: 'cm' },
	{ key: 'hips', label: 'Hips', min: 60, max: 145, unit: 'cm' },
];

function formatMetric(field, value) {
	if (field.key === 'complexion') {
		if (value < 35) return 'Slim';
		if (value > 65) return 'Broad';
		return 'Average';
	}
	return `${value} ${field.unit}`;
}

function getLookSignature(items) {
	return Object.values(items).map((item) => item.id).join('|');
}

function localizeSavedStyle(style) {
	if (!style || style === 'Invierno profundo') return 'Deep Winter';
	const styleLabels = { Otoño: 'Autumn', Primavera: 'Spring', Invierno: 'Winter', Verano: 'Summer' };
	const undertoneLabels = { Cálido: 'Warm', Frío: 'Cool' };
	const match = style.match(/^(Otoño|Primavera|Invierno|Verano)\s*\((Cálido|Frío)\)$/);
	return match ? `${styleLabels[match[1]]} (${undertoneLabels[match[2]]})` : style;
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
			<Check size={15} />			{saved ? 'Look saved' : 'Save look'}
		</button>
	);
}

export default function Main() {
	const [activeView, setActiveView] = useState('DressMe');
	const [menuOpen, setMenuOpen] = useState(false);
	const [theme, setTheme] = useState(() => {
		try {
			const storedTheme = window.localStorage.getItem('ondressme-theme');
			if (storedTheme === 'dark') return 'noir';
			return themeOptions.some((option) => option.value === storedTheme) ? storedTheme : 'noir';
		} catch {
			return 'noir';
		}
	});
	const [activeCategory, setActiveCategory] = useState('Tops');
	const [profileForm, setProfileForm] = useState(() => {
		try {
			const stored = JSON.parse(window.localStorage.getItem('ondressme-profile') || '{}');
			return {
				name: stored.name || 'Eva Garcia',
				style: localizeSavedStyle(stored.style),
				photoName: stored.photoName === 'Sin foto aún' ? 'No photo yet' : stored.photoName || 'No photo yet',
			};
		} catch {
			return { name: 'Eva Garcia', style: 'Deep Winter', photoName: 'No photo yet' };
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
	const [undertone, setUndertone] = useState('Neutral');
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
		{ category: 'Hats', item: selectedItems.hat },
		{ category: 'Accessories', item: selectedItems.accessory },
		{ category: 'Tops', item: selectedItems.shirt },
		{ category: 'Bottoms', item: selectedItems.pants },
		{ category: 'Shoes', item: selectedItems.shoes },
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
			mood: 'Saved today',
			signature,
			items: { ...selectedItems },
		}, ...current].slice(0, 6));
	}

	function applySavedLook(look) {
		setSelectedItems(look.items);
		setActiveCategory('Tops');
	}

	function scrollCloset(direction) {
		closetTrackRef.current?.scrollBy({ left: direction * 300, behavior: 'smooth' });
	}

	function selectTheme(event) {
		const nextTheme = event.target.value;
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

	useEffect(() => {
		if (!profileModalOpen) {
			try {
				window.localStorage.setItem('ondressme-profile', JSON.stringify(profileForm));
			} catch {
				return;
			}
		}
	}, [profileForm, profileModalOpen]);

	function renderClosetPanel() {
		return (
			<aside className={activeView === 'DressMe' ? 'closet-panel dressing-room-closet-panel' : 'closet-panel'} id="closet" aria-labelledby="closet-title">
				<div className={activeView === 'DressMe' ? 'closet-heading dressing-room-closet-heading' : 'closet-heading'}>
					<div className="closet-icon"><Shirt size={18} /></div>
					<div><span className="eyebrow">{activeView === 'DressMe' ? 'Wardrobe' : 'Digital closet'}</span><h2 id="closet-title">{activeView === 'DressMe' ? 'Choose an item' : 'Your clothes'}</h2></div>
				</div>
				<div className="category-tabs" role="tablist" aria-label="Clothing categories">
					{categories.map((category) => (
						<CategoryTab
							category={category}
							isActive={activeCategory === category}
							key={category}
							onClick={() => setActiveCategory(category)}
						/>
					))}
				</div>
				<h3 className="items-heading">{activeCategory}<span>{visibleItems.length} items</span></h3>
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
				{activeView !== 'DressMe' && <div className="closet-actions">
					<button className="action-button" type="button"><span className="add-garment-icon" aria-hidden="true"><Shirt size={16} /><Plus size={9} /></span> Add item</button>
					<button className="action-button" onClick={() => setActiveView('Closet')} type="button">View full closet <PiCoatHanger size={15} /></button>
				</div>}
				<div className={activeView === 'DressMe' ? 'outfit-palette dressing-room-outfit-palette' : 'outfit-palette'}>
					<div className="palette-title"><span className="eyebrow">Outfit palette</span><Sparkles size={14} /></div>
					<div className="selected-swatches" aria-label="Outfit colors">
						{(activeView === 'DressMe' ? outfitSlots.map(({ item }) => item) : [selectedItems.shirt, selectedItems.pants, selectedItems.accessory]).map((item) => (
							<span key={item.type} title={item.shade} style={{ backgroundColor: item.color }} />
						))}
					</div>
				</div>
			</aside>
		);
	}

	return (
		<div className="dressme-app" data-theme={theme}>
			{profileModalOpen && (
				<OnboardingModal
					isOpen={profileModalOpen}
					initialProfile={profileForm}
					onComplete={(newProfile) => {
						setProfileForm(newProfile);
						try {
							window.localStorage.setItem('ondressme-profile-created', 'true');
						} catch {
							// Keep the completed profile in memory if browser storage is unavailable.
						}
						setProfileModalOpen(false);
					}}
				/>
			)}
			<header className="topbar relative z-50 flex h-[65px] items-center gap-[14px] border-b border-line bg-surface/90 px-[max(4.6vw,24px)] max-[700px]:h-[60px] max-[700px]:gap-[10px] max-[700px]:px-[14px]">
				<button
					aria-controls="main-navigation"
					aria-expanded={menuOpen}
					aria-label={menuOpen ? 'Close menu' : 'Open menu'}
					className="menu-toggle"
					onClick={() => setMenuOpen(!menuOpen)}
					type="button"
				>
					{menuOpen ? <X size={20} /> : <Menu size={20} />}
				</button>
				<a className="brand" href="#inicio" aria-label="OnDressMe, home">
					<img className="brand-logo" src="/ondressme-logo.png" alt="OnDressMe logo" />
				</a>
				<nav id="main-navigation" className={menuOpen ? 'main-nav is-open' : 'main-nav'} aria-label="Main navigation">
					<a className={activeView === 'DressMe' ? 'nav-link is-current' : 'nav-link'} href="#simulador" onClick={(event) => { event.preventDefault(); setActiveView('DressMe'); setMenuOpen(false); }}>DressMe</a>
					<a className={activeView === 'Avatar' ? 'nav-link is-current' : 'nav-link'} href="#avatar" onClick={(event) => { event.preventDefault(); setActiveView('Avatar'); setMenuOpen(false); }}>Avatar</a>
					<a className={activeView === 'Closet' ? 'nav-link is-current' : 'nav-link'} href="#closet" onClick={(event) => { event.preventDefault(); setActiveView('Closet'); setMenuOpen(false); }}>Closet</a>
					<a className={activeView === 'Profile' ? 'nav-link is-current' : 'nav-link'} href="#perfil" onClick={(event) => { event.preventDefault(); setActiveView('Profile'); setMenuOpen(false); }}>Profile</a>
				</nav>
				<div className="header-actions">
					<label className="theme-picker" title="Color theme">
						<span aria-hidden="true">Theme</span>
						<select aria-label="Choose a color theme" onChange={selectTheme} value={theme}>
							{themeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
						</select>
					</label>
					<button className="profile-menu" type="button" onClick={() => setActiveView('Profile')}>
						<span className="profile-initials">{profileForm.name.slice(0, 2).toUpperCase() || 'E'}</span>
						<span className="profile-copy"><strong>{profileForm.name}</strong><small>{profileForm.style}</small></span>
						<ArrowRight size={15} aria-hidden="true" />
					</button>
				</div>
			</header>

			<main className={activeView === 'DressMe'
				? 'workspace dressing-room-workspace mx-auto mb-14 mt-5 w-[calc(100%-48px)] max-w-[1206px] max-[700px]:mt-[14px] max-[700px]:w-[calc(100%-28px)] max-[700px]:max-w-[540px]'
				: 'workspace mx-auto mb-14 mt-5 w-[calc(100%-48px)] max-w-[1206px] max-[700px]:mt-[14px] max-[700px]:w-[calc(100%-28px)] max-[700px]:max-w-[540px]'} id="inicio">
				{activeView === 'Profile' ? (
					<section className="profile-page" aria-labelledby="profile-page-title">
						<div className="profile-page-header">
							<div>
								<span className="eyebrow">Profile</span>
								<h1 id="profile-page-title">Your profile</h1>
							</div>
							<button className="outline-button" type="button" onClick={() => setProfileModalOpen(true)}>Edit profile</button>
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
								<span className="eyebrow">Color analysis</span>
								<h2>How to prepare your photo</h2>
								<ol>
									<li>Keep your face uncovered, without hats, glasses, or accessories that obscure it.</li>
									<li>Use natural lighting, ideally soft daylight.</li>
									<li>Take the photo against a neutral wall while looking straight ahead, with your face fully visible.</li>
									<li>Avoid filters, heavy makeup, and harsh shadows for a more accurate reading.</li>
								</ol>
								<label className="profile-upload-box compact">
									<div className="profile-upload-copy">
										<strong>Upload a face photo</strong>
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
								<h1 id="closet-library-title">Your closet</h1>
								<button className="outline-button add-closet-item" type="button"><span className="add-garment-icon" aria-hidden="true"><Shirt size={16} /><Plus size={9} /></span> Add item</button>
							</div>
						</div>
						<div className="closet-library-toolbar">
							<div className="category-tabs" role="tablist" aria-label="Clothing categories">
								{categories.map((category) => (
									<CategoryTab
										category={category}
										isActive={activeCategory === category}
										key={category}
										onClick={() => setActiveCategory(category)}
									/>
								))}
							</div>
							<div className="closet-carousel-controls" aria-label="Browse clothing">
								<button className="icon-button" onClick={() => scrollCloset(-1)} type="button" aria-label="Previous items"><ChevronLeft size={18} /></button>
								<button className="icon-button" onClick={() => scrollCloset(1)} type="button" aria-label="Next items"><ChevronRight size={18} /></button>
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
						<div className="closet-library-footer"><span>{visibleItems.length} items in {activeCategory.toLowerCase()}</span><button type="button" onClick={() => setActiveView('DressMe')}>Back to DressMe <ArrowRight size={15} /></button></div>
						<section className="saved-looks-panel" aria-labelledby="saved-looks-title-library">
							<div className="saved-looks-header">
								<div>
									<span className="eyebrow">Saved looks</span>
									<h2 id="saved-looks-title-library">Your favorite outfits</h2>
								</div>
								<span className="saved-looks-count">{savedLooks.length} saved</span>
							</div>
							<div className="saved-looks-list">
								{savedLooks.length === 0 ? (
									<div className="saved-look-empty">You haven't saved any looks yet. Save your current outfit to use it again later.</div>
								) : (
									savedLooks.map((look) => (
										<article className="saved-look-card" key={look.id}>
											<div className="saved-look-summary">
												<div className="saved-look-swatches" aria-label={`Colors in ${look.name}`}>
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
												<button className="action-button" type="button" onClick={() => applySavedLook(look)}>Apply look</button>
												<button className="ghost-button" type="button" onClick={() => setSavedLooks((current) => current.filter((savedLook) => savedLook.id !== look.id))}>Remove</button>
											</div>
										</article>
									))
								)}
							</div>
						</section>
					</section>
				) : (
					<>
						<div className={activeView === 'DressMe'
							? 'workspace-grid dressing-room-grid'
							: 'workspace-grid grid grid-cols-1 items-stretch gap-3 min-[951px]:grid-cols-[minmax(0,1.85fr)_minmax(330px,1fr)] max-[950px]:grid-cols-[minmax(0,1.45fr)_minmax(295px,1fr)] max-[700px]:grid-cols-1'}>
							<section className="simulator-panel" id="simulador" aria-labelledby="simulator-title">
								<div className={activeView === 'DressMe' ? 'panel-heading dressing-room-heading' : 'panel-heading'}>
									<div>
										{activeView !== 'DressMe' && <span className="eyebrow">Dressing room</span>}
										<h1 id="simulator-title">{activeView === 'Avatar' ? 'Your avatar' : 'Your mannequin'}</h1>
									</div>
									{activeView !== 'DressMe' && (
										<button className="icon-button" type="button" title="Expand viewer" aria-label="Expand viewer">
											<Maximize2 size={17} />
										</button>
									)}
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
											<aside className="outfit-slots" aria-label="Selected outfit items">
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
																<span className="outfit-slot-copy"><small>{category}</small><strong>{item.name}</strong></span>
															</button>
														);
													})}
												</div>
											</aside>
										)}
										<div className={activeView === 'DressMe' ? 'mannequin-viewer dressing-room-mannequin-viewer' : 'mannequin-viewer'}>
											<div className="height-markers" aria-hidden="true">
												<span>190</span><i /><span>175</span><i /><span>155</span><i />
											</div>
											<div className="undertone-controls" aria-label="Skin undertone">
												{[
													['Warm', '#f08225'],
													['Cool', '#a8d7e8'],
													['Neutral', '#aeb1b5'],
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
											<div className="rotate-hint"><span>↔</span> Drag to rotate</div>
										</div>
										{activeView === 'DressMe' && renderClosetPanel()}
									</div>
								</div>
								{activeView === 'DressMe' && (
									<div className="dressing-room-footer">
										<div className="dressing-room-footer-copy">
											<span className="eyebrow">Current selection</span>
											<strong>{selectedItems[visibleItems[0]?.type]?.name || 'Choose an item'}</strong>
										</div>
										<SaveLookButton saved={saved} onClick={toggleSaveCurrentLook} />
									</div>
								)}
								<div className={activeView === 'Avatar' ? 'look-score' : 'look-score is-hidden'} id="perfil">
									{activeView === 'Avatar' && <SaveLookButton saved={saved} onClick={toggleSaveCurrentLook} />}
								</div>
							</section>

							{activeView === 'Avatar' ? (
								<aside className="metrics-panel" id="avatar-metrics" aria-labelledby="metrics-title">
									<div className="metrics-heading">
										<div className="closet-icon"><UserRound size={18} /></div>
										<div><span className="eyebrow">Body measurements</span><h2 id="metrics-title">Define your body</h2></div>
									</div>
									<div className="metric-summary">
										<div className="metric-card"><small>Height</small><strong>{bodyMetrics.height}<span> cm</span></strong></div>
										<div className="metric-card"><small>Weight</small><strong>{bodyMetrics.weight}<span> kg</span></strong></div>
									</div>
									<div className="measurements-title">
										<strong>Overall proportions</strong>
										<small>Changes are reflected in your avatar</small>
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
										<span><Info size={13} /> Your measurements are saved on this device.</span>
										<button className={measurementsSaved ? 'outline-button is-saved' : 'outline-button'} onClick={() => setMeasurementsSaved(true)} type="button">
											<Check size={14} />{measurementsSaved ? 'Measurements saved' : 'Save measurements'}
										</button>
									</div>
								</aside>
							) : activeView === 'Closet' ? renderClosetPanel() : null}
						</div>
					</>
				)}
			</main>
			<footer className="page-footer" aria-hidden="true" />
		</div>
	);
}