# ============================================================
# AGRIWASTE AI - POTENTIAL UTILIZER KNOWLEDGE BASE
# ============================================================

UTILIZER_DATABASE = {
    "rice": [
        {"name": "Mushroom Growers", "type": "Mushroom Cultivation", "score": 92, "reason": "Rice straw can serve as a substrate for suitable mushroom cultivation."},
        {"name": "Compost Producers", "type": "Composting", "score": 88, "reason": "Rice straw provides carbon-rich material for managed composting."},
        {"name": "Biomass Pellet & Briquette Producers", "type": "Biomass Products", "score": 84, "reason": "Dry rice straw can be processed into solid biomass products."},
        {"name": "Bioenergy Producers", "type": "Biofuel", "score": 78, "reason": "Rice straw is lignocellulosic biomass suitable for selected energy pathways."},
        {"name": "Livestock Feed Processors", "type": "Animal Feed", "score": 55, "reason": "Treated rice straw can be considered as roughage in suitable feed formulations."},
    ],
    "wheat": [
        {"name": "Livestock Feed Processors", "type": "Animal Feed", "score": 88, "reason": "Processed wheat straw can provide roughage for livestock."},
        {"name": "Compost Producers", "type": "Composting", "score": 86, "reason": "Wheat straw can provide carbon-rich material for compost production."},
        {"name": "Biomass Pellet & Briquette Producers", "type": "Biomass Products", "score": 84, "reason": "Dry wheat straw can be converted into solid biomass products."},
        {"name": "Mushroom Growers", "type": "Mushroom Cultivation", "score": 72, "reason": "Suitable wheat straw can be used as a mushroom cultivation substrate."},
        {"name": "Bioenergy Producers", "type": "Biofuel", "score": 70, "reason": "Wheat straw can be considered as lignocellulosic feedstock for energy applications."},
    ],
    "sugarcane": [
        {"name": "Biomass Product Manufacturers", "type": "Biomass Products", "score": 95, "reason": "Sugarcane bagasse is well suited to biomass-based products and energy generation."},
        {"name": "Bioenergy Producers", "type": "Biofuel", "score": 91, "reason": "Sugarcane residues can serve as feedstock for bioenergy applications."},
        {"name": "Paper & Packaging Manufacturers", "type": "Industrial Applications", "score": 88, "reason": "Bagasse has potential in paper, packaging and fiberboard applications."},
        {"name": "Compost Producers", "type": "Composting", "score": 70, "reason": "Suitable sugarcane residues can be incorporated into composting systems."},
    ],
    "maize": [
        {"name": "Livestock Feed Processors", "type": "Animal Feed", "score": 86, "reason": "Suitable maize residues can be processed into livestock roughage."},
        {"name": "Compost Producers", "type": "Composting", "score": 85, "reason": "Maize residues contribute carbon-rich material to composting."},
        {"name": "Biomass Pellet & Briquette Producers", "type": "Biomass Products", "score": 82, "reason": "Dry maize residues can be processed into solid biomass products."},
        {"name": "Bioenergy Producers", "type": "Biofuel", "score": 78, "reason": "Maize residues can be used as lignocellulosic feedstock for bioenergy."},
    ],
    "cotton": [
        {"name": "Biomass Product Manufacturers", "type": "Biomass Products", "score": 88, "reason": "Dry cotton stalks can be processed into solid biomass products."},
        {"name": "Compost Producers", "type": "Composting", "score": 82, "reason": "Suitable cotton residues can be incorporated into composting."},
        {"name": "Bioenergy Producers", "type": "Biofuel", "score": 75, "reason": "Dry cotton stalks can support selected biomass-based energy applications."},
        {"name": "Material & Fiber Processors", "type": "Industrial Applications", "score": 68, "reason": "Fibrous residues may have potential for selected material applications."},
    ],
    "coconut": [
        {"name": "Biomass & Charcoal Producers", "type": "Biomass Products", "score": 94, "reason": "Coconut residues can be processed into charcoal, activated carbon and biomass products."},
        {"name": "Fiber Product Manufacturers", "type": "Industrial Applications", "score": 91, "reason": "Coconut husk fiber and shell can support fiber and material processing."},
        {"name": "Bioenergy Producers", "type": "Biofuel", "score": 86, "reason": "Coconut shell and other residues can serve as biomass fuel feedstock."},
        {"name": "Compost Producers", "type": "Composting", "score": 62, "reason": "Coconut residues can be composted after suitable size reduction and treatment."},
    ],
    "jute": [
        {"name": "Biomass Product Manufacturers", "type": "Biomass Products", "score": 90, "reason": "Jute sticks can be used as biomass and for selected value-added products."},
        {"name": "Biodegradable Material Manufacturers", "type": "Industrial Applications", "score": 86, "reason": "Jute fibers and residues have applications in biodegradable materials."},
        {"name": "Compost Producers", "type": "Composting", "score": 72, "reason": "Organic jute residues can contribute to composting systems."},
    ],
    "banana": [
        {"name": "Compost Producers", "type": "Composting", "score": 91, "reason": "Banana plant residues are biodegradable and can contribute to compost production."},
        {"name": "Natural Fiber Product Manufacturers", "type": "Biomass Products", "score": 82, "reason": "Banana fibers can be recovered from pseudostems for value-added products."},
        {"name": "Livestock Feed Processors", "type": "Animal Feed", "score": 65, "reason": "Some banana residues can be used as livestock feed after suitable processing."},
    ],
    "soyabean": [
        {"name": "Livestock Feed Processors", "type": "Animal Feed", "score": 82, "reason": "Suitable soybean residues can provide roughage after appropriate processing."},
        {"name": "Compost Producers", "type": "Composting", "score": 84, "reason": "Soybean residues can contribute organic matter to composting."},
        {"name": "Biomass Product Manufacturers", "type": "Biomass Products", "score": 78, "reason": "Dry soybean residues can be considered for biomass applications."},
    ],
    "jowar": [
        {"name": "Livestock Feed Processors", "type": "Animal Feed", "score": 86, "reason": "Suitable sorghum residues can be used as livestock roughage."},
        {"name": "Compost Producers", "type": "Composting", "score": 82, "reason": "Sorghum residues can contribute carbon and organic matter to compost."},
        {"name": "Biomass Product Manufacturers", "type": "Biomass Products", "score": 77, "reason": "Dry sorghum residues can support selected biomass applications."},
    ],
    "Pearl_millet(bajra)": [
        {"name": "Livestock Feed Processors", "type": "Animal Feed", "score": 85, "reason": "Suitable pearl millet stover can provide roughage for livestock."},
        {"name": "Compost Producers", "type": "Composting", "score": 82, "reason": "Millet residues can contribute organic material to composting."},
        {"name": "Biomass Product Manufacturers", "type": "Biomass Products", "score": 76, "reason": "Dry millet residues can be considered for biomass applications."},
    ],
}

DEFAULT_UTILIZERS = [
    {"name": "Compost Producers", "type": "Composting", "score": 75, "reason": "Suitable organic crop residues can be processed through composting."},
    {"name": "Biomass Product Manufacturers", "type": "Biomass Products", "score": 70, "reason": "Dry agricultural residues may have potential for biomass applications."},
]


def get_utilizers(crop_name):
    """Return potential utilization partners sorted by match score."""
    utilizers = UTILIZER_DATABASE.get(crop_name, DEFAULT_UTILIZERS)
    return sorted(utilizers, key=lambda item: item["score"], reverse=True)


def get_top_utilizer(crop_name):
    """Return the highest-scoring potential utilizer."""
    utilizers = get_utilizers(crop_name)
    return utilizers[0] if utilizers else None


if __name__ == "__main__":
    for item in get_utilizers("rice"):
        print(f"{item['name']} - {item['score']}/100")
