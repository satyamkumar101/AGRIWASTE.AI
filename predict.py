from pathlib import Path
import json
import sys

import numpy as np
import tensorflow as tf
from tensorflow import keras


# ============================================================
# CONFIGURATION
# ============================================================

MODEL_PATH = Path(
    "models/agriwaste_classifier.keras"
)

CLASS_NAMES_PATH = Path(
    "models/class_names.json"
)

IMG_SIZE = (
    224,
    224
)


# ============================================================
# LOAD MODEL
# ============================================================

def load_model():

    if not MODEL_PATH.exists():

        raise FileNotFoundError(
            f"Model not found:\n"
            f"{MODEL_PATH.resolve()}\n\n"
            f"Run train_model.py first."
        )

    return keras.models.load_model(
        MODEL_PATH
    )


# ============================================================
# LOAD CLASS NAMES
# ============================================================

def load_class_names():

    if not CLASS_NAMES_PATH.exists():

        raise FileNotFoundError(
            f"Class names file not found:\n"
            f"{CLASS_NAMES_PATH.resolve()}"
        )

    with open(
        CLASS_NAMES_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# LOAD IMAGE
# ============================================================

def load_image(image_path):

    image_path = Path(image_path)

    if not image_path.exists():

        raise FileNotFoundError(
            f"Image not found:\n"
            f"{image_path.resolve()}"
        )

    image = tf.keras.utils.load_img(
        image_path,
        target_size=IMG_SIZE
    )

    image_array = tf.keras.utils.img_to_array(
        image
    )

    # Add batch dimension:
    # (224, 224, 3)
    # becomes
    # (1, 224, 224, 3)
    image_array = np.expand_dims(
        image_array,
        axis=0
    )

    return image_array


# ============================================================
# PREDICT
# ============================================================

def predict_image(
    image_path,
    top_k=3
):

    model = load_model()

    class_names = load_class_names()

    image = load_image(
        image_path
    )

    predictions = model.predict(
        image,
        verbose=0
    )[0]

    # Get indexes of highest probabilities
    top_indexes = np.argsort(
        predictions
    )[::-1][:top_k]

    results = []

    for index in top_indexes:

        results.append(
            {
                "class": class_names[index],
                "confidence": float(
                    predictions[index]
                )
            }
        )

    return results


# ============================================================
# COMMAND-LINE INTERFACE
# ============================================================

def main():

    if len(sys.argv) < 2:

        print(
            "\nUsage:"
        )

        print(
            "python predict.py "
            "<image_path>"
        )

        print(
            "\nExample:"
        )

        print(
            "python predict.py "
            "data/processed/test/rice/image.jpg"
        )

        return

    image_path = sys.argv[1]

    print("\n" + "=" * 60)
    print("AGRIWASTE AI - IMAGE PREDICTION")
    print("=" * 60)

    print(
        f"\nImage:"
        f"\n{Path(image_path).resolve()}"
    )

    try:

        results = predict_image(
            image_path,
            top_k=3
        )

        print(
            "\nTop Predictions:"
        )

        print("-" * 60)

        for rank, result in enumerate(
            results,
            start=1
        ):

            class_name = result["class"]

            confidence = (
                result["confidence"] * 100
            )

            print(
                f"{rank}. "
                f"{class_name:<30} "
                f"{confidence:.2f}%"
            )

        print("-" * 60)

        best_result = results[0]

        print(
            f"\nPredicted Crop: "
            f"{best_result['class']}"
        )

        print(
            f"Confidence: "
            f"{best_result['confidence'] * 100:.2f}%"
        )

    except Exception as error:

        print(
            "\nERROR:"
        )

        print(error)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()