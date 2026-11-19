from pathlib import Path
import json
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf

from tensorflow import keras
from tensorflow.keras import layers
from sklearn.metrics import classification_report, confusion_matrix


# ============================================================
# CONFIGURATION
# ============================================================

DATASET_DIR = Path("data/processed")
MODEL_DIR = Path("models")

TRAIN_DIR = DATASET_DIR / "train"
VALIDATION_DIR = DATASET_DIR / "validation"
TEST_DIR = DATASET_DIR / "test"

MODEL_PATH = MODEL_DIR / "agriwaste_classifier.keras"
CLASS_NAMES_PATH = MODEL_DIR / "class_names.json"

IMG_SIZE = (224, 224)
BATCH_SIZE = 16

EPOCHS = 15

RANDOM_SEED = 42


# ============================================================
# CREATE MODEL DIRECTORY
# ============================================================

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CHECK DATASET
# ============================================================

def check_dataset():

    required_directories = [
        TRAIN_DIR,
        VALIDATION_DIR,
        TEST_DIR
    ]

    for directory in required_directories:

        if not directory.exists():

            raise FileNotFoundError(
                f"Dataset directory not found:\n"
                f"{directory.resolve()}\n\n"
                f"Run prepare_dataset.py first."
            )


# ============================================================
# LOAD DATASETS
# ============================================================

def load_datasets():

    print("\nLoading training dataset...")

    train_dataset = tf.keras.utils.image_dataset_from_directory(
        TRAIN_DIR,
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=True,
        seed=RANDOM_SEED
    )

    print("\nLoading validation dataset...")

    validation_dataset = tf.keras.utils.image_dataset_from_directory(
        VALIDATION_DIR,
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=False
    )

    print("\nLoading test dataset...")

    test_dataset = tf.keras.utils.image_dataset_from_directory(
        TEST_DIR,
        image_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=False
    )

    class_names = train_dataset.class_names

    return (
        train_dataset,
        validation_dataset,
        test_dataset,
        class_names
    )


# ============================================================
# DATA PIPELINE OPTIMIZATION
# ============================================================

def optimize_datasets(
    train_dataset,
    validation_dataset,
    test_dataset
):

    AUTOTUNE = tf.data.AUTOTUNE

    train_dataset = train_dataset.prefetch(
        buffer_size=AUTOTUNE
    )

    validation_dataset = validation_dataset.prefetch(
        buffer_size=AUTOTUNE
    )

    test_dataset = test_dataset.prefetch(
        buffer_size=AUTOTUNE
    )

    return (
        train_dataset,
        validation_dataset,
        test_dataset
    )


# ============================================================
# DATA AUGMENTATION
# ============================================================

def create_data_augmentation():

    return keras.Sequential(
        [
            layers.RandomFlip(
                "horizontal"
            ),

            layers.RandomRotation(
                0.10
            ),

            layers.RandomZoom(
                0.10
            ),

            layers.RandomContrast(
                0.10
            )
        ],
        name="data_augmentation"
    )


# ============================================================
# BUILD MODEL
# ============================================================

def build_model(number_of_classes):

    data_augmentation = create_data_augmentation()

    # --------------------------------------------------------
    # Pretrained EfficientNetB0
    # --------------------------------------------------------

    base_model = keras.applications.EfficientNetB0(
        include_top=False,
        weights="imagenet",
        input_shape=(
            IMG_SIZE[0],
            IMG_SIZE[1],
            3
        )
    )

    # Freeze pretrained layers during first training stage
    base_model.trainable = False

    # --------------------------------------------------------
    # Input
    # --------------------------------------------------------

    inputs = keras.Input(
        shape=(
            IMG_SIZE[0],
            IMG_SIZE[1],
            3
        ),
        name="image"
    )

    # --------------------------------------------------------
    # Augmentation
    # --------------------------------------------------------

    x = data_augmentation(inputs)

    # --------------------------------------------------------
    # EfficientNet feature extraction
    # --------------------------------------------------------

    x = base_model(
        x,
        training=False
    )

    # --------------------------------------------------------
    # Classification head
    # --------------------------------------------------------

    x = layers.GlobalAveragePooling2D()(x)

    x = layers.Dropout(
        0.30
    )(x)

    outputs = layers.Dense(
        number_of_classes,
        activation="softmax",
        name="predictions"
    )(x)

    model = keras.Model(
        inputs,
        outputs,
        name="AgriWaste_EfficientNetB0"
    )

    # --------------------------------------------------------
    # Compile
    # --------------------------------------------------------

    model.compile(
        optimizer=keras.optimizers.Adam(
            learning_rate=0.001
        ),
        loss="sparse_categorical_crossentropy",
        metrics=[
            "accuracy"
        ]
    )

    return model


# ============================================================
# TRAIN MODEL
# ============================================================

def train_model(
    model,
    train_dataset,
    validation_dataset
):

    callbacks = [

        keras.callbacks.ModelCheckpoint(
            filepath=str(MODEL_PATH),
            monitor="val_accuracy",
            save_best_only=True,
            mode="max",
            verbose=1
        ),

        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=4,
            restore_best_weights=True,
            verbose=1
        ),

        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.3,
            patience=2,
            min_lr=1e-6,
            verbose=1
        )
    ]

    print("\n" + "=" * 70)
    print("STARTING MODEL TRAINING")
    print("=" * 70)

    history = model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=EPOCHS,
        callbacks=callbacks
    )

    return history


# ============================================================
# PLOT TRAINING HISTORY
# ============================================================

def plot_training_history(history):

    history_data = history.history

    # --------------------------------------------------------
    # Accuracy
    # --------------------------------------------------------

    plt.figure(figsize=(8, 5))

    plt.plot(
        history_data["accuracy"],
        label="Training Accuracy"
    )

    plt.plot(
        history_data["val_accuracy"],
        label="Validation Accuracy"
    )

    plt.title(
        "AgriWaste AI - Training Accuracy"
    )

    plt.xlabel("Epoch")

    plt.ylabel("Accuracy")

    plt.legend()

    plt.grid(True)

    plt.tight_layout()

    plt.savefig(
        "models/training_accuracy.png",
        dpi=150
    )

    plt.close()

    # --------------------------------------------------------
    # Loss
    # --------------------------------------------------------

    plt.figure(figsize=(8, 5))

    plt.plot(
        history_data["loss"],
        label="Training Loss"
    )

    plt.plot(
        history_data["val_loss"],
        label="Validation Loss"
    )

    plt.title(
        "AgriWaste AI - Training Loss"
    )

    plt.xlabel("Epoch")

    plt.ylabel("Loss")

    plt.legend()

    plt.grid(True)

    plt.tight_layout()

    plt.savefig(
        "models/training_loss.png",
        dpi=150
    )

    plt.close()

    print("\nTraining graphs saved:")
    print("models/training_accuracy.png")
    print("models/training_loss.png")


# ============================================================
# EVALUATE MODEL
# ============================================================

def evaluate_model(
    model,
    test_dataset,
    class_names
):

    print("\n" + "=" * 70)
    print("MODEL EVALUATION")
    print("=" * 70)

    test_loss, test_accuracy = model.evaluate(
        test_dataset,
        verbose=1
    )

    print(
        f"\nTest Loss: {test_loss:.4f}"
    )

    print(
        f"Test Accuracy: {test_accuracy:.4f}"
    )

    print(
        f"Test Accuracy: {test_accuracy * 100:.2f}%"
    )

    # --------------------------------------------------------
    # Generate predictions
    # --------------------------------------------------------

    y_true = []
    y_pred = []

    for images, labels in test_dataset:

        predictions = model.predict(
            images,
            verbose=0
        )

        predicted_classes = np.argmax(
            predictions,
            axis=1
        )

        y_true.extend(
            labels.numpy()
        )

        y_pred.extend(
            predicted_classes
        )

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)

    # --------------------------------------------------------
    # Classification report
    # --------------------------------------------------------

    print("\nClassification Report:\n")

    report = classification_report(
        y_true,
        y_pred,
        target_names=class_names,
        zero_division=0
    )

    print(report)

    with open(
        "models/classification_report.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(report)

    # --------------------------------------------------------
    # Confusion matrix
    # --------------------------------------------------------

    matrix = confusion_matrix(
        y_true,
        y_pred
    )

    plt.figure(
        figsize=(18, 16)
    )

    plt.imshow(
        matrix,
        interpolation="nearest"
    )

    plt.title(
        "AgriWaste AI - Confusion Matrix"
    )

    plt.colorbar()

    tick_marks = np.arange(
        len(class_names)
    )

    plt.xticks(
        tick_marks,
        class_names,
        rotation=90,
        fontsize=8
    )

    plt.yticks(
        tick_marks,
        class_names,
        fontsize=8
    )

    plt.xlabel(
        "Predicted Class"
    )

    plt.ylabel(
        "Actual Class"
    )

    plt.tight_layout()

    plt.savefig(
        "models/confusion_matrix.png",
        dpi=150,
        bbox_inches="tight"
    )

    plt.close()

    print(
        "\nConfusion matrix saved:"
    )

    print(
        "models/confusion_matrix.png"
    )

    return test_accuracy


# ============================================================
# SAVE CLASS NAMES
# ============================================================

def save_class_names(class_names):

    with open(
        CLASS_NAMES_PATH,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            class_names,
            file,
            indent=4
        )

    print(
        f"\nClass names saved to:"
        f"\n{CLASS_NAMES_PATH}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n" + "=" * 70)
    print("AGRIWASTE AI - IMAGE CLASSIFIER")
    print("=" * 70)

    # Check dataset
    check_dataset()

    # Load datasets
    (
        train_dataset,
        validation_dataset,
        test_dataset,
        class_names
    ) = load_datasets()

    print(
        f"\nNumber of classes: "
        f"{len(class_names)}"
    )

    print("\nClasses:")

    for index, class_name in enumerate(
        class_names
    ):

        print(
            f"{index:2d}. {class_name}"
        )

    # Optimize pipeline
    (
        train_dataset,
        validation_dataset,
        test_dataset
    ) = optimize_datasets(
        train_dataset,
        validation_dataset,
        test_dataset
    )

    # Build model
    print("\nBuilding EfficientNetB0 model...")

    model = build_model(
        number_of_classes=len(class_names)
    )

    print("\nModel summary:\n")

    model.summary()

    # Train
    history = train_model(
        model,
        train_dataset,
        validation_dataset
    )

    # Plot training history
    plot_training_history(
        history
    )

    # Load best saved model
    if MODEL_PATH.exists():

        print(
            "\nLoading best saved model..."
        )

        model = keras.models.load_model(
            MODEL_PATH
        )

    # Evaluate
    test_accuracy = evaluate_model(
        model,
        test_dataset,
        class_names
    )

    # Save class names
    save_class_names(
        class_names
    )

    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)

    print(
        f"\nFinal test accuracy: "
        f"{test_accuracy * 100:.2f}%"
    )

    print(
        f"\nModel:"
        f"\n{MODEL_PATH.resolve()}"
    )

    print(
        "\nNext step:"
        "\nBuild the prediction system."
    )


if __name__ == "__main__":
    main()