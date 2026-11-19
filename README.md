# AgriWaste AI

### AI-assisted agricultural residue identification, utilization, and farmer–buyer marketplace prototype

AgriWaste AI is a Streamlit-based prototype that helps farmers turn agricultural residues into potentially useful resources.

The platform combines **computer vision, residue-utilization guidance, economic-value estimation, and a farmer–buyer marketplace workflow** in one application.

Instead of stopping at:

> “What crop is this?”

the prototype extends the workflow to:

> **Identify → Understand → Find uses → Estimate value → List residue → Match buyers → Prepare → Respond → Negotiate → Handover**

---

## Project Overview

Agricultural residues are often burned, discarded, or underutilized because farmers may not have accessible information about:

- What the residue can be used for
- Its potential economic value
- Who may want to use it
- What form or quality a buyer requires
- How to prepare the residue for a specific requirement

AgriWaste AI explores a digital solution to this problem by connecting **AI-assisted residue understanding** with a structured marketplace workflow.

---

## Core Features

### 1. AI-based Crop Identification

Farmers can upload a crop image and receive:

- Predicted crop
- Prediction confidence
- Top model predictions
- Human correction option

The prototype uses an **EfficientNetB0-based TensorFlow/Keras classifier**.

Human correction is kept separate from the original AI prediction so that the system does not falsely represent a farmer correction as a model prediction.

---

### 2. Agricultural Residue Analysis

After identifying the crop, the system maps it to relevant agricultural residue information and provides practical utilization pathways.

Potential pathways include:

- Composting
- Mushroom cultivation
- Animal-feed-related applications where appropriate
- Bioenergy / biofuel
- Biomass products
- Industrial applications

Recommendations are intended as prototype decision support rather than guaranteed technical or commercial advice.

---

### 3. Prototype Economic Value Estimation

Farmers can provide an estimated residue quantity and utilization pathway to obtain a configured value range.

The estimate is a **prototype calculation**, not a live market quotation or guaranteed farmer income.

Actual value can vary with:

- Residue quality
- Moisture
- Quantity
- Location
- Transportation cost
- Processing requirements
- Local demand
- Buyer requirements

---

### 4. Farmer Residue Marketplace

Farmers can create residue lots containing information such as:

- Crop
- Residue type
- Quantity
- Form: raw / dry / processed
- Moisture
- Processing information
- Location
- Pickup availability
- Notes

Each lot can then participate in the buyer workflow.

---

### 5. Buyer Requirements / RFQs

Buyers can publish structured requirements including:

- Required crop/residue
- Accepted forms
- Minimum quantity
- Maximum moisture
- Processing requirements
- Packaging requirements
- Pickup requirements
- Location
- Additional notes

This turns buyer needs into structured data that can be compared with farmer lots.

---

### 6. Smart Buyer–Farmer Matching

The prototype compares an active farmer lot with buyer RFQs.

Matches are classified as:

- **Ready to respond**
- **Preparation needed**
- **Not currently compatible**

The system considers factors such as:

- Crop
- Residue
- Form
- Quantity
- Moisture
- Processing
- Pickup requirements

Location is treated as contextual information rather than a hard geographic-distance match in this prototype because the current system does not use coordinate-based logistics matching.

---

### 7. Preparation Guide

When a buyer's requirement is not yet fully aligned with a farmer's lot, the preparation workflow identifies outstanding requirements.

The goal is to answer:

> **“What do I need to do before I respond to this buyer?”**

The guide uses the buyer's stated requirements rather than inventing universal requirements.

---

### 8. Farmer Response Assistant

For compatible or preparation-needed opportunities, the system can create an editable response draft using the actual lot and buyer requirements.

The draft is **reviewable before submission** and does not automatically send a message.

---

### 9. Negotiation and Transaction Workflow

The marketplace supports an end-to-end transaction flow:

```text
Buyer RFQ
   ↓
Farmer Response
   ↓
Negotiation
   ↓
Mutual Confirmation
   ↓
Pickup Scheduling
   ↓
Handover
   ↓
Buyer Confirmation
   ↓
Completed Transaction
```

The prototype records important transaction events and supports a handover record including actual quantity and measured moisture where available.

---

### 10. Quality and Photo Evidence

Farmers can provide lot-level quality information and photographic evidence.

The system distinguishes:

**Farmer-reported information**

from

**Platform-independent verification**

The prototype does not claim that a farmer-entered quality observation or photograph independently proves quality, ownership, weight, or authenticity.

---

### 11. Lot Traceability

Residue lots have an identifiable record through the marketplace workflow.

Important events can be associated with the lot, supporting a traceable history from listing through transaction completion.

---

### 12. Human-in-the-loop AI Feedback

If the AI prediction is incorrect, the user can provide a correction.

The prototype keeps:

```text
AI prediction
AI confidence
Human correction
Working identification
```

as distinct pieces of information.

This creates a foundation for future model-improvement workflows without automatically retraining the model from unverified user input.

---

### 13. Multilingual Farmer Interface

The farmer-facing interface supports:

- English
- Hindi
- Odia
- Bengali

The underlying technical data and database values remain language-independent.

---

### 14. Model Evaluation

The repository includes model evaluation artifacts.

The currently included classification report contains results for **30 classes and 152 evaluated samples**:

| Metric | Reported value |
|---|---:|
| Accuracy | 79% |
| Macro Precision | 83% |
| Macro Recall | 78% |
| Macro F1 | 77% |

These figures describe the supplied evaluation artifact. They should not be interpreted as a guarantee of performance on new real-world images.

The repository also includes:

- Classification report
- Confusion matrix
- Training accuracy curve
- Training loss curve
- Class-name mapping

---

## System Architecture

```text
                         AGRIWASTE AI
                              │
             ┌────────────────┴────────────────┐
             │                                 │
        AI / ANALYSIS                     MARKETPLACE
             │                                 │
      Image Upload                         Farmer Lot
             ↓                                 ↓
      AI Classification                    Buyer RFQ
             ↓                                 ↓
    Confidence + Correction            Smart Matching
             │                                 ↓
             │                         Preparation Guide
             │                                 ↓
             │                         Response Assistant
             │                                 ↓
             └──────────────────────→ Negotiation
                                              ↓
                                        Confirmation
                                              ↓
                                      Pickup / Handover
                                              ↓
                                          Completed
                                              │
                                  ┌───────────┴───────────┐
                                  │                       │
                            Quality Data             Photo Evidence
                                  │                       │
                                  └───────────┬───────────┘
                                              ↓
                                       Lot Traceability
```

---

## Screenshots

### Farmer Dashboard

The dashboard brings the main farmer workflows together, including residue analysis, selling residue, finding buyers, active lots, inventory, and completed sales.

![Farmer Dashboard](assets/screenshots/farmer-dashboard.png)

### Smart Buyer Matching

The marketplace compares a farmer's lot with buyer requirements and identifies what already matches and what still needs attention before responding.

![Smart Buyer Matching](assets/screenshots/buyer-matching.png)

### Marketplace Transaction Center

The transaction workflow connects negotiation, agreed terms, confirmation, pickup, handover, completion, and the transaction receipt.

![Marketplace Transaction Center](assets/screenshots/transaction.png)

### About Project

The About Project page provides a visual overview of the problem, solution, capabilities, workflow, architecture, quality principles, and prototype validation scope.

![About Project](assets/screenshots/about-project.png)

## Technology Stack

| Area | Technology |
|---|---|
| UI | Streamlit |
| Language | Python |
| ML | TensorFlow / Keras |
| CNN architecture | EfficientNetB0 |
| Data processing | Pandas, NumPy |
| ML evaluation | scikit-learn |
| Image processing | Pillow |
| Visualization | Plotly, Matplotlib |
| Local persistence | SQLite |
| Version control | Git / GitHub |

---

## Repository Structure

```text
AgriWaste-AI/
│
├── app.py
├── auth.py
├── marketplace.py
├── marketplace_db.py
├── predict.py
├── recommendations.py
├── economic_value.py
├── processing_guides.py
├── utilizers.py
│
├── models/
│   ├── agriwaste_classifier.keras
│   ├── class_names.json
│   ├── classification_report.txt
│   ├── confusion_matrix.png
│   ├── training_accuracy.png
│   └── training_loss.png
│
├── assets/
│   └── project visual assets
│
├── tests/
│   └── prototype_preflight_v26.py
│
├── ARCHITECTURE.md
├── PROJECT_ROADMAP.md
├── README.md
├── requirements.txt
└── .gitignore
```

### Dataset

The agricultural image dataset used for model development is **not included in this repository**.

The local project uses the `data/` directory for training/validation/test data, but that directory is excluded from GitHub to keep the repository lightweight and avoid redistributing dataset content without checking its applicable license/terms.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/ADVIN-dev/AgriWaste-AI.git
cd AgriWaste-AI
```

### 2. Create a virtual environment

#### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
streamlit run app.py
```

The application should open in your browser.

---

## Important Notes

### Prototype status

AgriWaste AI is a **working academic/proof-of-concept prototype**, not a production agricultural marketplace.

The following areas would require additional engineering before real-world deployment:

- Production-grade authentication and authorization
- Secure secret management
- Managed database infrastructure
- Independent quality verification
- Real payment processing
- Logistics integration
- Location-aware distance calculations
- Verified organizations and buyer identities
- Production monitoring and backups
- Security testing
- Legal/privacy review

### AI limitations

The classifier's reported evaluation metrics are based on the supplied evaluation artifact. Real-world performance can differ because of:

- Image quality
- Lighting
- Camera angle
- Backgrounds
- Crop variety
- Geographic variation
- Class imbalance
- Images outside the training distribution

The application therefore provides confidence information and allows human correction rather than treating every prediction as certain.

### Marketplace limitations

Buyer matching in the prototype is requirement-based. It is not a live market-demand prediction system and does not guarantee that a buyer will purchase a listed residue.

Economic values are configured prototype estimates and are not guaranteed market prices.

---

## Future Scope

Potential production-stage improvements include:

1. Residue-specific image classification.
2. Better-calibrated AI confidence and image-quality checks.
3. Larger and more diverse datasets.
4. Verified farmer and buyer organizations.
5. Location-aware matching and transportation estimation.
6. Live market-price integration.
7. Payment integration.
8. Logistics and pickup-service integration.
9. Independent quality verification.
10. Mobile-first and voice-assisted farmer workflows.
11. Production PostgreSQL/API architecture.
12. Automated testing, monitoring, CI/CD and secure deployment.
13. Human-feedback pipelines for controlled model improvement.

---

## Project Roadmap

The repository also includes:

- `ARCHITECTURE.md` — technical architecture
- `PROJECT_ROADMAP.md` — development roadmap and future production phases

---

## Academic / Project Context

AgriWaste AI demonstrates how:

**Computer Vision + Machine Learning + Decision Support + Marketplace Workflow**

can be combined into a single platform for agricultural-residue management.

The project focuses on moving agricultural residue from a simple waste-disposal problem toward a more structured **resource identification, utilization, and exchange workflow**.

---

## License and Dataset Attribution

Before redistributing this project or deploying it commercially, review the licenses and attribution requirements of:

- The agricultural image dataset
- TensorFlow/Keras and other dependencies
- Any third-party visual assets
- Any external data used by the project

The repository's source code license should be selected according to the project's ownership and academic requirements.

---

## Author

**Aditya Raj**

AgriWaste AI — Academic Prototype

GitHub: https://github.com/ADVIN-dev/AgriWaste-AI
