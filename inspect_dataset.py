from pathlib import Path
from collections import Counter

DATASET_PATH = Path("data/raw")


def inspect_dataset():
    if not DATASET_PATH.exists():
        print("ERROR: Dataset folder was not found.")
        print(f"Expected location: {DATASET_PATH.resolve()}")
        return

    image_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp"
    }

    class_counts = Counter()

    for file in DATASET_PATH.rglob("*"):
        if file.is_file() and file.suffix.lower() in image_extensions:
            # The immediate parent folder is treated as the class name.
            class_name = file.parent.name
            class_counts[class_name] += 1

    if not class_counts:
        print("No images were found.")
        print("Check whether the dataset was extracted correctly.")
        return

    print("\n" + "=" * 60)
    print("AGRIWASTE AI - DATASET INSPECTION")
    print("=" * 60)

    print(f"\nDataset location:")
    print(DATASET_PATH.resolve())

    print(f"\nNumber of classes: {len(class_counts)}")

    total_images = sum(class_counts.values())

    print(f"Total images: {total_images}")

    print("\nImages per class:")
    print("-" * 60)

    for class_name, count in sorted(class_counts.items()):
        print(f"{class_name:<35} {count:>6}")

    print("=" * 60)


if __name__ == "__main__":
    inspect_dataset()