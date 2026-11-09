import { useRef, useState } from 'react';
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
	Cálido: { top: '#57443d', middle: '#3e3837', floor: '#89786f' },
	Frío: { top: '#3e4b59', middle: '#343a42', floor: '#77818b' },
	Neutro: { top: '#47484d', middle: '#35363a', floor: '#777a80' },
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
	const closetTrackRef = useRef(null);
	const [selectedItems, setSelectedItems] = useState({
		shirt: wardrobe[0],
		pants: wardrobe[6],
		accessory: wardrobe[8],
		shoes: wardrobe[10],
		hat: wardrobe[11],
	});
	const [undertone, setUndertone] = useState('Neutro');
	const [saved, setSaved] = useState(false);
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

	const visibleItems = wardrobe.filter((item) => item.category === activeCategory);
	const activeSelectedItem = visibleItems.find((item) => selectedItems[item.type].id === item.id);
	const ActiveCategoryIcon = categoryIcons[activeCategory];
	const bmi = bodyMetrics.weight / ((bodyMetrics.height / 100) ** 2);
	const bmiCategory = bmi < 18.5 ? 'bajo' : bmi < 25 ? 'normal' : bmi < 30 ? 'alto' : 'obesidad';
	const outfitSlots = [
		{ category: 'Camisas', item: selectedItems.shirt },
		{ category: 'Pantalones', item: selectedItems.pants },
		{ category: 'Accesorios', item: selectedItems.accessory },
		{ category: 'Calzado', item: selectedItems.shoes },
		{ category: 'Gorras', item: selectedItems.hat },
	];

	function previewItem(item) {
		setSelectedItems((current) => ({ ...current, [item.type]: item }));
		setSaved(false);
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
					<a className="nav-link" href="#perfil" onClick={(event) => { event.preventDefault(); setMenuOpen(false); }}>Perfil</a>
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
					<button className="profile-menu" type="button">
						<span className="profile-initials">EG</span>
						<span className="profile-copy"><strong>Eva García</strong><small>Invierno profundo</small></span>
						<ArrowRight size={15} aria-hidden="true" />
					</button>
				</div>
			</header>

			<main className="workspace" id="inicio">
				{activeView === 'Closet' ? (
					<section className="closet-library" id="closet" aria-labelledby="closet-library-title">
						<div className="closet-library-heading">
							<span className="eyebrow">Clóset digital</span>
							<div className="closet-library-title-row">
								<h1 id="closet-library-title">Todo tu estilo, en un solo lugar.</h1>
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
														<span className="outfit-slot-check"><Check size={10} strokeWidth={2.5} /></span>
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
							{activeView === 'Avatar' && <SaveLookButton saved={saved} onClick={() => setSaved(!saved)} />}
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
								<div className="metric-card"><small>IMC</small><strong>{bmi.toFixed(1)}<span> {bmiCategory}</span></strong></div>
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
							{activeView === 'DressMe' && <SaveLookButton saved={saved} onClick={() => setSaved(!saved)} />}
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
						<div className="active-garment" aria-live="polite">
							<span className="active-garment-swatch" style={{ '--garment-color': activeSelectedItem.color }}>
								<ActiveCategoryIcon size={20} strokeWidth={1.6} />
							</span>
							<span className="active-garment-copy"><small>En tu avatar</small><strong>{activeSelectedItem.name}</strong></span>
							<span className="live-preview"><span />Vista 3D</span>
						</div>
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
		</div>
	);
}
