import os
import shutil

base_dir = "/Users/akshdharodiya/Desktop/projects/police_watch/18_09_26"
models_synth_dir = os.path.join(base_dir, "models", "synthetic_model")
models_ft_dir = os.path.join(base_dir, "models", "fine_tuned_models")
models_scratch_dir = os.path.join(base_dir, "models", "real_scratch_models")

data_train_dir = os.path.join(base_dir, "data", "train")
data_val_dir = os.path.join(base_dir, "data", "val")
data_test_dir = os.path.join(base_dir, "data", "test")

code_dir = os.path.join(base_dir, "code")
nb_dir = os.path.join(base_dir, "notebooks")

for d in [models_synth_dir, models_ft_dir, models_scratch_dir, data_train_dir, data_val_dir, data_test_dir, code_dir, nb_dir]:
    os.makedirs(d, exist_ok=True)
    print(f"Directory ready: {d}")

# Copy Model 1 ONNX
src_m1_onnx = "/Users/akshdharodiya/Desktop/projects/police_watch/testing_model/full_dataset_model_filewearable_model.onnx"
dst_m1_onnx = os.path.join(models_synth_dir, "wearable_model_state_synthetic.onnx")
if os.path.exists(src_m1_onnx):
    shutil.copy2(src_m1_onnx, dst_m1_onnx)
    print(f"Copied Model 1 ONNX -> {dst_m1_onnx}")

# Copy Model 1 PyTorch Checkpoint (snapshot)
# Let's find the latest snapshot
snapshot_dir = "/Users/akshdharodiya/Desktop/projects/police_watch/model_trainig_work/snapshots"
if os.path.exists(snapshot_dir):
    snapshots = [f for f in os.listdir(snapshot_dir) if f.startswith("snapshot_") and f.endswith(".pt")]
    if snapshots:
        # Sort by step number
        snapshots.sort(key=lambda x: int(x.replace("snapshot_", "").replace(".pt", "")))
        latest_snapshot = snapshots[-1]
        src_pt = os.path.join(snapshot_dir, latest_snapshot)
        dst_pt = os.path.join(models_synth_dir, "wearable_model_state_synthetic.pt")
        shutil.copy2(src_pt, dst_pt)
        print(f"Copied Model 1 PyTorch checkpoint ({latest_snapshot}) -> {dst_pt}")

# Copy Model 2 ONNX
src_m2_onnx = "/Users/akshdharodiya/Desktop/projects/police_watch/testing_model/model2/distraction_model (1).onnx"
dst_m2_onnx = os.path.join(models_synth_dir, "distraction_model_synthetic.onnx")
if os.path.exists(src_m2_onnx):
    shutil.copy2(src_m2_onnx, dst_m2_onnx)
    print(f"Copied Model 2 ONNX -> {dst_m2_onnx}")

print("\nSetup & Model Copying Completed Successfully!")
