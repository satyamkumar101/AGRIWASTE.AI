# ============================================================
# AGRIWASTE AI - AGRICULTURAL WASTE KNOWLEDGE BASE
# ============================================================

WASTE_DATABASE = {

    "rice": {
        "waste_name": "Rice Straw",
        "description": (
            "Rice straw is the dry residue left after harvesting "
            "rice. It is commonly available in large quantities."
        ),
        "uses": [
            {
                "name": "Mushroom Cultivation",
                "score": 92,
                "reason": (
                    "Rice straw can be used as a substrate for "
                    "cultivating suitable mushroom varieties."
                )
            },
            {
                "name": "Composting",
                "score": 88,
                "reason": (
                    "Rice straw provides carbon-rich material "
                    "for composting when properly managed."
                )
            },
            {
                "name": "Biomass Products",
                "score": 84,
                "reason": (
                    "Dry rice straw can be processed into "
                    "briquettes, pellets and other biomass products."
                )
            },
            {
                "name": "Biofuel",
                "score": 78,
                "reason": (
                    "Rice straw can be used as lignocellulosic "
                    "biomass for energy applications."
                )
            },
            {
                "name": "Animal Feed",
                "score": 55,
                "reason": (
                    "Rice straw can be used as roughage after "
                    "appropriate treatment and formulation."
                )
            }
        ]
    },


    "wheat": {
        "waste_name": "Wheat Straw",
        "description": (
            "Wheat straw is the dry stalk residue remaining "
            "after wheat harvesting."
        ),
        "uses": [
            {
                "name": "Animal Feed",
                "score": 88,
                "reason": (
                    "Processed wheat straw can provide useful "
                    "roughage for livestock."
                )
            },
            {
                "name": "Composting",
                "score": 86,
                "reason": (
                    "Wheat straw can provide carbon-rich material "
                    "for compost production."
                )
            },
            {
                "name": "Biomass Products",
                "score": 84,
                "reason": (
                    "Dry wheat straw can be converted into "
                    "briquettes, pellets and other biomass products."
                )
            },
            {
                "name": "Mushroom Cultivation",
                "score": 72,
                "reason": (
                    "Suitable wheat straw can be used as a "
                    "cultivation substrate for mushrooms."
                )
            },
            {
                "name": "Biofuel",
                "score": 70,
                "reason": (
                    "Wheat straw is a lignocellulosic biomass "
                    "resource suitable for some energy applications."
                )
            }
        ]
    },


    "sugarcane": {
        "waste_name": "Sugarcane Bagasse & Crop Residues",
        "description": (
            "Sugarcane processing produces bagasse, while "
            "harvesting also generates leaves and tops."
        ),
        "uses": [
            {
                "name": "Biomass Products",
                "score": 95,
                "reason": (
                    "Sugarcane bagasse is widely suitable for "
                    "biomass-based products and energy generation."
                )
            },
            {
                "name": "Biofuel",
                "score": 91,
                "reason": (
                    "Sugarcane residues can serve as feedstock "
                    "for various bioenergy applications."
                )
            },
            {
                "name": "Industrial Applications",
                "score": 88,
                "reason": (
                    "Bagasse can be used in paper, packaging, "
                    "fiberboard and other industrial applications."
                )
            },
            {
                "name": "Composting",
                "score": 70,
                "reason": (
                    "Suitable sugarcane residues can be incorporated "
                    "into composting systems."
                )
            }
        ]
    },


    "maize": {
        "waste_name": "Maize Stover",
        "description": (
            "Maize stover includes stalks, leaves and other "
            "residues remaining after maize harvest."
        ),
        "uses": [
            {
                "name": "Animal Feed",
                "score": 86,
                "reason": (
                    "Suitable maize residues can be processed "
                    "and used as livestock roughage."
                )
            },
            {
                "name": "Composting",
                "score": 85,
                "reason": (
                    "Maize residues can contribute carbon-rich "
                    "material to composting."
                )
            },
            {
                "name": "Biomass Products",
                "score": 82,
                "reason": (
                    "Dry maize residues can be processed into "
                    "solid biomass products."
                )
            },
            {
                "name": "Biofuel",
                "score": 78,
                "reason": (
                    "Maize residues can be used as lignocellulosic "
                    "feedstock for bioenergy."
                )
            }
        ]
    },


    "cotton": {
        "waste_name": "Cotton Stalks & Crop Residues",
        "description": (
            "Cotton cultivation generates stalks and other "
            "plant residues after harvesting."
        ),
        "uses": [
            {
                "name": "Biomass Products",
                "score": 88,
                "reason": (
                    "Dry cotton stalks can be processed into "
                    "solid biomass products."
                )
            },
            {
                "name": "Composting",
                "score": 82,
                "reason": (
                    "Suitable cotton residues can be incorporated "
                    "into composting."
                )
            },
            {
                "name": "Biofuel",
                "score": 75,
                "reason": (
                    "Dry cotton stalks can be considered for "
                    "biomass-based energy applications."
                )
            },
            {
                "name": "Industrial Applications",
                "score": 68,
                "reason": (
                    "Fibrous agricultural residues may have "
                    "potential for selected material applications."
                )
            }
        ]
    },


    "coconut": {
        "waste_name": "Coconut Husk & Shell",
        "description": (
            "Coconut processing generates husk, shell and "
            "other fibrous residues."
        ),
        "uses": [
            {
                "name": "Biomass Products",
                "score": 94,
                "reason": (
                    "Coconut residues can be processed into "
                    "charcoal, activated carbon and biomass products."
                )
            },
            {
                "name": "Industrial Applications",
                "score": 91,
                "reason": (
                    "Coconut husk fiber and shell have applications "
                    "in fiber products and material processing."
                )
            },
            {
                "name": "Biofuel",
                "score": 86,
                "reason": (
                    "Coconut shell and other residues can serve "
                    "as biomass fuel feedstock."
                )
            },
            {
                "name": "Composting",
                "score": 62,
                "reason": (
                    "Coconut residues can be composted after "
                    "appropriate size reduction and treatment."
                )
            }
        ]
    },


    "jute": {
        "waste_name": "Jute Sticks & Jute Residues",
        "description": (
            "Jute cultivation and processing generate sticks "
            "and fibrous plant residues."
        ),
        "uses": [
            {
                "name": "Biomass Products",
                "score": 90,
                "reason": (
                    "Jute sticks can be used as biomass and "
                    "for selected value-added products."
                )
            },
            {
                "name": "Industrial Applications",
                "score": 86,
                "reason": (
                    "Jute fibers and residues have applications "
                    "in various biodegradable materials."
                )
            },
            {
                "name": "Composting",
                "score": 72,
                "reason": (
                    "Organic jute residues can contribute to "
                    "composting systems."
                )
            }
        ]
    },


    "banana": {
        "waste_name": "Banana Pseudostem & Leaves",
        "description": (
            "Banana cultivation generates pseudostems, leaves "
            "and other organic residues."
        ),
        "uses": [
            {
                "name": "Composting",
                "score": 91,
                "reason": (
                    "Banana plant residues are biodegradable "
                    "and can contribute to compost production."
                )
            },
            {
                "name": "Biomass Products",
                "score": 82,
                "reason": (
                    "Banana fibers can be recovered from "
                    "pseudostems for value-added products."
                )
            },
            {
                "name": "Animal Feed",
                "score": 65,
                "reason": (
                    "Some banana residues can be used as "
                    "livestock feed after suitable processing."
                )
            }
        ]
    },


    "soyabean": {
        "waste_name": "Soybean Stover",
        "description": (
            "Soybean stover consists of stems, leaves and "
            "other crop residues after harvest."
        ),
        "uses": [
            {
                "name": "Animal Feed",
                "score": 82,
                "reason": (
                    "Suitable soybean residues can provide "
                    "roughage after appropriate processing."
                )
            },
            {
                "name": "Composting",
                "score": 84,
                "reason": (
                    "Soybean residues can contribute organic "
                    "matter to composting."
                )
            },
            {
                "name": "Biomass Products",
                "score": 78,
                "reason": (
                    "Dry soybean residues can be considered "
                    "for biomass applications."
                )
            }
        ]
    },


    "jowar": {
        "waste_name": "Sorghum Stover",
        "description": (
            "Sorghum cultivation generates stalks, leaves "
            "and other crop residues."
        ),
        "uses": [
            {
                "name": "Animal Feed",
                "score": 86,
                "reason": (
                    "Suitable sorghum residues can be used "
                    "as livestock roughage."
                )
            },
            {
                "name": "Composting",
                "score": 82,
                "reason": (
                    "Sorghum residues can contribute carbon "
                    "and organic matter to compost."
                )
            },
            {
                "name": "Biomass Products",
                "score": 77,
                "reason": (
                    "Dry sorghum residues can be used for "
                    "selected biomass applications."
                )
            }
        ]
    },


    "Pearl_millet(bajra)": {
        "waste_name": "Pearl Millet Stover",
        "description": (
            "Pearl millet generates stalks and leaves that "
            "remain after harvesting."
        ),
        "uses": [
            {
                "name": "Animal Feed",
                "score": 85,
                "reason": (
                    "Suitable pearl millet stover can provide "
                    "roughage for livestock."
                )
            },
            {
                "name": "Composting",
                "score": 82,
                "reason": (
                    "Millet residues can contribute organic "
                    "material to composting."
                )
            },
            {
                "name": "Biomass Products",
                "score": 76,
                "reason": (
                    "Dry millet residues can be considered "
                    "for biomass applications."
                )
            }
        ]
    }
}


# ============================================================
# FALLBACK FOR OTHER CROPS
# ============================================================

DEFAULT_WASTE = {
    "waste_name": "Crop Residues",
    "description": (
        "The identified crop can generate organic residues "
        "such as stalks, leaves, husks, stems or processing waste."
    ),
    "uses": [
        {
            "name": "Composting",
            "score": 75,
            "reason": (
                "Suitable organic crop residues can be "
                "processed through composting."
            )
        },
        {
            "name": "Biomass Products",
            "score": 70,
            "reason": (
                "Dry agricultural residues may have potential "
                "for biomass applications."
            )
        }
    ]
}


# ============================================================
# PUBLIC FUNCTIONS
# ============================================================

def normalize_crop_name(crop_name):
    """
    Converts model output into a consistent lookup key.
    """

    return crop_name.strip()


def get_waste_information(crop_name):
    """
    Returns agricultural waste information for a crop.

    If the crop is not explicitly present in the knowledge base,
    a general crop-residue profile is returned.
    """

    crop_name = normalize_crop_name(crop_name)

    return WASTE_DATABASE.get(
        crop_name,
        DEFAULT_WASTE
    )


def get_recommendations(crop_name):
    """
    Returns recommendations sorted from highest to lowest score.
    """

    waste_info = get_waste_information(
        crop_name
    )

    recommendations = sorted(
        waste_info["uses"],
        key=lambda item: item["score"],
        reverse=True
    )

    return recommendations


def get_best_recommendation(crop_name):
    """
    Returns the highest-scoring recommended use.
    """

    recommendations = get_recommendations(
        crop_name
    )

    if not recommendations:
        return None

    return recommendations[0]

if __name__ == "__main__":

    crop = "rice"

    waste = get_waste_information(crop)

    print("\n" + "=" * 60)
    print("AGRIWASTE AI - RECOMMENDATION TEST")
    print("=" * 60)

    print(f"\nCrop: {crop}")

    print(
        f"Waste: {waste['waste_name']}"
    )

    print(
        f"\nDescription:\n"
        f"{waste['description']}"
    )

    print("\nRecommended Uses:")

    for index, recommendation in enumerate(
        get_recommendations(crop),
        start=1
    ):

        print(
            f"{index}. "
            f"{recommendation['name']} "
            f"({recommendation['score']}/100)"
        )

        print(
            f"   {recommendation['reason']}"
        )