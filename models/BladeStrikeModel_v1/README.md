# Blade strike model pipeline: v1

Two-stage prediction pipeline: the binary model detects strike vs no-contact; the multiclass model assigns a pump region to each predicted strike.

- **Trained:** 2026-08-24T17:08:25 with StrikeWorks v0.1.0
- **Training dataset:** C:\python_projects\StrikeWorks\input_data\Pumpflow_2024_and_2026_datatset_.csv
- **Channels:** higacc_x_g, higacc_y_g, higacc_z_g, inacc_x_ms, inacc_y_ms, inacc_z_ms, rot_x_degs, rot_y_degs, rot_z_degs, pressure_kpa
- **Sequence length:** 401 samples

## Binary model (565 observations)

- roc_auc: 0.9893
- pr_auc: 0.9905
- overall_accuracy: 0.9593
- sensitivity: 0.9659
- specificity: 0.9535
- precision: 0.9480
- f1_score: 0.9568
- mcc: 0.9185
- FNR: 0.0341
- FPR: 0.0465
- optimal_threshold: 0.4541

## Multiclass model (247 observations)

- overall_accuracy: 0.5992
- macro_precision: 0.5876
- macro_recall: 0.5768
- macro_f1: 0.5800

Full provenance: `model_card.json` / `train_config.json`.
The models are also deployed beside this folder as `binary1.joblib` and `multiclass1.joblib` for auto-discovery by Model Prediction.
