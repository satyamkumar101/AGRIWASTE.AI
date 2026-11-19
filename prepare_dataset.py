from pathlib import Path
import shutil
import random
from collections import defaultdict


# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_DIR = Path("data/raw")
OUTPUT_DIR = Path("data/processed")

TRAIN_RATIO = 0.70
VALIDATION_RATIO = 0.15
TEST_RATIO = 0.15

RANDOM_SEED = 42

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp"
}


# ============================================================
# VALIDATION
# ============================================================

if abs((TRAIN_RATIO + VALIDATION_RATIO + TEST_RATIO) - 1.0) > 0.001:
    raise ValueError("Train, validation and test ratios must add up to 1.0.")


# ============================================================
# FIND IMAGE FILES
# ============================================================

def find_images():
    """
    Finds images recursively inside data/raw.

    The immediate parent folder of each image is treated
    as the class name.
    """

    class_images = defaultdict(list)

    for file_path in SOURCE_DIR.rglob("*"):

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        class_name = file_path.parent.name

        class_images[class_name].append(file_path)

    return class_images


# ============================================================
# CREATE DIRECTORIES
# ============================================================

def create_output_directories(class_names):

    for split in ["train", "validation", "test"]:

        for class_name in class_names:

            directory = OUTPUT_DIR / split / class_name

            directory.mkdir(
                parents=True,
                exist_ok=True
            )


# ============================================================
# COPY DATASET
# ============================================================

def split_dataset(class_images):

    random.seed(RANDOM_SEED)

    total_copied = 0

    for class_name, images in sorted(class_images.items()):

        # Shuffle without changing the original list
        shuffled_images = images.copy()
        random.shuffle(shuffled_images)

        total_images = len(shuffled_images)

        train_count = int(total_images * TRAIN_RATIO)

        validation_count = int(
            total_images * VALIDATION_RATIO
        )

        train_images = shuffled_images[:train_count]

        validation_images = shuffled_images[
            train_count:
            train_count + validation_count
        ]

        test_images = shuffled_images[
            train_count + validation_count:
        ]

        splits = {
            "train": train_images,
            "validation": validation_images,
            "test": test_images
        }

        print(
            f"{class_name:<30} "
            f"Train: {len(train_images):>3} | "
            f"Validation: {len(validation_images):>3} | "
            f"Test: {len(test_images):>3}"
        )

        for split_name, split_images in splits.items():

            destination_dir = (
                OUTPUT_DIR /
                split_name /
                class_name
            )

            for image_path in split_images:

                destination = (
                    destination_dir /
                    image_path.name
                )

                shutil.copy2(
                    image_path,
                    destination
                )

                total_copied += 1

    return total_copied


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n" + "=" * 70)
    print("AGRIWASTE AI - DATASET PREPARATION")
    print("=" * 70)

    if not SOURCE_DIR.exists():

        print("\nERROR:")
        print(f"Dataset directory not found: {SOURCE_DIR.resolve()}")

        return

    # Prevent accidentally mixing old and new files
    if OUTPUT_DIR.exists():

        print("\nRemoving previous processed dataset...")

        shutil.rmtree(OUTPUT_DIR)

    print("\nScanning dataset...")

    class_images = find_images()

    if not class_images:

        print("\nERROR: No images were found.")

        return

    print(f"\nClasses found: {len(class_images)}")

    total_images = sum(
        len(images)
        for images in class_images.values()
    )

    print(f"Total images: {total_images}")

    print("\nCreating train/validation/test split...\n")

    create_output_directories(
        class_images.keys()
    )

    total_copied = split_dataset(
        class_images
    )

    print("\n" + "=" * 70)

    print("DATASET PREPARATION COMPLETE")

    print("=" * 70)

    print(f"\nImages copied: {total_copied}")

    print(
        f"\nProcessed dataset location:"
        f"\n{OUTPUT_DIR.resolve()}"
    )

    print("\nSplit ratios:")

    print(f"Training:    {TRAIN_RATIO * 100:.0f}%")
    print(f"Validation:  {VALIDATION_RATIO * 100:.0f}%")
    print(f"Testing:     {TEST_RATIO * 100:.0f}%")

    print("\nYou can now proceed to model training.")


if __name__ == "__main__":
    main()