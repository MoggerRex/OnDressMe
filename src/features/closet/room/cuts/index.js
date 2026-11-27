import * as tshirt from './tshirt';
import * as longSleeve from './longSleeve';
import * as pants from './pants';
import * as shoes from './shoes';

// Un archivo por tipo de prenda: cada uno decide cómo cuelga (mangas, hombros, etc.) o, si es `floor`, va en el piso
export const CUTS = { tshirt, longSleeve, pants, shoes };
