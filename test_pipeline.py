from predict import predict_image
from recommendations import (
    get_waste_information,
    get_best_recommendation
)
from economic_value import estimate_value


def main():

    # --------------------------------------------------------
    # For this integration test, we use a known crop.
    # Later Streamlit will provide the crop automatically
    # from the ML prediction.
    # --------------------------------------------------------

    crop = "rice"

    quantity = 500

    # --------------------------------------------------------
    # Get waste information
    # --------------------------------------------------------

    waste = get_waste_information(
        crop
    )

    # --------------------------------------------------------
    # Get best recommendation
    # --------------------------------------------------------

    best_use = get_best_recommendation(
        crop
    )

    # --------------------------------------------------------
    # Estimate value
    # --------------------------------------------------------

    value = estimate_value(
        crop_name=crop,
        waste_name=waste["waste_name"],
        use_name=best_use["name"],
        quantity_kg=quantity
    )

    # --------------------------------------------------------
    # Display complete pipeline
    # --------------------------------------------------------

    print("\n" + "=" * 70)

    print(
        "AGRIWASTE AI - END-TO-END PIPELINE TEST"
    )

    print("=" * 70)

    print(
        f"\nDetected Crop:"
        f"\n{crop}"
    )

    print(
        f"\nAgricultural Waste:"
        f"\n{waste['waste_name']}"
    )

    print(
        f"\nBest Recommended Use:"
        f"\n{best_use['name']}"
    )

    print(
        f"\nSuitability Score:"
        f"\n{best_use['score']}/100"
    )

    print(
        f"\nQuantity:"
        f"\n{quantity} kg"
    )

    print(
        f"\nEstimated Gross Value:"
        f"\n{value['display_range']}"
    )

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()