import { useState } from 'react';
import {
	ArrowRight,
	Check,
	Footprints,
	Glasses,
	Maximize2,
	Plus,
	Shirt,
	Sparkles,
	UserRound,
	Watch,
} from 'lucide-react';
import MannequinCanvas from '../features/mannequin/MannequinScene.jsx';
import '../App.css';

const categories = ['Camisas', 'Pantalones', 'Accesorios', 'Tenis', 'Gorras'];

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
	{ id: 'white-sneakers', name: 'Tenis hielo', category: 'Tenis', type: 'shoes', color: '#e5e7eb', shade: 'Hielo' },
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
	Pantalones: Shirt,
	Accesorios: Watch,
	Tenis: Footprints,
	Gorras: Glasses,
};

export default function Main() {
	const [activeCategory, setActiveCategory] = useState('Camisas');
	const [selectedItems, setSelectedItems] = useState({
		shirt: wardrobe[0],
		pants: wardrobe[6],
		accessory: wardrobe[8],
		shoes: wardrobe[10],
		hat: wardrobe[11],
	});
	const [undertone, setUndertone] = useState('Neutro');
	const [saved, setSaved] = useState(false);

	const visibleItems = wardrobe.filter((item) => item.category === activeCategory);
	const activeSelectedItem = visibleItems.find((item) => selectedItems[item.type].id === item.id);
	const ActiveCategoryIcon = categoryIcons[activeCategory];

	function previewItem(item) {
		setSelectedItems((current) => ({ ...current, [item.type]: item }));
		setSaved(false);
	}

	return (
		<div className="dressme-app">
			<header className="topbar">
				<a className="brand" href="#inicio" aria-label="OnDressMe, inicio">
					<span className="brand-mark">O</span>
					<span>ONDRESSME</span>
				</a>
				<nav className="main-nav" aria-label="Navegación principal">
					<a className="nav-link is-current" href="#simulador">DressMe</a>
					<a className="nav-link" href="#avatar">Avatar</a>
					<a className="nav-link" href="#closet">Closet</a>
					<a className="nav-link" href="#perfil">Perfil</a>
				</nav>
				<button className="profile-menu" type="button">
					<span className="profile-initials">EG</span>
					<span className="profile-copy"><strong>Eva García</strong><small>Invierno profundo</small></span>
					<ArrowRight size={15} aria-hidden="true" />
				</button>
			</header>

			<main className="workspace" id="inicio">
				<div className="workspace-grid">
					<section className="simulator-panel" id="simulador" aria-labelledby="simulator-title">
						<div className="panel-heading">
							<div>
								<span className="eyebrow">Simulador</span>
								<h1 id="simulator-title">Tu maniquí</h1>
							</div>
							<button className="icon-button" type="button" title="Ampliar visor" aria-label="Ampliar visor">
								<Maximize2 size={17} />
							</button>
						</div>
						<div
							className="avatar-stage"
							id="avatar"
							style={{
								'--stage-top': stageColors[undertone].top,
								'--stage-middle': stageColors[undertone].middle,
								'--stage-floor': stageColors[undertone].floor,
							}}
						>
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
							/>
							<div className="rotate-hint"><span>↔</span> Arrastra para rotar</div>
						</div>
						<div className="look-score" id="perfil">
							<div className="score-number">94<small>/100</small></div>
							<div className="score-copy"><strong>Este look armoniza contigo</strong><span>El azul grisáceo equilibra tu contraste natural.</span></div>
							<button className={saved ? 'outline-button is-saved' : 'outline-button'} onClick={() => setSaved(!saved)} type="button">
								{saved ? <Check size={15} /> : <Check size={15} />}
								{saved ? 'Look guardado' : 'Guardar look'}
							</button>
						</div>
					</section>

					<aside className="closet-panel" id="closet" aria-labelledby="closet-title">
						<div className="closet-heading">
							<div className="closet-icon"><Shirt size={18} /></div>
							<div><span className="eyebrow">Clóset digital</span><h2 id="closet-title">Tu ropa</h2></div>
						</div>
						<div className="category-tabs" role="tablist" aria-label="Categorías de prendas">
							{categories.map((category) => (
								<button
									aria-selected={activeCategory === category}
									className={activeCategory === category ? 'category-tab is-active' : 'category-tab'}
									key={category}
									onClick={() => setActiveCategory(category)}
									role="tab"
									type="button"
								>
									{category}
								</button>
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
										<strong>{item.name}</strong>
										<small>{item.category}</small>
									</button>
								);
							})}
						</div>
						<div className="closet-actions">
							<button className="action-button" type="button"><UserRound size={15} /> Añadir prenda</button>
							<button className="action-button" type="button">Ver clóset completo <ArrowRight size={15} /></button>
						</div>
						<div className="outfit-palette">
							<div className="palette-title"><span className="eyebrow">Paleta del outfit</span><Sparkles size={14} /></div>
							<div className="selected-swatches" aria-label="Colores del outfit">
								{[selectedItems.shirt, selectedItems.pants, selectedItems.accessory].map((item) => (
									<span key={item.type} title={item.shade} style={{ backgroundColor: item.color }} />
								))}
							</div>
						</div>
					</aside>
				</div>

				<section className="recommendation-panel" aria-labelledby="recommendation-title">
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
					<button className="add-look-button" type="button" aria-label="Crear nuevo look"><Plus size={16} /></button>
				</section>
			</main>
		</div>
	);
}
