#!/usr/bin/env python3
"""
ONNX EXPORT-ONLY UTILITY — loads the trained .pth weights and exports/verifies ONNX.
(Used when training already completed; mirrors train_onnx.py's export step.)
"""
import os
import json
import numpy as np
import torch

from train_onnx import (ImitationPolicyNet, NormalizedPolicy, OBS_SCALE,
                        load_transitions, HERE, MODELS_DIR, SEED)

PTH = os.path.join(MODELS_DIR, "imitation_policy_750ep.pth")
ONNX = os.path.join(MODELS_DIR, "imitation_policy_750ep.onnx")


def main():
    net = ImitationPolicyNet()
    net.load_state_dict(torch.load(PTH, map_location="cpu"))
    net.eval()
    wrapper = NormalizedPolicy(net, OBS_SCALE).eval()
    dummy = torch.randn(1, 9) * 90.0

    torch.onnx.export(
        wrapper, dummy, ONNX,
        input_names=["observation"], output_names=["action"],
        dynamic_axes={"observation": {0: "batch"}, "action": {0: "batch"}},
        opset_version=14, dynamo=False,
    )
    print(f"Exported: {ONNX}")

    # Verify against PyTorch on real dataset frames
    import onnxruntime as ort
    obs, acts, _, _ = load_transitions()
    sess = ort.InferenceSession(ONNX, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(SEED)
    sample = rng.choice(len(obs), size=4096, replace=False)
    torch_out = wrapper(torch.from_numpy(obs[sample])).detach().numpy()
    ort_out = sess.run(["action"], {"observation": obs[sample]})[0]
    err = np.abs(torch_out - ort_out).max()
    print(f"ONNX vs PyTorch max abs diff: {err:.6f} ({'PASS' if err < 1e-3 else 'FAIL'})")

    # Sanity demo: feed a real observation from episode 1 (home frame + pick frame)
    with open(os.path.join(HERE, "datasets", "episode_001.json")) as fh:
        ep1 = json.load(fh)
    p = ep1["initial_block_pose"]
    for tag, fr in [("home", ep1["trajectory"][0]), ("pick", ep1["trajectory"][261])]:
        raw = np.array(fr["joints"] + [fr["gripper_state"], p["x_cm"], p["y_cm"], p["theta_deg"]],
                       dtype=np.float32)[None, :]
        a = sess.run(["action"], {"observation": raw})[0][0]
        print(f"  {tag:5s} obs={np.round(raw[0], 1).tolist()} -> "
              f"next joints={np.round(a[:5], 1).tolist()}, gripper open p={a[5]:.3f}")


if __name__ == "__main__":
    main()
